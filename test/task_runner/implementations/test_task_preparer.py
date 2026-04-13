"""Tests for WorktreeTaskPreparer."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from agentrelay.agent_comm_protocol.manifest import InputFileInfo
from agentrelay.errors import _WorkspaceIntegrationError
from agentrelay.task import AdrVerbosity, AgentConfig, AgentRole, InputFrom, Task
from agentrelay.task_runner.core.io import TaskPreparer
from agentrelay.task_runner.implementations.task_preparer import (
    WorktreeTaskPreparer,
    _resolve_input_files,
)
from agentrelay.task_runtime import TaskRuntime


def _make_runtime(
    task_id: str = "task_1", role: AgentRole = AgentRole.GENERIC
) -> TaskRuntime:
    runtime = TaskRuntime(task=Task(id=task_id, role=role, description="Do something"))
    runtime.state.integration_branch = "agentrelay/demo"
    runtime.state.workstream_worktree_path = Path("/worktrees/demo/ws-1")
    return runtime


def _make_preparer(
    run_dir: Path = Path("/repo/.workflow/demo/runs/0"),
) -> WorktreeTaskPreparer:
    return WorktreeTaskPreparer(
        run_dir=run_dir,
        graph_name="demo",
        dependency_descriptions={"dep_1": "A dependency"},
    )


class TestWorktreeTaskPreparer:
    """Tests for WorktreeTaskPreparer.prepare."""

    @patch("agentrelay.task_runner.implementations.task_preparer.resolve_instructions")
    @patch("agentrelay.task_runner.implementations.task_preparer.policies_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_policies")
    @patch("agentrelay.task_runner.implementations.task_preparer.manifest_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_manifest")
    @patch("agentrelay.task_runner.implementations.task_preparer.signals")
    @patch("agentrelay.task_runner.implementations.task_preparer.git")
    def test_creates_branch_and_checks_out(
        self,
        mock_git: MagicMock,
        mock_signals: MagicMock,
        mock_build_manifest: MagicMock,
        _mock_manifest_to_dict: MagicMock,
        _mock_build_policies: MagicMock,
        _mock_policies_to_dict: MagicMock,
        _mock_resolve: MagicMock,
    ) -> None:
        """Calls git.branch_create and git.checkout in the workstream worktree."""
        preparer = _make_preparer(run_dir=Path("/repo/.workflow/demo/runs/0"))
        runtime = _make_runtime()
        mock_build_manifest.return_value = MagicMock()
        mock_git.current_branch.return_value = None  # Fresh prepare.

        preparer.prepare(runtime)

        mock_git.branch_create.assert_called_once_with(
            Path("/worktrees/demo/ws-1"),
            "agentrelay/demo/task_1",
            "agentrelay/demo",
            force=True,
        )
        mock_git.checkout.assert_called_once_with(
            Path("/worktrees/demo/ws-1"),
            "agentrelay/demo/task_1",
        )

    @patch("agentrelay.task_runner.implementations.task_preparer.resolve_instructions")
    @patch("agentrelay.task_runner.implementations.task_preparer.policies_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_policies")
    @patch("agentrelay.task_runner.implementations.task_preparer.manifest_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_manifest")
    @patch("agentrelay.task_runner.implementations.task_preparer.signals")
    @patch("agentrelay.task_runner.implementations.task_preparer.git")
    def test_writes_three_protocol_files(
        self,
        _mock_git: MagicMock,
        mock_signals: MagicMock,
        mock_build_manifest: MagicMock,
        mock_manifest_to_dict: MagicMock,
        mock_build_policies: MagicMock,
        mock_policies_to_dict: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Writes manifest.json, policies.json, and instructions.md."""
        mock_build_manifest.return_value = MagicMock()
        mock_manifest_to_dict.return_value = {"manifest": "data"}
        mock_build_policies.return_value = MagicMock()
        mock_policies_to_dict.return_value = {"policies": "data"}
        mock_resolve.return_value = "# Instructions"

        preparer = _make_preparer()
        runtime = _make_runtime()
        preparer.prepare(runtime)

        signal_dir = Path("/repo/.workflow/demo/runs/0/signals/task_1")
        mock_signals.write_json.assert_any_call(
            signal_dir, "manifest.json", {"manifest": "data"}
        )
        mock_signals.write_json.assert_any_call(
            signal_dir, "policies.json", {"policies": "data"}
        )
        mock_signals.write_text.assert_any_call(
            signal_dir, "instructions.md", "# Instructions"
        )

    @patch("agentrelay.task_runner.implementations.task_preparer.resolve_instructions")
    @patch("agentrelay.task_runner.implementations.task_preparer.policies_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_policies")
    @patch("agentrelay.task_runner.implementations.task_preparer.manifest_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_manifest")
    @patch("agentrelay.task_runner.implementations.task_preparer.signals")
    @patch("agentrelay.task_runner.implementations.task_preparer.git")
    def test_sets_runtime_state(
        self,
        _mock_git: MagicMock,
        _mock_signals: MagicMock,
        mock_build_manifest: MagicMock,
        _mock_manifest_to_dict: MagicMock,
        _mock_build_policies: MagicMock,
        _mock_policies_to_dict: MagicMock,
        _mock_resolve: MagicMock,
    ) -> None:
        """Sets worktree_path, branch_name, and signal_dir on runtime."""
        mock_build_manifest.return_value = MagicMock()
        preparer = _make_preparer()
        runtime = _make_runtime()

        preparer.prepare(runtime)

        assert runtime.state.worktree_path == Path("/worktrees/demo/ws-1")
        assert runtime.state.branch_name == "agentrelay/demo/task_1"
        assert runtime.state.signal_dir == Path(
            "/repo/.workflow/demo/runs/0/signals/task_1"
        )

    @patch("agentrelay.task_runner.implementations.task_preparer.resolve_instructions")
    @patch("agentrelay.task_runner.implementations.task_preparer.policies_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_policies")
    @patch("agentrelay.task_runner.implementations.task_preparer.manifest_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_manifest")
    @patch("agentrelay.task_runner.implementations.task_preparer.signals")
    @patch("agentrelay.task_runner.implementations.task_preparer.git")
    def test_writes_context_md_when_provided(
        self,
        _mock_git: MagicMock,
        mock_signals: MagicMock,
        mock_build_manifest: MagicMock,
        _mock_manifest_to_dict: MagicMock,
        _mock_build_policies: MagicMock,
        _mock_policies_to_dict: MagicMock,
        _mock_resolve: MagicMock,
    ) -> None:
        """Writes context.md when context_content is provided."""
        mock_build_manifest.return_value = MagicMock()
        preparer = _make_preparer()
        preparer.context_content = "# Context\nPrevious task output."

        runtime = _make_runtime()
        preparer.prepare(runtime)

        signal_dir = Path("/repo/.workflow/demo/runs/0/signals/task_1")
        mock_signals.write_text.assert_any_call(
            signal_dir, "context.md", "# Context\nPrevious task output."
        )

    @patch("agentrelay.task_runner.implementations.task_preparer.resolve_instructions")
    @patch("agentrelay.task_runner.implementations.task_preparer.policies_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_policies")
    @patch("agentrelay.task_runner.implementations.task_preparer.manifest_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_manifest")
    @patch("agentrelay.task_runner.implementations.task_preparer.signals")
    @patch("agentrelay.task_runner.implementations.task_preparer.git")
    def test_omits_context_md_when_not_provided(
        self,
        _mock_git: MagicMock,
        mock_signals: MagicMock,
        mock_build_manifest: MagicMock,
        _mock_manifest_to_dict: MagicMock,
        _mock_build_policies: MagicMock,
        _mock_policies_to_dict: MagicMock,
        _mock_resolve: MagicMock,
    ) -> None:
        """Does not write context.md when context_content is None."""
        mock_build_manifest.return_value = MagicMock()
        preparer = _make_preparer()
        runtime = _make_runtime()

        preparer.prepare(runtime)

        context_calls = [
            c for c in mock_signals.write_text.call_args_list if c[0][1] == "context.md"
        ]
        assert context_calls == []

    @patch("agentrelay.task_runner.implementations.task_preparer.signals")
    @patch("agentrelay.task_runner.implementations.task_preparer.git")
    def test_wraps_git_error_in_workspace_integration_error(
        self,
        mock_git: MagicMock,
        _mock_signals: MagicMock,
    ) -> None:
        """Wraps CalledProcessError from git in _WorkspaceIntegrationError."""
        mock_git.current_branch.return_value = None  # Fresh prepare.
        mock_git.branch_create.side_effect = subprocess.CalledProcessError(
            1, "git branch"
        )
        preparer = _make_preparer()
        runtime = _make_runtime()

        with pytest.raises(_WorkspaceIntegrationError, match="task_1"):
            preparer.prepare(runtime)

    @patch("agentrelay.task_runner.implementations.task_preparer.resolve_instructions")
    @patch("agentrelay.task_runner.implementations.task_preparer.policies_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_policies")
    @patch("agentrelay.task_runner.implementations.task_preparer.manifest_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_manifest")
    @patch("agentrelay.task_runner.implementations.task_preparer.signals")
    @patch("agentrelay.task_runner.implementations.task_preparer.git")
    def test_retry_skips_branch_creation_when_already_checked_out(
        self,
        mock_git: MagicMock,
        mock_signals: MagicMock,
        mock_build_manifest: MagicMock,
        _mock_manifest_to_dict: MagicMock,
        _mock_build_policies: MagicMock,
        _mock_policies_to_dict: MagicMock,
        _mock_resolve: MagicMock,
    ) -> None:
        """On retry, skips branch_create/checkout when branch is already checked out."""
        mock_git.current_branch.return_value = "agentrelay/demo/task_1"
        mock_build_manifest.return_value = MagicMock()
        preparer = _make_preparer()
        runtime = _make_runtime()

        preparer.prepare(runtime)

        mock_git.branch_create.assert_not_called()
        mock_git.checkout.assert_not_called()
        # Protocol files are still written.
        signal_dir = Path("/repo/.workflow/demo/runs/0/signals/task_1")
        mock_signals.write_json.assert_any_call(
            signal_dir, "manifest.json", _mock_manifest_to_dict.return_value
        )

    @patch("agentrelay.task_runner.implementations.task_preparer.resolve_instructions")
    @patch("agentrelay.task_runner.implementations.task_preparer.policies_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_policies")
    @patch("agentrelay.task_runner.implementations.task_preparer.manifest_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_manifest")
    @patch("agentrelay.task_runner.implementations.task_preparer.signals")
    @patch("agentrelay.task_runner.implementations.task_preparer.git")
    def test_passes_adr_verbosity_to_resolve_instructions(
        self,
        _mock_git: MagicMock,
        _mock_signals: MagicMock,
        mock_build_manifest: MagicMock,
        _mock_manifest_to_dict: MagicMock,
        _mock_build_policies: MagicMock,
        _mock_policies_to_dict: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Passes task's adr_verbosity to resolve_instructions."""
        mock_build_manifest.return_value = MagicMock()
        task = Task(
            id="adr_task",
            role=AgentRole.GENERIC,
            description="Do something",
            primary_agent=AgentConfig(adr_verbosity=AdrVerbosity.STANDARD),
        )
        runtime = TaskRuntime(task=task)
        runtime.state.integration_branch = "agentrelay/demo"
        runtime.state.workstream_worktree_path = Path("/worktrees/demo/ws-1")

        preparer = _make_preparer()
        preparer.prepare(runtime)

        mock_resolve.assert_called_once()
        _, kwargs = mock_resolve.call_args
        assert kwargs.get("adr_verbosity") == AdrVerbosity.STANDARD

    @patch("agentrelay.task_runner.implementations.task_preparer.resolve_instructions")
    @patch("agentrelay.task_runner.implementations.task_preparer.policies_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_policies")
    @patch("agentrelay.task_runner.implementations.task_preparer.manifest_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_manifest")
    @patch("agentrelay.task_runner.implementations.task_preparer.signals")
    @patch("agentrelay.task_runner.implementations.task_preparer.git")
    def test_passes_worktree_path_to_resolve_instructions(
        self,
        _mock_git: MagicMock,
        _mock_signals: MagicMock,
        mock_build_manifest: MagicMock,
        _mock_manifest_to_dict: MagicMock,
        _mock_build_policies: MagicMock,
        _mock_policies_to_dict: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Passes workstream_worktree_path as worktree_path to resolve_instructions."""
        mock_build_manifest.return_value = MagicMock()
        preparer = _make_preparer()
        runtime = _make_runtime()

        preparer.prepare(runtime)

        mock_resolve.assert_called_once()
        _, kwargs = mock_resolve.call_args
        assert kwargs.get("worktree_path") == Path("/worktrees/demo/ws-1")

    @patch("agentrelay.task_runner.implementations.task_preparer.resolve_instructions")
    @patch("agentrelay.task_runner.implementations.task_preparer.policies_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_policies")
    @patch("agentrelay.task_runner.implementations.task_preparer.manifest_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_manifest")
    @patch("agentrelay.task_runner.implementations.task_preparer.signals")
    @patch("agentrelay.task_runner.implementations.task_preparer.git")
    def test_passes_graph_paths_to_resolve_instructions(
        self,
        _mock_git: MagicMock,
        _mock_signals: MagicMock,
        mock_build_manifest: MagicMock,
        _mock_manifest_to_dict: MagicMock,
        _mock_build_policies: MagicMock,
        _mock_policies_to_dict: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Passes graph_yaml_path and signals_base_path to resolve_instructions."""
        mock_build_manifest.return_value = MagicMock()
        preparer = _make_preparer()
        runtime = _make_runtime()

        preparer.prepare(runtime)

        mock_resolve.assert_called_once()
        _, kwargs = mock_resolve.call_args
        assert kwargs.get("graph_yaml_path") == Path(
            "/repo/.workflow/demo/runs/0/graph.yaml"
        )
        assert kwargs.get("signals_base_path") == Path(
            "/repo/.workflow/demo/runs/0/signals"
        )

    def test_satisfies_task_preparer_protocol(self) -> None:
        """WorktreeTaskPreparer satisfies the TaskPreparer protocol."""
        preparer = _make_preparer()
        assert isinstance(preparer, TaskPreparer)


class TestResolveInputFiles:
    """Tests for _resolve_input_files."""

    def _make_run_dir(self, tmp_path: Path) -> Path:
        run_dir = tmp_path / ".workflow" / "g" / "runs" / "0"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _write_outputs_json(
        self, run_dir: Path, task_id: str, files: list[dict]
    ) -> None:
        """Write a mock outputs.json for an upstream task."""
        import json

        signal_dir = run_dir / "signals" / task_id
        signal_dir.mkdir(parents=True, exist_ok=True)
        (signal_dir / "outputs.json").write_text(
            json.dumps({"schema_version": "1", "files": files})
        )

    def test_resolves_from_upstream_outputs(self, tmp_path: Path) -> None:
        """Reads upstream outputs.json and returns InputFileInfo entries."""
        run_dir = self._make_run_dir(tmp_path)
        self._write_outputs_json(
            run_dir,
            "spec",
            [{"path": "src/q.py", "action": "created", "category": "stubs"}],
        )
        task = Task(
            id="impl",
            role=AgentRole.GENERIC,
            inputs_from=(InputFrom(task="spec", category="stubs"),),
        )
        result = _resolve_input_files(task, run_dir)
        assert result == (
            InputFileInfo(path=Path("src/q.py"), category="stubs", source_task="spec"),
        )

    def test_filters_by_category(self, tmp_path: Path) -> None:
        """Only entries matching the category are returned."""
        run_dir = self._make_run_dir(tmp_path)
        self._write_outputs_json(
            run_dir,
            "spec",
            [
                {"path": "src/q.py", "action": "created", "category": "stubs"},
                {"path": "docs/spec.md", "action": "created", "category": "spec"},
            ],
        )
        task = Task(
            id="impl",
            role=AgentRole.GENERIC,
            inputs_from=(InputFrom(task="spec", category="stubs"),),
        )
        result = _resolve_input_files(task, run_dir)
        assert len(result) == 1
        assert result[0].path == Path("src/q.py")

    def test_no_category_takes_all(self, tmp_path: Path) -> None:
        """When category is None, all entries are included."""
        run_dir = self._make_run_dir(tmp_path)
        self._write_outputs_json(
            run_dir,
            "spec",
            [
                {"path": "src/q.py", "action": "created", "category": "stubs"},
                {"path": "docs/spec.md", "action": "created", "category": "spec"},
            ],
        )
        task = Task(
            id="impl",
            role=AgentRole.GENERIC,
            inputs_from=(InputFrom(task="spec", category=None),),
        )
        result = _resolve_input_files(task, run_dir)
        assert len(result) == 2

    def test_missing_outputs_raises(self, tmp_path: Path) -> None:
        """Missing outputs.json raises FileNotFoundError."""
        run_dir = self._make_run_dir(tmp_path)
        # Signal dir exists but no outputs.json
        signal_dir = run_dir / "signals" / "spec"
        signal_dir.mkdir(parents=True, exist_ok=True)

        task = Task(
            id="impl",
            role=AgentRole.GENERIC,
            inputs_from=(InputFrom(task="spec"),),
        )
        with pytest.raises(FileNotFoundError, match="upstream task 'spec'"):
            _resolve_input_files(task, run_dir)

    def test_skipped_when_empty(self) -> None:
        """Task without inputs_from returns empty tuple."""
        task = Task(id="t1", role=AgentRole.GENERIC)
        result = _resolve_input_files(task, Path("/unused"))
        assert result == ()

    def test_multiple_sources(self, tmp_path: Path) -> None:
        """Multiple inputs_from entries combine results from all sources."""
        run_dir = self._make_run_dir(tmp_path)
        self._write_outputs_json(
            run_dir,
            "spec",
            [{"path": "src/q.py", "action": "created", "category": "stubs"}],
        )
        self._write_outputs_json(
            run_dir,
            "test",
            [{"path": "test/test_q.py", "action": "created", "category": "tests"}],
        )
        task = Task(
            id="impl",
            role=AgentRole.GENERIC,
            inputs_from=(
                InputFrom(task="spec", category="stubs"),
                InputFrom(task="test", category="tests"),
            ),
        )
        result = _resolve_input_files(task, run_dir)
        assert len(result) == 2
        assert result[0].source_task == "spec"
        assert result[1].source_task == "test"
