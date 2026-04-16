"""Unit tests for run_graph module — YAML pre-processing, dry-run, and builder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentrelay.orchestrator import OrchestratorConfig
from agentrelay.orchestrator.builders import build_standard_workstream_runner
from agentrelay.orchestrator.probe import (  # noqa: F401
    GraphProbe,
    TaskProbe,
    WorkstreamProbe,
)
from agentrelay.resolved import ResolvedTask, ResolvedWorkstream  # noqa: F401
from agentrelay.run_graph import (
    OperationalConfig,
    _any_task_uses_oci,
    _apply_overrides,
    _build_parser,
    _build_resume_runtimes,
    _compare_run_configs,
    _copy_frozen_artifacts,
    _copy_graph_yaml,
    _extract_operational_config,
    _load_and_prepare_graph,
    _read_prior_start_head,
    _record_run_config,
    _record_run_start,
    _resolve_override,
    _resolve_run_context,
    _RunContext,
    dry_run,
)
from agentrelay.sandbox import IsolationConfig, SandboxType, TokenTier
from agentrelay.task import AgentConfig, AgentRole, Task
from agentrelay.task_graph import TaskGraph
from agentrelay.workstream.implementations.workstream_integrator import (
    GhWorkstreamIntegrator,
)
from agentrelay.workstream.implementations.workstream_preparer import (
    GitWorkstreamPreparer,
)
from agentrelay.workstream.implementations.workstream_teardown import (
    GitWorkstreamTeardown,
)

# --- _extract_operational_config ---


def test_extract_operational_config_defaults() -> None:
    raw: dict = {"name": "g", "tasks": []}
    ops = _extract_operational_config(raw)
    assert ops.keep_panes is False
    assert ops.model is None
    assert ops.tools == ()
    assert ops.anthropic_credential is None
    assert ops.fail_fast_on_workstream_error is None
    assert ops.fail_fast_on_internal_error is None
    assert ops.max_concurrency is None
    assert ops.max_task_attempts is None
    assert ops.teardown_mode is None


def test_extract_operational_config_reads_yaml_values() -> None:
    raw: dict = {
        "name": "g",
        "tasks": [],
        "keep_panes": True,
        "model": "claude-opus-4-6",
    }
    ops = _extract_operational_config(raw)
    assert ops.keep_panes is True
    assert ops.model == "claude-opus-4-6"
    assert ops.tools == ()


def test_extract_operational_config_pops_keys() -> None:
    raw: dict = {
        "name": "g",
        "tasks": [],
        "keep_panes": True,
        "model": "m",
        "tools": ["pixi"],
        "anthropic_credential": "max_plan",
        "fail_fast_on_workstream_error": True,
        "fail_fast_on_internal_error": False,
        "max_concurrency": 4,
        "max_task_attempts": 2,
        "teardown_mode": "never",
    }
    _extract_operational_config(raw)
    assert "keep_panes" not in raw
    assert "model" not in raw
    assert "tools" not in raw
    assert "anthropic_credential" not in raw
    assert "fail_fast_on_workstream_error" not in raw
    assert "fail_fast_on_internal_error" not in raw
    assert "max_concurrency" not in raw
    assert "max_task_attempts" not in raw
    assert "teardown_mode" not in raw
    assert "name" in raw


def test_extract_operational_config_does_not_pop_tmux_session() -> None:
    """tmux_session is no longer an operational key — it stays in the dict."""
    raw: dict = {"name": "g", "tasks": [], "tmux_session": "x"}
    _extract_operational_config(raw)
    assert "tmux_session" in raw


def test_extract_operational_config_parses_tools() -> None:
    raw: dict = {"name": "g", "tasks": [], "tools": ["pixi", "npm"]}
    ops = _extract_operational_config(raw)
    assert ops.tools == ("pixi", "npm")
    assert "tasks" in raw


def test_extract_operational_config_reads_anthropic_credential() -> None:
    raw: dict = {"name": "g", "tasks": [], "anthropic_credential": "max_plan"}
    ops = _extract_operational_config(raw)
    assert ops.anthropic_credential == "max_plan"


# --- _apply_overrides ---


def test_apply_overrides_tmux_session() -> None:
    raw: dict = {"tasks": [{"id": "a"}, {"id": "b"}]}
    _apply_overrides(raw, tmux_session="my-session")
    for task in raw["tasks"]:
        assert task["primary_agent"]["environment"]["session"] == "my-session"


def test_apply_overrides_model() -> None:
    raw: dict = {"tasks": [{"id": "a"}, {"id": "b"}]}
    _apply_overrides(raw, model="claude-opus-4-6")
    for task in raw["tasks"]:
        assert task["primary_agent"]["model"] == "claude-opus-4-6"


def test_apply_overrides_both() -> None:
    raw: dict = {"tasks": [{"id": "a", "primary_agent": {"model": "old"}}]}
    _apply_overrides(raw, tmux_session="s", model="new")
    task = raw["tasks"][0]
    assert task["primary_agent"]["model"] == "new"
    assert task["primary_agent"]["environment"]["session"] == "s"


def test_apply_overrides_no_op_when_none() -> None:
    raw: dict = {"tasks": [{"id": "a"}]}
    original = {"tasks": [{"id": "a"}]}
    _apply_overrides(raw)
    assert raw == original


def test_apply_overrides_handles_empty_tasks() -> None:
    raw: dict = {"tasks": []}
    _apply_overrides(raw, tmux_session="s", model="m")
    assert raw == {"tasks": []}


def test_apply_overrides_sandbox_oci() -> None:
    raw: dict = {"tasks": [{"id": "a"}, {"id": "b"}]}
    _apply_overrides(raw, sandbox="oci")
    for task in raw["tasks"]:
        assert task["isolation"]["sandbox"] == "oci"


def test_apply_overrides_sandbox_none() -> None:
    raw: dict = {"tasks": [{"id": "a"}, {"id": "b"}]}
    _apply_overrides(raw, sandbox="none")
    for task in raw["tasks"]:
        assert task["isolation"]["sandbox"] == "none"


def test_apply_overrides_sandbox_preserves_token_tier() -> None:
    raw: dict = {
        "tasks": [
            {"id": "a", "isolation": {"sandbox": "oci", "token_tier": "elevated"}}
        ]
    }
    _apply_overrides(raw, sandbox="none")
    task = raw["tasks"][0]
    assert task["isolation"]["sandbox"] == "none"
    assert task["isolation"]["token_tier"] == "elevated"


def test_apply_overrides_sandbox_preserves_image_and_runtime() -> None:
    raw: dict = {
        "tasks": [
            {
                "id": "a",
                "isolation": {
                    "sandbox": "none",
                    "image": "custom:latest",
                    "runtime": "podman",
                },
            }
        ]
    }
    _apply_overrides(raw, sandbox="oci")
    task = raw["tasks"][0]
    assert task["isolation"]["sandbox"] == "oci"
    assert task["isolation"]["image"] == "custom:latest"
    assert task["isolation"]["runtime"] == "podman"


def test_apply_overrides_sandbox_creates_isolation_dict() -> None:
    raw: dict = {"tasks": [{"id": "a"}]}
    _apply_overrides(raw, sandbox="oci")
    assert raw["tasks"][0]["isolation"] == {"sandbox": "oci"}


def test_apply_overrides_sandbox_with_model_and_session() -> None:
    raw: dict = {"tasks": [{"id": "a"}]}
    _apply_overrides(raw, tmux_session="s", model="m", sandbox="oci")
    task = raw["tasks"][0]
    assert task["primary_agent"]["model"] == "m"
    assert task["primary_agent"]["environment"]["session"] == "s"
    assert task["isolation"]["sandbox"] == "oci"


def test_apply_overrides_sandbox_overrides_primary_agent() -> None:
    raw: dict = {
        "tasks": [
            {
                "id": "a",
                "primary_agent": {
                    "isolation": {"sandbox": "none", "token_tier": "elevated"}
                },
            }
        ]
    }
    _apply_overrides(raw, sandbox="oci")
    task = raw["tasks"][0]
    assert task["isolation"]["sandbox"] == "oci"
    assert task["primary_agent"]["isolation"]["sandbox"] == "oci"
    assert task["primary_agent"]["isolation"]["token_tier"] == "elevated"


def test_apply_overrides_sandbox_overrides_review_agent() -> None:
    raw: dict = {
        "tasks": [
            {
                "id": "a",
                "review": {
                    "agent": {"isolation": {"sandbox": "none"}},
                    "review_on_attempt": 1,
                },
            }
        ]
    }
    _apply_overrides(raw, sandbox="oci")
    task = raw["tasks"][0]
    assert task["isolation"]["sandbox"] == "oci"
    assert task["review"]["agent"]["isolation"]["sandbox"] == "oci"


def test_apply_overrides_sandbox_skips_absent_agents() -> None:
    """Sandbox override doesn't create primary_agent or review when absent."""
    raw: dict = {"tasks": [{"id": "a"}]}
    _apply_overrides(raw, sandbox="oci")
    assert "primary_agent" not in raw["tasks"][0]
    assert "review" not in raw["tasks"][0]
    assert raw["tasks"][0]["isolation"]["sandbox"] == "oci"


# --- dry_run ---


def _minimal_graph_yaml(tmp_path: Path) -> Path:
    """Write a minimal valid graph YAML and return its path."""
    content = """\
name: test-graph
tasks:
  - id: task_a
    description: First task
    dependencies: []
  - id: task_b
    description: Second task depends on A
    dependencies:
      - task_a
"""
    path = tmp_path / "test.yaml"
    path.write_text(content)
    return path


def test_dry_run_prints_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    graph_path = _minimal_graph_yaml(tmp_path)
    dry_run(graph_path)
    output = capsys.readouterr().out

    assert "test-graph" in output
    assert "Tasks: 2" in output
    assert "task_a" in output
    assert "task_b" in output
    assert "Roots" in output
    assert "Leaves" in output


def test_dry_run_with_operational_keys(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Operational keys in YAML are stripped before graph parsing."""
    content = """\
name: test-graph
keep_panes: true
model: claude-opus-4-6
tasks:
  - id: task_a
    dependencies: []
"""
    path = tmp_path / "test.yaml"
    path.write_text(content)
    dry_run(path)
    output = capsys.readouterr().out
    assert "test-graph" in output
    assert "task_a" in output


# --- build_standard_workstream_runner ---


def test_build_standard_workstream_runner_types(tmp_path: Path) -> None:
    run_dir = tmp_path / ".workflow" / "test-graph" / "runs" / "0"
    runner = build_standard_workstream_runner(
        repo_path=tmp_path,
        graph_name="test-graph",
        run_dir=run_dir,
    )
    assert isinstance(runner._preparer, GitWorkstreamPreparer)
    assert isinstance(runner._integrator, GhWorkstreamIntegrator)
    assert isinstance(runner._teardown, GitWorkstreamTeardown)


def test_build_standard_workstream_runner_preparer_config(tmp_path: Path) -> None:
    run_dir = tmp_path / ".workflow" / "my-graph" / "runs" / "0"
    runner = build_standard_workstream_runner(
        repo_path=tmp_path,
        graph_name="my-graph",
        run_dir=run_dir,
    )
    preparer = runner._preparer
    assert isinstance(preparer, GitWorkstreamPreparer)
    assert preparer.repo_path == tmp_path
    assert preparer.graph_name == "my-graph"
    assert preparer.run_dir == run_dir


def test_build_standard_workstream_runner_integrator_config(tmp_path: Path) -> None:
    run_dir = tmp_path / ".workflow" / "my-graph" / "runs" / "0"
    runner = build_standard_workstream_runner(
        repo_path=tmp_path,
        graph_name="my-graph",
        run_dir=run_dir,
    )
    integrator = runner._integrator
    assert isinstance(integrator, GhWorkstreamIntegrator)
    assert integrator.repo_path == tmp_path


def test_build_standard_workstream_runner_teardown_config(tmp_path: Path) -> None:
    run_dir = tmp_path / ".workflow" / "my-graph" / "runs" / "0"
    runner = build_standard_workstream_runner(
        repo_path=tmp_path,
        graph_name="my-graph",
        run_dir=run_dir,
    )
    teardown = runner._teardown
    assert isinstance(teardown, GitWorkstreamTeardown)
    assert teardown.repo_path == tmp_path


# --- _any_task_uses_oci ---


def test_any_task_uses_oci_false_when_no_isolation() -> None:
    """Returns False when no tasks have isolation config."""
    graph = TaskGraph.from_tasks(
        (
            Task(id="a", role=AgentRole.GENERIC),
            Task(id="b", role=AgentRole.GENERIC, dependencies=("a",)),
        )
    )
    assert _any_task_uses_oci(graph) is False


def test_any_task_uses_oci_true_when_oci_task() -> None:
    """Returns True when at least one task uses OCI sandbox."""
    oci_config = AgentConfig(
        isolation=IsolationConfig(
            sandbox_type=SandboxType.OCI,
            token_tier=TokenTier.STANDARD,
        ),
    )
    graph = TaskGraph.from_tasks(
        (
            Task(id="a", role=AgentRole.GENERIC),
            Task(id="b", role=AgentRole.GENERIC, primary_agent=oci_config),
        )
    )
    assert _any_task_uses_oci(graph) is True


def test_any_task_uses_oci_false_when_all_none_sandbox() -> None:
    """Returns False when all tasks explicitly use SandboxType.NONE."""
    none_config = AgentConfig(
        isolation=IsolationConfig(
            sandbox_type=SandboxType.NONE,
            token_tier=TokenTier.STANDARD,
        ),
    )
    graph = TaskGraph.from_tasks(
        (Task(id="a", role=AgentRole.GENERIC, primary_agent=none_config),)
    )
    assert _any_task_uses_oci(graph) is False


def test_any_task_uses_oci_round_trip_from_yaml(tmp_path: Path) -> None:
    """YAML with isolation: {sandbox: oci} is detected by _any_task_uses_oci."""
    content = """\
name: oci-yaml-test
isolation:
  sandbox: oci
  token_tier: standard
tasks:
  - id: task_a
    description: Task with OCI isolation
    dependencies: []
"""
    path = tmp_path / "graph.yaml"
    path.write_text(content)
    graph, _ = _load_and_prepare_graph(path)
    assert _any_task_uses_oci(graph) is True


def test_any_task_uses_oci_round_trip_no_isolation_yaml(tmp_path: Path) -> None:
    """YAML without isolation config is not detected as OCI."""
    content = """\
name: plain-test
tasks:
  - id: task_a
    description: Plain task
    dependencies: []
"""
    path = tmp_path / "graph.yaml"
    path.write_text(content)
    graph, _ = _load_and_prepare_graph(path)
    assert _any_task_uses_oci(graph) is False


# --- _copy_graph_yaml ---


def test_copy_graph_yaml_writes_file(tmp_path: Path) -> None:
    """graph.yaml is written to run directory with identical bytes."""
    source = tmp_path / "my-graph.yaml"
    source.write_text("name: my-graph\ntasks:\n  - id: a\n    description: do stuff\n")

    run_dir = tmp_path / ".workflow" / "my-graph" / "runs" / "0"
    run_dir.mkdir(parents=True)

    _copy_graph_yaml(run_dir, source)

    dest = run_dir / "graph.yaml"
    assert dest.is_file()
    assert dest.read_bytes() == source.read_bytes()


def test_copy_graph_yaml_preserves_comments(tmp_path: Path) -> None:
    """YAML comments and formatting are preserved byte-for-byte."""
    content = "# This is a comment\nname: test  # inline comment\ntasks:\n  - id: a\n    description: task\n    dependencies: []\n"
    source = tmp_path / "graph.yaml"
    source.write_text(content)

    run_dir = tmp_path / ".workflow" / "test" / "runs" / "0"
    run_dir.mkdir(parents=True)

    _copy_graph_yaml(run_dir, source)

    dest = run_dir / "graph.yaml"
    assert dest.read_text() == content


# --- _record_run_config ---


def test_record_run_config_writes_file(tmp_path: Path) -> None:
    """run_config.json is written with all effective config fields."""
    run_dir = tmp_path / ".workflow" / "my-graph" / "runs" / "0"
    run_dir.mkdir(parents=True)

    config = OrchestratorConfig(
        max_concurrency=4,
        max_task_attempts=2,
        fail_fast_on_internal_error=False,
        fail_fast_on_workstream_error=True,
    )
    _record_run_config(
        run_dir,
        config,
        keep_panes=True,
        model="claude-sonnet-4-6",
        sandbox="oci",
        anthropic_credential="my-key",
        verbose=True,
    )

    dest = run_dir / "run_config.json"
    assert dest.is_file()

    data = json.loads(dest.read_text())
    assert data["max_concurrency"] == 4
    assert data["max_task_attempts"] == 2
    assert data["task_teardown_mode"] == "always"
    assert data["fail_fast_on_internal_error"] is False
    assert data["fail_fast_on_workstream_error"] is True
    assert data["keep_panes"] is True
    assert data["model"] == "claude-sonnet-4-6"
    assert data["sandbox"] == "oci"
    assert data["anthropic_credential"] == "my-key"
    assert data["verbose"] is True


def test_record_run_config_handles_none_optionals(tmp_path: Path) -> None:
    """Optional fields are written as null when not set."""
    run_dir = tmp_path / ".workflow" / "test-graph" / "runs" / "0"
    run_dir.mkdir(parents=True)

    _record_run_config(
        run_dir,
        OrchestratorConfig(),
        keep_panes=False,
        model=None,
        sandbox=None,
        anthropic_credential=None,
        verbose=False,
    )

    data = json.loads((run_dir / "run_config.json").read_text())
    assert data["model"] is None
    assert data["sandbox"] is None
    assert data["anthropic_credential"] is None


# --- _resolve_run_context ---


def test_resolve_run_context_fresh_returns_runs_0(tmp_path: Path) -> None:
    """Fresh run (nothing exists) returns runs/0/ and creates it."""
    ctx = _resolve_run_context(tmp_path, "my-graph")
    assert ctx.run_dir == tmp_path / ".workflow" / "my-graph" / "runs" / "0"
    assert ctx.run_dir.is_dir()
    assert ctx.prior_run_dir is None
    assert ctx.is_resume is False
    assert ctx.run_number == 0
    assert ctx.prior_run_number is None


def test_resolve_run_context_resume_creates_next_run(tmp_path: Path) -> None:
    """Resume creates runs/1/ when runs/0/ exists."""
    run_0 = tmp_path / ".workflow" / "my-graph" / "runs" / "0"
    run_0.mkdir(parents=True)
    ctx = _resolve_run_context(tmp_path, "my-graph")
    assert ctx.run_dir == tmp_path / ".workflow" / "my-graph" / "runs" / "1"
    assert ctx.run_dir.is_dir()
    assert ctx.prior_run_dir == run_0
    assert ctx.is_resume is True
    assert ctx.run_number == 1
    assert ctx.prior_run_number == 0


def test_resolve_run_context_resume_multiple_prior_runs(tmp_path: Path) -> None:
    """Resume finds latest run and creates N+1."""
    for i in range(3):
        (tmp_path / ".workflow" / "g" / "runs" / str(i)).mkdir(parents=True)
    ctx = _resolve_run_context(tmp_path, "g")
    assert ctx.run_number == 3
    assert ctx.prior_run_number == 2


def test_resolve_run_context_workflow_exists_no_runs_raises(tmp_path: Path) -> None:
    """Workflow dir exists but no runs/ subdir raises RuntimeError."""
    (tmp_path / ".workflow" / "g").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="no run directories"):
        _resolve_run_context(tmp_path, "g")


# --- docker_build.sh syntax ---


# --- _extract_operational_config: fail_fast_on_workstream_error ---


def test_extract_operational_config_fail_fast_true() -> None:
    raw: dict = {"name": "g", "tasks": [], "fail_fast_on_workstream_error": True}
    ops = _extract_operational_config(raw)
    assert ops.fail_fast_on_workstream_error is True


def test_extract_operational_config_fail_fast_false() -> None:
    raw: dict = {"name": "g", "tasks": [], "fail_fast_on_workstream_error": False}
    ops = _extract_operational_config(raw)
    assert ops.fail_fast_on_workstream_error is False


def test_extract_operational_config_fail_fast_default_is_none() -> None:
    raw: dict = {"name": "g", "tasks": []}
    ops = _extract_operational_config(raw)
    assert ops.fail_fast_on_workstream_error is None


def test_extract_operational_config_fail_fast_pops_key() -> None:
    raw: dict = {"name": "g", "tasks": [], "fail_fast_on_workstream_error": True}
    _extract_operational_config(raw)
    assert "fail_fast_on_workstream_error" not in raw


def test_extract_operational_config_fail_fast_rejects_string() -> None:
    raw: dict = {"name": "g", "tasks": [], "fail_fast_on_workstream_error": "yes"}
    with pytest.raises(ValueError, match="must be a boolean"):
        _extract_operational_config(raw)


def test_extract_operational_config_fail_fast_rejects_int() -> None:
    raw: dict = {"name": "g", "tasks": [], "fail_fast_on_workstream_error": 1}
    with pytest.raises(ValueError, match="must be a boolean"):
        _extract_operational_config(raw)


# --- _extract_operational_config: fail_fast_on_internal_error ---


def test_extract_operational_config_fail_fast_internal_true() -> None:
    raw: dict = {"name": "g", "tasks": [], "fail_fast_on_internal_error": True}
    ops = _extract_operational_config(raw)
    assert ops.fail_fast_on_internal_error is True


def test_extract_operational_config_fail_fast_internal_false() -> None:
    raw: dict = {"name": "g", "tasks": [], "fail_fast_on_internal_error": False}
    ops = _extract_operational_config(raw)
    assert ops.fail_fast_on_internal_error is False


def test_extract_operational_config_fail_fast_internal_default_is_none() -> None:
    raw: dict = {"name": "g", "tasks": []}
    ops = _extract_operational_config(raw)
    assert ops.fail_fast_on_internal_error is None


def test_extract_operational_config_fail_fast_internal_pops_key() -> None:
    raw: dict = {"name": "g", "tasks": [], "fail_fast_on_internal_error": True}
    _extract_operational_config(raw)
    assert "fail_fast_on_internal_error" not in raw


def test_extract_operational_config_fail_fast_internal_rejects_string() -> None:
    raw: dict = {"name": "g", "tasks": [], "fail_fast_on_internal_error": "yes"}
    with pytest.raises(ValueError, match="must be a boolean"):
        _extract_operational_config(raw)


def test_extract_operational_config_fail_fast_internal_rejects_int() -> None:
    raw: dict = {"name": "g", "tasks": [], "fail_fast_on_internal_error": 1}
    with pytest.raises(ValueError, match="must be a boolean"):
        _extract_operational_config(raw)


# --- _extract_operational_config: max_concurrency ---


def test_extract_operational_config_max_concurrency() -> None:
    raw: dict = {"name": "g", "tasks": [], "max_concurrency": 4}
    ops = _extract_operational_config(raw)
    assert ops.max_concurrency == 4


def test_extract_operational_config_max_concurrency_pops_key() -> None:
    raw: dict = {"name": "g", "tasks": [], "max_concurrency": 2}
    _extract_operational_config(raw)
    assert "max_concurrency" not in raw


def test_extract_operational_config_max_concurrency_rejects_string() -> None:
    raw: dict = {"name": "g", "tasks": [], "max_concurrency": "four"}
    with pytest.raises(ValueError, match="must be an integer >= 1"):
        _extract_operational_config(raw)


def test_extract_operational_config_max_concurrency_rejects_zero() -> None:
    raw: dict = {"name": "g", "tasks": [], "max_concurrency": 0}
    with pytest.raises(ValueError, match="must be an integer >= 1"):
        _extract_operational_config(raw)


# --- _extract_operational_config: max_task_attempts ---


def test_extract_operational_config_max_task_attempts() -> None:
    raw: dict = {"name": "g", "tasks": [], "max_task_attempts": 3}
    ops = _extract_operational_config(raw)
    assert ops.max_task_attempts == 3


def test_extract_operational_config_max_task_attempts_pops_key() -> None:
    raw: dict = {"name": "g", "tasks": [], "max_task_attempts": 2}
    _extract_operational_config(raw)
    assert "max_task_attempts" not in raw


def test_extract_operational_config_max_task_attempts_rejects_zero() -> None:
    raw: dict = {"name": "g", "tasks": [], "max_task_attempts": 0}
    with pytest.raises(ValueError, match="must be an integer >= 1"):
        _extract_operational_config(raw)


# --- _extract_operational_config: teardown_mode ---


def test_extract_operational_config_teardown_mode() -> None:
    raw: dict = {"name": "g", "tasks": [], "teardown_mode": "never"}
    ops = _extract_operational_config(raw)
    assert ops.teardown_mode == "never"


def test_extract_operational_config_teardown_mode_pops_key() -> None:
    raw: dict = {"name": "g", "tasks": [], "teardown_mode": "always"}
    _extract_operational_config(raw)
    assert "teardown_mode" not in raw


def test_extract_operational_config_teardown_mode_rejects_invalid() -> None:
    raw: dict = {"name": "g", "tasks": [], "teardown_mode": "sometimes"}
    with pytest.raises(ValueError, match="must be one of"):
        _extract_operational_config(raw)


# --- dry_run: fail_fast operational keys stripped before builder ---


def test_dry_run_with_fail_fast_operational_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """fail_fast_on_workstream_error in YAML is stripped before graph parsing."""
    content = """\
name: test-graph
fail_fast_on_workstream_error: true
tasks:
  - id: task_a
    dependencies: []
"""
    path = tmp_path / "test.yaml"
    path.write_text(content)
    dry_run(path)
    output = capsys.readouterr().out
    assert "test-graph" in output
    assert "task_a" in output


def test_dry_run_with_fail_fast_internal_operational_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """fail_fast_on_internal_error in YAML is stripped before graph parsing."""
    content = """\
name: test-graph
fail_fast_on_internal_error: false
tasks:
  - id: task_a
    dependencies: []
"""
    path = tmp_path / "test.yaml"
    path.write_text(content)
    dry_run(path)
    output = capsys.readouterr().out
    assert "test-graph" in output
    assert "task_a" in output


# --- OrchestratorConfig defaults ---


def test_orchestrator_config_default_fail_fast_is_false() -> None:
    """Default for fail_fast_on_workstream_error changed from True to False."""
    config = OrchestratorConfig()
    assert config.fail_fast_on_workstream_error is False


def test_orchestrator_config_default_fail_fast_internal_is_true() -> None:
    """Default for fail_fast_on_internal_error is True."""
    config = OrchestratorConfig()
    assert config.fail_fast_on_internal_error is True


# --- _build_parser ---


def test_cli_parser_fail_fast_default_none() -> None:
    parser = _build_parser()
    args = parser.parse_args(["graph.yaml"])
    assert args.fail_fast_workstream is None


def test_cli_parser_fail_fast_true() -> None:
    parser = _build_parser()
    args = parser.parse_args(["graph.yaml", "--fail-fast-workstream"])
    assert args.fail_fast_workstream is True


def test_cli_parser_fail_fast_false() -> None:
    parser = _build_parser()
    args = parser.parse_args(["graph.yaml", "--no-fail-fast-workstream"])
    assert args.fail_fast_workstream is False


def test_cli_parser_fail_fast_internal_default_none() -> None:
    parser = _build_parser()
    args = parser.parse_args(["graph.yaml"])
    assert args.fail_fast_internal is None


def test_cli_parser_fail_fast_internal_true() -> None:
    parser = _build_parser()
    args = parser.parse_args(["graph.yaml", "--fail-fast-internal"])
    assert args.fail_fast_internal is True


def test_cli_parser_fail_fast_internal_false() -> None:
    parser = _build_parser()
    args = parser.parse_args(["graph.yaml", "--no-fail-fast-internal"])
    assert args.fail_fast_internal is False


def test_build_parser_short_options() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "graph.yaml",
            "-c",
            "4",
            "-s",
            "mysession",
            "-m",
            "claude-opus-4-6",
            "-C",
            "/tmp/creds.yaml",
            "-S",
            "oci",
        ]
    )
    assert args.max_concurrency == 4
    assert args.tmux_session == "mysession"
    assert args.model == "claude-opus-4-6"
    assert args.credentials == "/tmp/creds.yaml"
    assert args.sandbox == "oci"


def test_build_parser_sandbox_default_none() -> None:
    parser = _build_parser()
    args = parser.parse_args(["graph.yaml"])
    assert args.sandbox is None


# --- _load_and_prepare_graph: sandbox_override ---


def test_load_and_prepare_graph_sandbox_override_oci(tmp_path: Path) -> None:
    """--sandbox oci makes all tasks use OCI isolation."""
    content = """\
name: test-graph
tasks:
  - id: task_a
    description: Plain task
    dependencies: []
"""
    path = tmp_path / "graph.yaml"
    path.write_text(content)
    graph, _ = _load_and_prepare_graph(path, sandbox_override="oci")
    assert _any_task_uses_oci(graph) is True


def test_load_and_prepare_graph_sandbox_override_none(tmp_path: Path) -> None:
    """--sandbox none disables OCI even when graph YAML specifies it."""
    content = """\
name: test-graph
isolation:
  sandbox: oci
  token_tier: standard
tasks:
  - id: task_a
    description: OCI task
    dependencies: []
"""
    path = tmp_path / "graph.yaml"
    path.write_text(content)
    graph, _ = _load_and_prepare_graph(path, sandbox_override="none")
    assert _any_task_uses_oci(graph) is False


def test_load_and_prepare_graph_sandbox_override_preserves_token_tier(
    tmp_path: Path,
) -> None:
    """Sandbox override preserves token_tier from graph YAML."""
    content = """\
name: test-graph
isolation:
  sandbox: oci
  token_tier: elevated
tasks:
  - id: task_a
    description: Task with elevated tokens
    dependencies: []
"""
    path = tmp_path / "graph.yaml"
    path.write_text(content)
    graph, _ = _load_and_prepare_graph(path, sandbox_override="none")
    task = graph.task("task_a")
    assert task.primary_agent.isolation is not None
    assert task.primary_agent.isolation.sandbox_type == SandboxType.NONE
    assert task.primary_agent.isolation.token_tier == TokenTier.ELEVATED


def test_load_and_prepare_graph_rejects_tmux_session_in_yaml(
    tmp_path: Path,
) -> None:
    """tmux_session in graph YAML is rejected as an unknown key."""
    content = """\
name: test-graph
tmux_session: agentrelay
tasks:
  - id: task_a
    dependencies: []
"""
    path = tmp_path / "graph.yaml"
    path.write_text(content)
    with pytest.raises(ValueError, match="unknown key.*tmux_session"):
        _load_and_prepare_graph(path)


# --- _resolve_override ---


def test_resolve_override_cli_overrides_yaml() -> None:
    assert _resolve_override(cli_value=False, yaml_value=True) is False
    assert _resolve_override(cli_value=True, yaml_value=False) is True


def test_resolve_override_yaml_used_when_cli_none() -> None:
    assert _resolve_override(cli_value=None, yaml_value=True) is True
    assert _resolve_override(cli_value=None, yaml_value=False) is False


def test_resolve_override_none_when_both_none() -> None:
    assert _resolve_override(cli_value=None, yaml_value=None) is None


# --- docker_build.sh syntax ---


def test_docker_build_script_is_valid_bash() -> None:
    """tools/docker_build.sh passes bash syntax check."""
    import subprocess

    script = Path(__file__).resolve().parent.parent / "tools" / "docker_build.sh"
    assert script.is_file(), f"Script not found: {script}"
    result = subprocess.run(
        ["bash", "-n", str(script)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Bash syntax error: {result.stderr}"


# --- _copy_frozen_artifacts ---


def _make_task_probe(
    task_id: str,
    *,
    resolved: bool = False,
    status: str = "pending",
) -> TaskProbe:
    """Build a minimal TaskProbe for testing."""
    from agentrelay.task_runtime import TaskStatus

    status_enum = TaskStatus(status)
    resolved_obj: ResolvedTask | None = None
    if resolved:
        resolved_obj = ResolvedTask(
            task_id=task_id,
            workstream_id="ws-1",
            dependencies=(),
            inputs_from=(),
            role="generic",
            model=None,
            tagged_paths=(),
            branch_name=f"agentrelay/g/{task_id}",
            integration_branch="agentrelay/g/ws-1/integration",
            integration_branch_before_merge="abc123",
            completed_at_attempt=0,
            pr_url=f"https://github.com/test/repo/pull/1",
        )
    return TaskProbe(
        task_id=task_id,
        status=status_enum,
        signal_dir=Path("/fake/signals") / task_id,
        attempt_num=0,
        branch_name=f"agentrelay/g/{task_id}",
        pr_url=f"https://github.com/test/repo/pull/1" if resolved else None,
        resolved=resolved_obj,
    )


def _make_ws_probe(
    ws_id: str,
    *,
    status: str = "pending",
    resolved: bool = False,
) -> WorkstreamProbe:
    """Build a minimal WorkstreamProbe for testing."""
    from agentrelay.workstream.core.runtime import WorkstreamStatus

    status_enum = WorkstreamStatus(status)
    resolved_obj = None
    if resolved:
        resolved_obj = ResolvedWorkstream(
            workstream_id=ws_id,
            integration_pr_url="https://github.com/test/repo/pull/10",
            target_branch="main",
            target_branch_before_any_merge="def456",
            merge_occurred=True,
            merged_at="2026-04-16T00:00:00Z",
        )
    return WorkstreamProbe(
        workstream_id=ws_id,
        status=status_enum,
        signal_dir=Path("/fake/workstreams") / ws_id,
        worktree_path=Path("/fake/.worktrees/g") / ws_id,
        branch_name=f"agentrelay/g/{ws_id}/integration",
        merge_pr_url="https://github.com/test/repo/pull/10" if resolved else None,
        resolved=resolved_obj,
    )


def test_copy_frozen_artifacts_copies_resolved_and_outputs(tmp_path: Path) -> None:
    """Copies resolved.json, outputs.json, and status files for frozen tasks."""
    prior = tmp_path / "prior"
    new = tmp_path / "new"

    # Set up prior run signal dir for a frozen task.
    sig = prior / "signals" / "task_a"
    (sig / "status").mkdir(parents=True)
    (sig / "resolved.json").write_text('{"task_id": "task_a"}')
    (sig / "outputs.json").write_text('{"files": []}')
    (sig / "status" / "pr_merged").write_text("")

    probe = GraphProbe(
        task_probes={
            "task_a": _make_task_probe("task_a", resolved=True, status="pr_merged")
        },
        workstream_probes={},
    )
    _copy_frozen_artifacts(prior, new, probe)

    dst = new / "signals" / "task_a"
    assert (dst / "resolved.json").is_file()
    assert (dst / "outputs.json").is_file()
    assert (dst / "status" / "pr_merged").is_file()


def test_copy_frozen_artifacts_skips_non_frozen_tasks(tmp_path: Path) -> None:
    """Non-frozen tasks (no resolved.json) are not copied."""
    prior = tmp_path / "prior"
    sig = prior / "signals" / "task_b"
    (sig / "status").mkdir(parents=True)
    (sig / "status" / "failed").write_text("")

    probe = GraphProbe(
        task_probes={
            "task_b": _make_task_probe("task_b", resolved=False, status="failed")
        },
        workstream_probes={},
    )
    new = tmp_path / "new"
    _copy_frozen_artifacts(prior, new, probe)

    assert not (new / "signals" / "task_b").exists()


def test_copy_frozen_artifacts_copies_merged_workstream(tmp_path: Path) -> None:
    """Copies signal files for MERGED workstreams."""
    prior = tmp_path / "prior"
    ws_dir = prior / "workstreams" / "ws-1"
    ws_dir.mkdir(parents=True)
    (ws_dir / "resolved.json").write_text('{"workstream_id": "ws-1"}')
    (ws_dir / "merged").write_text("")
    (ws_dir / "pr_created").write_text("https://github.com/test/repo/pull/10")

    probe = GraphProbe(
        task_probes={},
        workstream_probes={
            "ws-1": _make_ws_probe("ws-1", status="merged", resolved=True)
        },
    )
    new = tmp_path / "new"
    _copy_frozen_artifacts(prior, new, probe)

    dst = new / "workstreams" / "ws-1"
    assert (dst / "resolved.json").is_file()
    assert (dst / "merged").is_file()
    assert (dst / "pr_created").is_file()


# --- _compare_run_configs ---


def test_compare_run_configs_matching(tmp_path: Path) -> None:
    """Matching configs return no warnings."""
    config = OrchestratorConfig()
    (tmp_path / "run_config.json").write_text(
        json.dumps(
            {
                "max_concurrency": config.max_concurrency,
                "max_task_attempts": config.max_task_attempts,
                "task_teardown_mode": config.task_teardown_mode.value,
                "model": None,
                "sandbox": None,
            }
        )
    )
    warnings = _compare_run_configs(tmp_path, config, model=None, sandbox=None)
    assert warnings == []


def test_compare_run_configs_detects_changes(tmp_path: Path) -> None:
    """Differing fields produce warnings."""
    config = OrchestratorConfig(max_concurrency=4)
    (tmp_path / "run_config.json").write_text(
        json.dumps(
            {
                "max_concurrency": 2,
                "max_task_attempts": config.max_task_attempts,
                "task_teardown_mode": config.task_teardown_mode.value,
                "model": None,
                "sandbox": None,
            }
        )
    )
    warnings = _compare_run_configs(tmp_path, config, model=None, sandbox=None)
    assert len(warnings) == 1
    assert "max_concurrency" in warnings[0]


def test_compare_run_configs_missing_file(tmp_path: Path) -> None:
    """Missing run_config.json returns empty list."""
    config = OrchestratorConfig()
    warnings = _compare_run_configs(tmp_path, config, model=None, sandbox=None)
    assert warnings == []


# --- _read_prior_start_head / _record_run_start ---


def test_read_prior_start_head(tmp_path: Path) -> None:
    """Reads start_head from run_info.json."""
    (tmp_path / "run_info.json").write_text(
        json.dumps({"start_head": "abc123", "started_at": "2026-01-01T00:00:00Z"})
    )
    assert _read_prior_start_head(tmp_path) == "abc123"


def test_record_run_start_with_override(tmp_path: Path) -> None:
    """start_head override is written instead of git rev-parse."""
    _record_run_start(tmp_path, tmp_path, start_head="override_sha")
    data = json.loads((tmp_path / "run_info.json").read_text())
    assert data["start_head"] == "override_sha"


# --- _build_resume_runtimes ---


def test_build_resume_runtimes_frozen_task(tmp_path: Path) -> None:
    """Frozen task gets signal_dir and branch_name from probe."""
    from agentrelay.task_graph import TaskGraphBuilder
    from agentrelay.task_runtime import TaskStatus

    graph = TaskGraphBuilder.from_dict(
        {"name": "g", "tasks": [{"id": "task_a", "description": "first"}]}
    )
    # Set up signal dir in new run dir (as _copy_frozen_artifacts would).
    sig_dir = tmp_path / "signals" / "task_a" / "status"
    sig_dir.mkdir(parents=True)
    (sig_dir / "pr_merged").write_text("")
    (tmp_path / "signals" / "task_a" / "resolved.json").write_text("{}")

    probe = GraphProbe(
        task_probes={
            "task_a": _make_task_probe("task_a", resolved=True, status="pr_merged")
        },
        workstream_probes={
            ws_id: _make_ws_probe(ws_id) for ws_id in graph.workstream_ids()
        },
    )
    task_rts, _ws_rts = _build_resume_runtimes(graph, probe, tmp_path)

    rt = task_rts["task_a"]
    assert rt.state.signal_dir == tmp_path / "signals" / "task_a"
    assert rt.status == TaskStatus.PR_MERGED


def test_build_resume_runtimes_non_frozen_task(tmp_path: Path) -> None:
    """Non-frozen task starts as PENDING with no signal_dir."""
    from agentrelay.task_graph import TaskGraphBuilder
    from agentrelay.task_runtime import TaskStatus

    graph = TaskGraphBuilder.from_dict(
        {"name": "g", "tasks": [{"id": "task_a", "description": "first"}]}
    )
    probe = GraphProbe(
        task_probes={
            "task_a": _make_task_probe("task_a", resolved=False, status="failed")
        },
        workstream_probes={
            ws_id: _make_ws_probe(ws_id) for ws_id in graph.workstream_ids()
        },
    )
    task_rts, _ = _build_resume_runtimes(graph, probe, tmp_path)

    rt = task_rts["task_a"]
    assert rt.state.signal_dir is None
    assert rt.status == TaskStatus.PENDING
