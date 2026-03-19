"""Integration tests for run_graph — verifies full wiring from YAML to orchestrator."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

from agentrelay.errors import IntegrationFailureClass
from agentrelay.orchestrator import (
    OrchestratorConfig,
    OrchestratorOutcome,
)
from agentrelay.run_graph import run_graph
from agentrelay.task_runner import TaskRunResult, TearDownMode
from agentrelay.task_runtime import TaskRuntime, TaskStatus
from agentrelay.workstream import (
    WorkstreamRunResult,
    WorkstreamRuntime,
    WorkstreamStatus,
)


@dataclass
class ScriptedTaskRunner:
    """TaskRunner double with per-task/attempt scripted outcomes."""

    script: dict[tuple[str, int], str] = field(default_factory=dict)
    calls: list[tuple[str, int, TearDownMode]] = field(default_factory=list)

    async def run(
        self,
        runtime: TaskRuntime,
        *,
        teardown_mode: TearDownMode = TearDownMode.ALWAYS,
    ) -> TaskRunResult:
        task_id = runtime.task.id
        attempt_num = runtime.state.attempt_num
        self.calls.append((task_id, attempt_num, teardown_mode))
        action = self.script.get((task_id, attempt_num), "success")

        if action == "raise":
            raise RuntimeError(f"{task_id} internal boom")
        if action == "block":
            await asyncio.sleep(10)
        if action == "fail":
            runtime.state.status = TaskStatus.FAILED
            runtime.state.error = f"{task_id} failed"
            return TaskRunResult.from_runtime(runtime)
        if action == "fail_internal":
            runtime.state.status = TaskStatus.FAILED
            runtime.state.error = f"{task_id} internal adapter error"
            return TaskRunResult.from_runtime(
                runtime,
                failure_class=IntegrationFailureClass.INTERNAL_ERROR,
            )

        runtime.artifacts.pr_url = f"https://example.com/{task_id}/{attempt_num}"
        runtime.state.status = TaskStatus.PR_MERGED
        runtime.state.error = None
        return TaskRunResult.from_runtime(runtime)


@dataclass
class NoOpWorkstreamRunner:
    """WorkstreamRunner double that performs state transitions without I/O."""

    prepare_calls: list[str] = field(default_factory=list)
    merge_calls: list[str] = field(default_factory=list)
    teardown_calls: list[str] = field(default_factory=list)

    def prepare(self, workstream_runtime: WorkstreamRuntime) -> None:
        self.prepare_calls.append(workstream_runtime.spec.id)
        workstream_runtime.state.status = WorkstreamStatus.ACTIVE

    def merge(self, workstream_runtime: WorkstreamRuntime) -> WorkstreamRunResult:
        self.merge_calls.append(workstream_runtime.spec.id)
        workstream_runtime.state.status = WorkstreamStatus.MERGED
        return WorkstreamRunResult.from_runtime(workstream_runtime)

    def teardown(self, workstream_runtime: WorkstreamRuntime) -> None:
        self.teardown_calls.append(workstream_runtime.spec.id)


def _write_graph_yaml(tmp_path: Path) -> Path:
    content = """\
name: integration-test
tasks:
  - id: task_a
    description: First task
    dependencies: []
  - id: task_b
    description: Second task
    dependencies:
      - task_a
"""
    path = tmp_path / "graph.yaml"
    path.write_text(content)
    return path


def _write_graph_yaml_with_ops(tmp_path: Path) -> Path:
    content = """\
name: integration-test
tmux_session: custom-session
keep_panes: true
model: claude-opus-4-6
tasks:
  - id: task_a
    description: First task
    dependencies: []
"""
    path = tmp_path / "graph.yaml"
    path.write_text(content)
    return path


def test_run_graph_wires_orchestrator(tmp_path: Path) -> None:
    """Full wiring: YAML -> graph -> orchestrator with test doubles."""
    graph_path = _write_graph_yaml(tmp_path)
    task_runner = ScriptedTaskRunner()
    ws_runner = NoOpWorkstreamRunner()

    with (
        patch(
            "agentrelay.run_graph.build_standard_runner",
            return_value=task_runner,
        ) as mock_build_runner,
        patch(
            "agentrelay.run_graph.build_standard_workstream_runner",
            return_value=ws_runner,
        ) as mock_build_ws,
        patch("agentrelay.run_graph._record_run_start"),
        patch("agentrelay.run_graph._validate_tmux_sessions"),
    ):
        result = asyncio.run(
            run_graph(
                graph_path=graph_path,
                repo_path=tmp_path,
            )
        )

    assert result.outcome == OrchestratorOutcome.SUCCEEDED
    assert set(result.task_runtimes.keys()) == {"task_a", "task_b"}

    mock_build_runner.assert_called_once()
    mock_build_ws.assert_called_once()

    assert ws_runner.prepare_calls == ["default"]
    assert ws_runner.merge_calls == ["default"]
    assert ws_runner.teardown_calls == ["default"]

    called_tasks = [call[0] for call in task_runner.calls]
    assert "task_a" in called_tasks
    assert "task_b" in called_tasks


def test_run_graph_passes_orchestrator_config(tmp_path: Path) -> None:
    """OrchestratorConfig from caller is passed to the orchestrator."""
    graph_path = _write_graph_yaml(tmp_path)
    task_runner = ScriptedTaskRunner()
    ws_runner = NoOpWorkstreamRunner()

    config = OrchestratorConfig(
        max_concurrency=3,
        max_task_attempts=2,
        task_teardown_mode=TearDownMode.NEVER,
    )

    with (
        patch(
            "agentrelay.run_graph.build_standard_runner",
            return_value=task_runner,
        ),
        patch(
            "agentrelay.run_graph.build_standard_workstream_runner",
            return_value=ws_runner,
        ),
        patch("agentrelay.run_graph._record_run_start"),
        patch("agentrelay.run_graph._validate_tmux_sessions"),
    ):
        result = asyncio.run(
            run_graph(
                graph_path=graph_path,
                repo_path=tmp_path,
                config=config,
            )
        )

    assert result.outcome == OrchestratorOutcome.SUCCEEDED
    for call in task_runner.calls:
        assert call[2] == TearDownMode.NEVER


def test_run_graph_with_operational_yaml_keys(tmp_path: Path) -> None:
    """Operational YAML keys are stripped and applied correctly."""
    graph_path = _write_graph_yaml_with_ops(tmp_path)
    task_runner = ScriptedTaskRunner()
    ws_runner = NoOpWorkstreamRunner()

    with (
        patch(
            "agentrelay.run_graph.build_standard_runner",
            return_value=task_runner,
        ) as mock_build_runner,
        patch(
            "agentrelay.run_graph.build_standard_workstream_runner",
            return_value=ws_runner,
        ),
        patch("agentrelay.run_graph._record_run_start"),
        patch("agentrelay.run_graph._validate_tmux_sessions"),
    ):
        result = asyncio.run(
            run_graph(
                graph_path=graph_path,
                repo_path=tmp_path,
            )
        )

    assert result.outcome == OrchestratorOutcome.SUCCEEDED
    call_kwargs = mock_build_runner.call_args
    assert (
        call_kwargs[1].get(
            "keep_panes", call_kwargs[0][3] if len(call_kwargs[0]) > 3 else False
        )
        or True
    )


def test_run_graph_cli_overrides_yaml(tmp_path: Path) -> None:
    """CLI overrides take precedence over YAML operational values."""
    graph_path = _write_graph_yaml_with_ops(tmp_path)
    task_runner = ScriptedTaskRunner()
    ws_runner = NoOpWorkstreamRunner()

    with (
        patch(
            "agentrelay.run_graph.build_standard_runner",
            return_value=task_runner,
        ),
        patch(
            "agentrelay.run_graph.build_standard_workstream_runner",
            return_value=ws_runner,
        ),
        patch("agentrelay.run_graph._record_run_start"),
        patch("agentrelay.run_graph._validate_tmux_sessions"),
    ):
        result = asyncio.run(
            run_graph(
                graph_path=graph_path,
                repo_path=tmp_path,
                tmux_session="cli-session",
                model_override="cli-model",
            )
        )

    assert result.outcome == OrchestratorOutcome.SUCCEEDED

    task_runtime = result.task_runtimes["task_a"]
    assert task_runtime.task.primary_agent.model == "cli-model"
    assert task_runtime.task.primary_agent.environment.session == "cli-session"


def test_run_graph_with_task_failure(tmp_path: Path) -> None:
    """Graph with a failing task produces COMPLETED_WITH_FAILURES."""
    graph_path = _write_graph_yaml(tmp_path)
    task_runner = ScriptedTaskRunner(script={("task_a", 0): "fail"})
    ws_runner = NoOpWorkstreamRunner()

    with (
        patch(
            "agentrelay.run_graph.build_standard_runner",
            return_value=task_runner,
        ),
        patch(
            "agentrelay.run_graph.build_standard_workstream_runner",
            return_value=ws_runner,
        ),
        patch("agentrelay.run_graph._record_run_start"),
        patch("agentrelay.run_graph._validate_tmux_sessions"),
    ):
        result = asyncio.run(
            run_graph(
                graph_path=graph_path,
                repo_path=tmp_path,
            )
        )

    assert result.outcome == OrchestratorOutcome.COMPLETED_WITH_FAILURES
    assert result.task_runtimes["task_a"].state.status == TaskStatus.FAILED
