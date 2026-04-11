"""Tests for TaskHelper agent-side workflow helper."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from agentrelay.agent_sdk.output_manifest import OutputAction
from agentrelay.agent_sdk.task_helper import NO_PR_SENTINEL, TaskHelper


def _gh_side_effect(
    *,
    list_url: str = "",
    create_url: str = "https://github.com/org/repo/pull/42",
) -> object:
    """Return a side_effect callable for subprocess.run that routes by gh subcommand."""

    def _side_effect(
        args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        # gh pr list / gh pr create → args[1]="pr", args[2]="list"/"create"
        # gh api repos/... → args[1]="api"
        if len(args) > 2 and args[1] == "pr":
            subcmd = args[2]
            if subcmd == "list":
                return subprocess.CompletedProcess(
                    args, 0, stdout=list_url + "\n", stderr=""
                )
            if subcmd == "create":
                return subprocess.CompletedProcess(
                    args, 0, stdout=create_url + "\n", stderr=""
                )
        if args[1] == "api":
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        raise ValueError(f"Unexpected gh command: {args}")

    return _side_effect


def _write_manifest(signal_dir: Path, **overrides: object) -> None:
    """Write a minimal manifest.json for testing."""
    manifest = {
        "schema_version": "1",
        "task": {"id": "test_task", "role": "generic", "description": None},
        "paths": {"src": [], "test": [], "spec": None},
        "workspace": {
            "branch_name": "agentrelay/graph/test_task",
            "integration_branch": "agentrelay/graph/default/integration",
        },
        "execution": {"attempt_num": 0, "graph_name": "test-graph"},
        "dependencies": {},
    }
    # Apply overrides to nested keys.
    for key, value in overrides.items():
        if "." in key:
            section, field = key.split(".", 1)
            manifest[section][field] = value
        else:
            manifest[key] = value
    signal_dir.mkdir(parents=True, exist_ok=True)
    (signal_dir / "manifest.json").write_text(json.dumps(manifest))


# -- Construction --


def test_from_env_reads_manifest(tmp_path: Path) -> None:
    signal_dir = tmp_path / "signals"
    _write_manifest(signal_dir)

    with patch.dict("os.environ", {"AGENTRELAY_SIGNAL_DIR": str(signal_dir)}):
        helper = TaskHelper.from_env()

    assert helper.signal_dir == signal_dir
    assert helper.task_id == "test_task"
    assert helper.branch_name == "agentrelay/graph/test_task"
    assert helper.integration_branch == "agentrelay/graph/default/integration"


def test_from_env_missing_env_var() -> None:
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(KeyError):
            TaskHelper.from_env()


def test_from_env_missing_manifest(tmp_path: Path) -> None:
    signal_dir = tmp_path / "signals"
    signal_dir.mkdir(parents=True)

    with patch.dict("os.environ", {"AGENTRELAY_SIGNAL_DIR": str(signal_dir)}):
        with pytest.raises(FileNotFoundError):
            TaskHelper.from_env()


# -- Signal files --


def test_mark_done_writes_signal(tmp_path: Path) -> None:
    helper = TaskHelper(
        signal_dir=tmp_path,
        task_id="t",
        branch_name="b",
        integration_branch="i",
    )
    helper.mark_done("https://github.com/org/repo/pull/1")

    content = (tmp_path / "attempts" / "0" / ".done").read_text()
    lines = content.strip().splitlines()
    assert len(lines) == 2
    assert lines[1] == "https://github.com/org/repo/pull/1"


def test_mark_failed_writes_signal(tmp_path: Path) -> None:
    helper = TaskHelper(
        signal_dir=tmp_path,
        task_id="t",
        branch_name="b",
        integration_branch="i",
    )
    helper.mark_failed("could not compile")

    content = (tmp_path / "attempts" / "0" / ".failed").read_text()
    lines = content.strip().splitlines()
    assert len(lines) == 2
    assert lines[1] == "could not compile"


# -- Concerns --


def test_record_concern_appends_to_file(tmp_path: Path) -> None:
    helper = TaskHelper(
        signal_dir=tmp_path,
        task_id="t",
        branch_name="b",
        integration_branch="i",
    )
    helper.record_concern("naming could be clearer")
    helper.record_concern("missing edge case")

    content = (tmp_path / "attempts" / "0" / "concerns.log").read_text()
    lines = content.strip().splitlines()
    assert lines == ["naming could be clearer", "missing edge case"]


def test_record_ops_concern_appends_to_file(tmp_path: Path) -> None:
    helper = TaskHelper(
        signal_dir=tmp_path,
        task_id="t",
        branch_name="b",
        integration_branch="i",
    )
    helper.record_ops_concern("pixi install took >30s")
    helper.record_ops_concern("pyright flagged unrelated warnings")

    content = (tmp_path / "attempts" / "0" / "ops_concerns.log").read_text()
    lines = content.strip().splitlines()
    assert lines == ["pixi install took >30s", "pyright flagged unrelated warnings"]


# -- Summary --


def test_write_summary_creates_file(tmp_path: Path) -> None:
    helper = TaskHelper(
        signal_dir=tmp_path,
        task_id="t",
        branch_name="b",
        integration_branch="i",
    )
    helper.write_summary("## Summary\n\n- reviewed all tests")
    assert (
        tmp_path / "attempts" / "0" / "summary.md"
    ).read_text() == "## Summary\n\n- reviewed all tests"


def test_write_summary_overwrites_existing(tmp_path: Path) -> None:
    helper = TaskHelper(
        signal_dir=tmp_path,
        task_id="t",
        branch_name="b",
        integration_branch="i",
    )
    helper.write_summary("first draft")
    helper.write_summary("final summary")
    assert (tmp_path / "attempts" / "0" / "summary.md").read_text() == "final summary"


# -- Output declarations --


def test_declare_output_creates_outputs_json(tmp_path: Path) -> None:
    helper = TaskHelper(
        signal_dir=tmp_path,
        task_id="t",
        branch_name="b",
        integration_branch="i",
    )
    helper.declare_output(Path("src/foo.py"), OutputAction.CREATED, "stubs")

    data = json.loads((tmp_path / "outputs.json").read_text())
    assert data["schema_version"] == "1"
    assert len(data["files"]) == 1
    assert data["files"][0] == {
        "path": "src/foo.py",
        "action": "created",
        "category": "stubs",
    }


def test_declare_output_appends(tmp_path: Path) -> None:
    helper = TaskHelper(
        signal_dir=tmp_path,
        task_id="t",
        branch_name="b",
        integration_branch="i",
    )
    helper.declare_output(Path("src/foo.py"), OutputAction.CREATED, "stubs")
    helper.declare_output(Path("src/bar.py"), OutputAction.MODIFIED, "implementation")

    data = json.loads((tmp_path / "outputs.json").read_text())
    assert len(data["files"]) == 2
    assert data["files"][0]["path"] == "src/foo.py"
    assert data["files"][1]["path"] == "src/bar.py"


def test_declare_output_preserves_existing(tmp_path: Path) -> None:
    # Pre-populate outputs.json with an existing entry.
    (tmp_path / "outputs.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "files": [{"path": "old.py", "action": "created", "category": "other"}],
            }
        )
    )
    helper = TaskHelper(
        signal_dir=tmp_path,
        task_id="t",
        branch_name="b",
        integration_branch="i",
    )
    helper.declare_output(Path("new.py"), OutputAction.CREATED, "stubs")

    data = json.loads((tmp_path / "outputs.json").read_text())
    assert len(data["files"]) == 2
    assert data["files"][0]["path"] == "old.py"
    assert data["files"][1]["path"] == "new.py"


def test_declare_output_all_actions(tmp_path: Path) -> None:
    helper = TaskHelper(
        signal_dir=tmp_path,
        task_id="t",
        branch_name="b",
        integration_branch="i",
    )
    helper.declare_output(Path("a.py"), OutputAction.CREATED, "stubs")
    helper.declare_output(Path("b.py"), OutputAction.MODIFIED, "implementation")
    helper.declare_output(Path("c.py"), OutputAction.DELETED, "other")

    data = json.loads((tmp_path / "outputs.json").read_text())
    assert len(data["files"]) == 3
    assert data["files"][0]["action"] == "created"
    assert data["files"][1]["action"] == "modified"
    assert data["files"][2]["action"] == "deleted"


# -- PR creation --


def test_create_pr_includes_ops_concerns_in_body(tmp_path: Path) -> None:
    helper = TaskHelper(
        signal_dir=tmp_path,
        task_id="my_task",
        branch_name="agentrelay/g/my_task",
        integration_branch="agentrelay/g/default/integration",
    )
    helper.record_ops_concern("slow build")

    with patch("agentrelay.agent_sdk.task_helper.subprocess.run") as mock_run:
        mock_run.side_effect = _gh_side_effect()
        helper.create_pr(body="task body")

    # The create call is the second call (after the probe).
    create_args = mock_run.call_args_list[1][0][0]
    body_idx = create_args.index("--body")
    body = create_args[body_idx + 1]
    assert "## Ops Concerns" in body
    assert "slow build" in body


def test_create_pr_includes_both_concern_types(tmp_path: Path) -> None:
    helper = TaskHelper(
        signal_dir=tmp_path,
        task_id="my_task",
        branch_name="agentrelay/g/my_task",
        integration_branch="agentrelay/g/default/integration",
    )
    helper.record_concern("spec ambiguity")
    helper.record_ops_concern("missing dep")

    with patch("agentrelay.agent_sdk.task_helper.subprocess.run") as mock_run:
        mock_run.side_effect = _gh_side_effect()
        helper.create_pr(body="task body")

    create_args = mock_run.call_args_list[1][0][0]
    body_idx = create_args.index("--body")
    body = create_args[body_idx + 1]
    assert "## Concerns" in body
    assert "spec ambiguity" in body
    assert "## Ops Concerns" in body
    assert "missing dep" in body


def test_create_pr_calls_gh(tmp_path: Path) -> None:
    helper = TaskHelper(
        signal_dir=tmp_path,
        task_id="my_task",
        branch_name="agentrelay/g/my_task",
        integration_branch="agentrelay/g/default/integration",
    )

    with patch("agentrelay.agent_sdk.task_helper.subprocess.run") as mock_run:
        mock_run.side_effect = _gh_side_effect()
        pr_url = helper.create_pr()

    assert pr_url == "https://github.com/org/repo/pull/42"
    assert mock_run.call_count == 2  # probe + create
    create_args = mock_run.call_args_list[1][0][0]
    assert create_args[0] == "gh"
    assert "--base" in create_args
    base_idx = create_args.index("--base")
    assert create_args[base_idx + 1] == "agentrelay/g/default/integration"
    head_idx = create_args.index("--head")
    assert create_args[head_idx + 1] == "agentrelay/g/my_task"


# -- Complete (combined workflow) --


def test_complete_without_pr_writes_no_pr_sentinel(tmp_path: Path) -> None:
    helper = TaskHelper(
        signal_dir=tmp_path,
        task_id="t",
        branch_name="b",
        integration_branch="i",
    )
    helper.complete_without_pr()

    content = (tmp_path / "attempts" / "0" / ".done").read_text()
    lines = content.strip().splitlines()
    assert len(lines) == 2
    assert lines[1] == NO_PR_SENTINEL


def test_complete_creates_pr_and_signals_done(tmp_path: Path) -> None:
    helper = TaskHelper(
        signal_dir=tmp_path,
        task_id="t",
        branch_name="b",
        integration_branch="i",
    )

    with patch.object(helper, "create_pr", return_value="https://example.com/pr/1"):
        helper.complete()

    content = (tmp_path / "attempts" / "0" / ".done").read_text()
    assert "https://example.com/pr/1" in content


# -- PR reuse on retry --


def test_create_pr_no_existing_pr_probes_then_creates(tmp_path: Path) -> None:
    """When no open PR exists, probe returns empty and gh pr create runs."""
    helper = TaskHelper(
        signal_dir=tmp_path,
        task_id="my_task",
        branch_name="agentrelay/g/my_task",
        integration_branch="agentrelay/g/default/integration",
    )

    with patch("agentrelay.agent_sdk.task_helper.subprocess.run") as mock_run:
        mock_run.side_effect = _gh_side_effect()
        pr_url = helper.create_pr()

    assert pr_url == "https://github.com/org/repo/pull/42"
    assert mock_run.call_count == 2
    probe_args = mock_run.call_args_list[0][0][0]
    assert probe_args[2] == "list"
    create_args = mock_run.call_args_list[1][0][0]
    assert create_args[2] == "create"


def test_create_pr_reuses_existing_pr(tmp_path: Path) -> None:
    """When an open PR exists, it is reused and gh pr create is not called."""
    helper = TaskHelper(
        signal_dir=tmp_path,
        task_id="my_task",
        branch_name="agentrelay/g/my_task",
        integration_branch="agentrelay/g/default/integration",
    )

    existing = "https://github.com/org/repo/pull/7"
    with patch("agentrelay.agent_sdk.task_helper.subprocess.run") as mock_run:
        mock_run.side_effect = _gh_side_effect(list_url=existing)
        pr_url = helper.create_pr()

    assert pr_url == existing
    assert mock_run.call_count == 2  # probe + api PATCH (no create)
    probe_args = mock_run.call_args_list[0][0][0]
    assert probe_args[2] == "list"
    api_args = mock_run.call_args_list[1][0][0]
    assert api_args[1] == "api"
    assert "repos/org/repo/pulls/7" in api_args


def test_create_pr_reuse_updates_body_with_concerns(tmp_path: Path) -> None:
    """When reusing a PR, the body passed to gh api PATCH includes concerns."""
    helper = TaskHelper(
        signal_dir=tmp_path,
        task_id="my_task",
        branch_name="agentrelay/g/my_task",
        integration_branch="agentrelay/g/default/integration",
    )
    helper.record_concern("retry concern")
    helper.record_ops_concern("retry ops issue")

    existing = "https://github.com/org/repo/pull/7"
    with patch("agentrelay.agent_sdk.task_helper.subprocess.run") as mock_run:
        mock_run.side_effect = _gh_side_effect(list_url=existing)
        helper.create_pr(body="attempt 2 body")

    api_args = mock_run.call_args_list[1][0][0]
    # Body is passed as "-f" "body=..." to gh api
    body_flag_indices = [i for i, a in enumerate(api_args) if a == "-f"]
    body_values = [
        api_args[i + 1]
        for i in body_flag_indices
        if api_args[i + 1].startswith("body=")
    ]
    assert len(body_values) == 1
    body = body_values[0].removeprefix("body=")
    assert "attempt 2 body" in body
    assert "## Concerns" in body
    assert "retry concern" in body
    assert "## Ops Concerns" in body
    assert "retry ops issue" in body
