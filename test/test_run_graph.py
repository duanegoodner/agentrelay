"""Unit tests for run_graph module — YAML pre-processing, dry-run, and builder."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentrelay.orchestrator.builders import build_standard_workstream_runner
from agentrelay.run_graph import (
    _apply_overrides,
    _extract_operational_config,
    dry_run,
)
from agentrelay.workstream.implementations.workstream_merger import GhWorkstreamMerger
from agentrelay.workstream.implementations.workstream_preparer import (
    GitWorkstreamPreparer,
)
from agentrelay.workstream.implementations.workstream_teardown import (
    GitWorkstreamTeardown,
)

# --- _extract_operational_config ---


def test_extract_operational_config_defaults() -> None:
    raw: dict = {"name": "g", "tasks": []}
    session, keep, model = _extract_operational_config(raw)
    assert session == "agentrelay"
    assert keep is False
    assert model is None


def test_extract_operational_config_reads_yaml_values() -> None:
    raw: dict = {
        "name": "g",
        "tasks": [],
        "tmux_session": "custom",
        "keep_panes": True,
        "model": "claude-opus-4-6",
    }
    session, keep, model = _extract_operational_config(raw)
    assert session == "custom"
    assert keep is True
    assert model == "claude-opus-4-6"


def test_extract_operational_config_pops_keys() -> None:
    raw: dict = {
        "name": "g",
        "tasks": [],
        "tmux_session": "x",
        "keep_panes": True,
        "model": "m",
    }
    _extract_operational_config(raw)
    assert "tmux_session" not in raw
    assert "keep_panes" not in raw
    assert "model" not in raw
    assert "name" in raw
    assert "tasks" in raw


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
    assert isinstance(runner._merger, GhWorkstreamMerger)
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


def test_build_standard_workstream_runner_merger_config(tmp_path: Path) -> None:
    runner = build_standard_workstream_runner(
        repo_path=tmp_path,
        graph_name="my-graph",
    )
    merger = runner._merger
    assert isinstance(merger, GhWorkstreamMerger)
    assert merger.repo_path == tmp_path


def test_build_standard_workstream_runner_teardown_config(tmp_path: Path) -> None:
    runner = build_standard_workstream_runner(
        repo_path=tmp_path,
        graph_name="my-graph",
    )
    teardown = runner._teardown
    assert isinstance(teardown, GitWorkstreamTeardown)
    assert teardown.repo_path == tmp_path
