"""Unit tests for run_graph module — YAML pre-processing, dry-run, and builder."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentrelay.orchestrator import OrchestratorConfig
from agentrelay.orchestrator.builders import build_standard_workstream_runner
from agentrelay.run_graph import (
    _any_task_uses_oci,
    _apply_overrides,
    _build_parser,
    _copy_graph_yaml,
    _extract_operational_config,
    _load_and_prepare_graph,
    _resolve_fail_fast,
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
    session, keep, model, tools, anthropic, fail_fast, fail_fast_internal = (
        _extract_operational_config(raw)
    )
    assert session is None
    assert keep is False
    assert model is None
    assert tools == ()
    assert anthropic is None
    assert fail_fast is None
    assert fail_fast_internal is None


def test_extract_operational_config_reads_yaml_values() -> None:
    raw: dict = {
        "name": "g",
        "tasks": [],
        "tmux_session": "custom",
        "keep_panes": True,
        "model": "claude-opus-4-6",
    }
    session, keep, model, tools, _, _, _ = _extract_operational_config(raw)
    assert session == "custom"
    assert keep is True
    assert model == "claude-opus-4-6"
    assert tools == ()


def test_extract_operational_config_pops_keys() -> None:
    raw: dict = {
        "name": "g",
        "tasks": [],
        "tmux_session": "x",
        "keep_panes": True,
        "model": "m",
        "tools": ["pixi"],
        "anthropic_credential": "max_plan",
        "fail_fast_on_workstream_error": True,
        "fail_fast_on_internal_error": False,
    }
    _extract_operational_config(raw)
    assert "tmux_session" not in raw
    assert "keep_panes" not in raw
    assert "model" not in raw
    assert "tools" not in raw
    assert "anthropic_credential" not in raw
    assert "fail_fast_on_workstream_error" not in raw
    assert "fail_fast_on_internal_error" not in raw
    assert "name" in raw


def test_extract_operational_config_parses_tools() -> None:
    raw: dict = {"name": "g", "tasks": [], "tools": ["pixi", "npm"]}
    _, _, _, tools, _, _, _ = _extract_operational_config(raw)
    assert tools == ("pixi", "npm")
    assert "tasks" in raw


def test_extract_operational_config_reads_anthropic_credential() -> None:
    raw: dict = {"name": "g", "tasks": [], "anthropic_credential": "max_plan"}
    _, _, _, _, anthropic, _, _ = _extract_operational_config(raw)
    assert anthropic == "max_plan"


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
tmux_session: my-session
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
    runner = build_standard_workstream_runner(
        repo_path=tmp_path,
        graph_name="test-graph",
    )
    assert isinstance(runner._preparer, GitWorkstreamPreparer)
    assert isinstance(runner._integrator, GhWorkstreamIntegrator)
    assert isinstance(runner._teardown, GitWorkstreamTeardown)


def test_build_standard_workstream_runner_preparer_config(tmp_path: Path) -> None:
    runner = build_standard_workstream_runner(
        repo_path=tmp_path,
        graph_name="my-graph",
    )
    preparer = runner._preparer
    assert isinstance(preparer, GitWorkstreamPreparer)
    assert preparer.repo_path == tmp_path
    assert preparer.graph_name == "my-graph"


def test_build_standard_workstream_runner_integrator_config(tmp_path: Path) -> None:
    runner = build_standard_workstream_runner(
        repo_path=tmp_path,
        graph_name="my-graph",
    )
    integrator = runner._integrator
    assert isinstance(integrator, GhWorkstreamIntegrator)
    assert integrator.repo_path == tmp_path


def test_build_standard_workstream_runner_teardown_config(tmp_path: Path) -> None:
    runner = build_standard_workstream_runner(
        repo_path=tmp_path,
        graph_name="my-graph",
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
    graph, _, _, _, _, _, _ = _load_and_prepare_graph(path)
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
    graph, _, _, _, _, _, _ = _load_and_prepare_graph(path)
    assert _any_task_uses_oci(graph) is False


# --- _copy_graph_yaml ---


def test_copy_graph_yaml_writes_file(tmp_path: Path) -> None:
    """graph.yaml is written to .workflow/<graph>/ with identical bytes."""
    source = tmp_path / "my-graph.yaml"
    source.write_text("name: my-graph\ntasks:\n  - id: a\n    description: do stuff\n")

    workflow_dir = tmp_path / ".workflow" / "my-graph"
    workflow_dir.mkdir(parents=True)

    _copy_graph_yaml(tmp_path, "my-graph", source)

    dest = workflow_dir / "graph.yaml"
    assert dest.is_file()
    assert dest.read_bytes() == source.read_bytes()


def test_copy_graph_yaml_preserves_comments(tmp_path: Path) -> None:
    """YAML comments and formatting are preserved byte-for-byte."""
    content = "# This is a comment\nname: test  # inline comment\ntasks:\n  - id: a\n    description: task\n    dependencies: []\n"
    source = tmp_path / "graph.yaml"
    source.write_text(content)

    workflow_dir = tmp_path / ".workflow" / "test"
    workflow_dir.mkdir(parents=True)

    _copy_graph_yaml(tmp_path, "test", source)

    dest = workflow_dir / "graph.yaml"
    assert dest.read_text() == content


# --- docker_build.sh syntax ---


# --- _extract_operational_config: fail_fast_on_workstream_error ---


def test_extract_operational_config_fail_fast_true() -> None:
    raw: dict = {"name": "g", "tasks": [], "fail_fast_on_workstream_error": True}
    _, _, _, _, _, fail_fast, _ = _extract_operational_config(raw)
    assert fail_fast is True


def test_extract_operational_config_fail_fast_false() -> None:
    raw: dict = {"name": "g", "tasks": [], "fail_fast_on_workstream_error": False}
    _, _, _, _, _, fail_fast, _ = _extract_operational_config(raw)
    assert fail_fast is False


def test_extract_operational_config_fail_fast_default_is_none() -> None:
    raw: dict = {"name": "g", "tasks": []}
    _, _, _, _, _, fail_fast, _ = _extract_operational_config(raw)
    assert fail_fast is None


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
    _, _, _, _, _, _, fail_fast_internal = _extract_operational_config(raw)
    assert fail_fast_internal is True


def test_extract_operational_config_fail_fast_internal_false() -> None:
    raw: dict = {"name": "g", "tasks": [], "fail_fast_on_internal_error": False}
    _, _, _, _, _, _, fail_fast_internal = _extract_operational_config(raw)
    assert fail_fast_internal is False


def test_extract_operational_config_fail_fast_internal_default_is_none() -> None:
    raw: dict = {"name": "g", "tasks": []}
    _, _, _, _, _, _, fail_fast_internal = _extract_operational_config(raw)
    assert fail_fast_internal is None


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
    assert args.fail_fast_on_workstream_error is None


def test_cli_parser_fail_fast_true() -> None:
    parser = _build_parser()
    args = parser.parse_args(["graph.yaml", "--fail-fast-on-workstream-error"])
    assert args.fail_fast_on_workstream_error is True


def test_cli_parser_fail_fast_false() -> None:
    parser = _build_parser()
    args = parser.parse_args(["graph.yaml", "--no-fail-fast-on-workstream-error"])
    assert args.fail_fast_on_workstream_error is False


def test_cli_parser_fail_fast_internal_default_none() -> None:
    parser = _build_parser()
    args = parser.parse_args(["graph.yaml"])
    assert args.fail_fast_on_internal_error is None


def test_cli_parser_fail_fast_internal_true() -> None:
    parser = _build_parser()
    args = parser.parse_args(["graph.yaml", "--fail-fast-on-internal-error"])
    assert args.fail_fast_on_internal_error is True


def test_cli_parser_fail_fast_internal_false() -> None:
    parser = _build_parser()
    args = parser.parse_args(["graph.yaml", "--no-fail-fast-on-internal-error"])
    assert args.fail_fast_on_internal_error is False


# --- _resolve_fail_fast ---


def test_resolve_fail_fast_cli_overrides_yaml() -> None:
    assert _resolve_fail_fast(cli_value=False, yaml_value=True) is False
    assert _resolve_fail_fast(cli_value=True, yaml_value=False) is True


def test_resolve_fail_fast_yaml_used_when_cli_none() -> None:
    assert _resolve_fail_fast(cli_value=None, yaml_value=True) is True
    assert _resolve_fail_fast(cli_value=None, yaml_value=False) is False


def test_resolve_fail_fast_none_when_both_none() -> None:
    assert _resolve_fail_fast(cli_value=None, yaml_value=None) is None


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
