"""Tests for reset_graph module — plan/execute reset and CLI."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from agentrelay.ops import git, signals
from agentrelay.reset_graph import (
    _load_run_info,
    execute_reset,
    plan_reset,
)


def _git(args: list[str]) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True)


# --- _load_run_info ---


def test_load_run_info_reads_file(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".workflow" / "test"
    workflow_dir.mkdir(parents=True)
    info = {"start_head": "abc123", "started_at": "2026-03-18T00:00:00Z"}
    (workflow_dir / "run_info.json").write_text(json.dumps(info))

    result = _load_run_info(workflow_dir)
    assert result["start_head"] == "abc123"
    assert result["started_at"] == "2026-03-18T00:00:00Z"


def test_load_run_info_raises_on_missing(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".workflow" / "test"
    with pytest.raises(FileNotFoundError, match="run_info.json"):
        _load_run_info(workflow_dir)


# --- plan_reset (with temp git repo) ---


@pytest.fixture
def reset_repo(tmp_path: Path) -> Path:
    """Create a git repo with a remote, simulate a graph run."""
    bare = tmp_path / "remote.git"
    _git(["init", "--bare", "-b", "main", str(bare)])

    clone = tmp_path / "clone"
    _git(["clone", str(bare), str(clone)])
    _git(["-C", str(clone), "config", "user.email", "test@test.com"])
    _git(["-C", str(clone), "config", "user.name", "Test"])

    (clone / "README.md").write_text("# test\n")
    _git(["-C", str(clone), "add", "README.md"])
    _git(["-C", str(clone), "commit", "-m", "initial"])
    _git(["-C", str(clone), "push", "-u", "origin", "main"])

    # Record start HEAD.
    start_head = git.rev_parse_head(clone)
    workflow_dir = clone / ".workflow" / "test-graph"
    signals.write_json(
        workflow_dir,
        "run_info.json",
        {"start_head": start_head, "started_at": "2026-03-18T00:00:00Z"},
    )

    # Simulate graph work: create a branch and push it.
    _git(["-C", str(clone), "checkout", "-b", "agentrelay/test-graph/task_a"])
    (clone / "task_a.txt").write_text("work\n")
    _git(["-C", str(clone), "add", "task_a.txt"])
    _git(["-C", str(clone), "commit", "-m", "task_a work"])
    _git(["-C", str(clone), "push", "-u", "origin", "agentrelay/test-graph/task_a"])

    # Create integration branch.
    _git(["-C", str(clone), "checkout", "main"])
    _git(
        [
            "-C",
            str(clone),
            "checkout",
            "-b",
            "agentrelay/test-graph/default/integration",
        ]
    )
    _git(
        [
            "-C",
            str(clone),
            "push",
            "-u",
            "origin",
            "agentrelay/test-graph/default/integration",
        ]
    )
    _git(["-C", str(clone), "checkout", "main"])

    # Simulate worktree directory.
    worktree_dir = clone / ".worktrees" / "test-graph" / "default"
    worktree_dir.mkdir(parents=True)
    (worktree_dir / "placeholder").write_text("")

    return clone


def test_plan_reset_discovers_branches(reset_repo: Path) -> None:
    with patch("agentrelay.reset_graph.gh.pr_list", return_value=[]):
        plan = plan_reset("test-graph", reset_repo)

    assert plan.graph_name == "test-graph"
    assert plan.can_reset_main is True
    assert len(plan.remote_branches) == 2
    branch_names = sorted(plan.remote_branches)
    assert "agentrelay/test-graph/default/integration" in branch_names
    assert "agentrelay/test-graph/task_a" in branch_names


def test_plan_reset_detects_out_of_order(reset_repo: Path) -> None:
    # Add a commit after the recorded start_head to simulate another graph run.
    (reset_repo / "extra.txt").write_text("extra\n")
    _git(["-C", str(reset_repo), "add", "extra.txt"])
    _git(["-C", str(reset_repo), "commit", "-m", "extra"])
    _git(["-C", str(reset_repo), "push", "origin", "main"])

    # Now tamper with run_info to use the CURRENT head as start (making it "ahead").
    # This simulates resetting an older graph while newer commits exist.
    current_head = git.rev_parse_head(reset_repo)

    # Reset main back one commit to make start_head ahead of HEAD.
    _git(["-C", str(reset_repo), "reset", "--hard", "HEAD~1"])

    workflow_dir = reset_repo / ".workflow" / "test-graph"
    signals.write_json(
        workflow_dir,
        "run_info.json",
        {"start_head": current_head, "started_at": "2026-03-18T00:00:00Z"},
    )

    with patch("agentrelay.reset_graph.gh.pr_list", return_value=[]):
        plan = plan_reset("test-graph", reset_repo)

    assert plan.can_reset_main is False
    assert any("not an ancestor" in msg for msg in plan.log)


# --- execute_reset ---


def test_execute_reset_deletes_branches(reset_repo: Path) -> None:
    with patch("agentrelay.reset_graph.gh.pr_list", return_value=[]):
        plan = plan_reset("test-graph", reset_repo)

    log = execute_reset(plan)

    # Remote branches should be gone.
    remaining = git.ls_remote_branches(reset_repo, "refs/heads/agentrelay/test-graph/*")
    assert remaining == []

    # Worktree dir should be gone.
    assert not (reset_repo / ".worktrees" / "test-graph").exists()

    # Workflow dir should be gone.
    assert not (reset_repo / ".workflow" / "test-graph").exists()

    assert any("Deleted remote branch" in msg for msg in log)
    assert any("Removed worktree directory" in msg for msg in log)
    assert any("Removed workflow directory" in msg for msg in log)


def test_execute_reset_closes_prs(reset_repo: Path) -> None:
    fake_prs = [
        {"number": 42, "headRefName": "agentrelay/test-graph/task_a"},
    ]
    with patch("agentrelay.reset_graph.gh.pr_list", return_value=fake_prs):
        plan = plan_reset("test-graph", reset_repo)

    with patch("agentrelay.reset_graph.gh.pr_close") as mock_close:
        log = execute_reset(plan)

    mock_close.assert_called_once_with(reset_repo, 42)
    assert any("Closed PR #42" in msg for msg in log)


def test_execute_reset_resets_main(reset_repo: Path) -> None:
    # Record the start head.
    workflow_dir = reset_repo / ".workflow" / "test-graph"
    run_info = json.loads((workflow_dir / "run_info.json").read_text())
    start_head = run_info["start_head"]

    # Add a commit to main after start_head.
    (reset_repo / "new_file.txt").write_text("new\n")
    _git(["-C", str(reset_repo), "add", "new_file.txt"])
    _git(["-C", str(reset_repo), "commit", "-m", "new work"])
    _git(["-C", str(reset_repo), "push", "origin", "main"])

    with patch("agentrelay.reset_graph.gh.pr_list", return_value=[]):
        plan = plan_reset("test-graph", reset_repo)

    log = execute_reset(plan)

    current_head = git.rev_parse_head(reset_repo)
    assert current_head == start_head
    assert any("Reset main" in msg for msg in log)


def test_execute_reset_skips_main_when_out_of_order(reset_repo: Path) -> None:
    current_head = git.rev_parse_head(reset_repo)

    # Make start_head ahead of HEAD.
    (reset_repo / "extra.txt").write_text("extra\n")
    _git(["-C", str(reset_repo), "add", "extra.txt"])
    _git(["-C", str(reset_repo), "commit", "-m", "extra"])
    ahead_head = git.rev_parse_head(reset_repo)
    _git(["-C", str(reset_repo), "push", "origin", "main"])
    _git(["-C", str(reset_repo), "reset", "--hard", current_head])

    workflow_dir = reset_repo / ".workflow" / "test-graph"
    signals.write_json(
        workflow_dir,
        "run_info.json",
        {"start_head": ahead_head, "started_at": "2026-03-18T00:00:00Z"},
    )

    with patch("agentrelay.reset_graph.gh.pr_list", return_value=[]):
        plan = plan_reset("test-graph", reset_repo)

    assert plan.can_reset_main is False
    log = execute_reset(plan)

    # HEAD should NOT have changed.
    assert git.rev_parse_head(reset_repo) == current_head
    assert any("Skipped main-branch reset" in msg for msg in log)

    # But cleanup should still happen.
    assert not (reset_repo / ".worktrees" / "test-graph").exists()
    assert not (reset_repo / ".workflow" / "test-graph").exists()


def test_execute_reset_prunes_worktrees(reset_repo: Path) -> None:
    """Worktree prune runs after directory removal."""
    with patch("agentrelay.reset_graph.gh.pr_list", return_value=[]):
        plan = plan_reset("test-graph", reset_repo)

    log = execute_reset(plan)

    assert any("Pruned stale git worktree references" in msg for msg in log)


def test_execute_reset_deletes_local_branches(reset_repo: Path) -> None:
    """Local branches matching the graph prefix are deleted."""
    # The fixture creates agentrelay/test-graph/task_a and
    # agentrelay/test-graph/default/integration as local branches.
    with patch("agentrelay.reset_graph.gh.pr_list", return_value=[]):
        plan = plan_reset("test-graph", reset_repo)

    log = execute_reset(plan)

    assert any("Deleted local branch" in msg for msg in log)

    # No local branches with the graph prefix should remain.
    from agentrelay.ops.git import branch_list_local

    remaining = branch_list_local(reset_repo, "agentrelay/test-graph/*")
    assert remaining == []


def test_execute_reset_idempotent(reset_repo: Path) -> None:
    """Running reset twice doesn't error."""
    with patch("agentrelay.reset_graph.gh.pr_list", return_value=[]):
        plan1 = plan_reset("test-graph", reset_repo)
    execute_reset(plan1)

    # Second reset: run_info.json is gone, so plan_reset should fail cleanly.
    with pytest.raises(FileNotFoundError, match="run_info.json"):
        plan_reset("test-graph", reset_repo)


# --- run_info.json integration with run_graph ---


def test_run_graph_writes_run_info(tmp_git_repo: Path) -> None:
    """run_graph's _record_run_start writes run_info.json."""
    from agentrelay.run_graph import _record_run_start

    _record_run_start(tmp_git_repo, "my-graph")

    run_info_path = tmp_git_repo / ".workflow" / "my-graph" / "run_info.json"
    assert run_info_path.is_file()

    info = json.loads(run_info_path.read_text())
    assert "start_head" in info
    assert "started_at" in info
    assert len(info["start_head"]) == 40  # Full SHA


# --- Docker cleanup in execute_reset ---


def test_execute_reset_cleans_docker_containers(reset_repo: Path) -> None:
    """Docker containers matching graph label are stopped and removed."""
    with patch("agentrelay.reset_graph.gh.pr_list", return_value=[]):
        plan = plan_reset("test-graph", reset_repo)

    with (patch("agentrelay.reset_graph.docker_ops") as mock_docker,):
        mock_docker.ps_by_label.return_value = [
            "agentrelay-test-graph-task_a",
            "agentrelay-test-graph-task_b",
        ]
        mock_docker.network_exists.return_value = False
        log = execute_reset(plan)

    mock_docker.ps_by_label.assert_called_once_with("agentrelay.graph=test-graph")
    assert mock_docker.force_rm.call_count == 2
    assert any("2 Docker container(s)" in msg for msg in log)


def test_execute_reset_removes_docker_network(reset_repo: Path) -> None:
    """Docker network matching graph name is removed."""
    with patch("agentrelay.reset_graph.gh.pr_list", return_value=[]):
        plan = plan_reset("test-graph", reset_repo)

    with (patch("agentrelay.reset_graph.docker_ops") as mock_docker,):
        mock_docker.ps_by_label.return_value = []
        mock_docker.network_exists.return_value = True
        log = execute_reset(plan)

    mock_docker.network_remove.assert_called_once_with("agentrelay-test-graph")
    assert any("Removed Docker network" in msg for msg in log)


def test_execute_reset_swallows_docker_errors(reset_repo: Path) -> None:
    """Reset completes even if Docker operations fail."""
    with patch("agentrelay.reset_graph.gh.pr_list", return_value=[]):
        plan = plan_reset("test-graph", reset_repo)

    with (patch("agentrelay.reset_graph.docker_ops") as mock_docker,):
        mock_docker.ps_by_label.side_effect = subprocess.CalledProcessError(1, "docker")
        mock_docker.network_exists.side_effect = subprocess.CalledProcessError(
            1, "docker"
        )
        log = execute_reset(plan)

    # Non-Docker steps should still execute.
    assert any("Removed worktree directory" in msg for msg in log)
    assert any("Removed workflow directory" in msg for msg in log)


def test_execute_reset_handles_no_docker(reset_repo: Path) -> None:
    """Reset completes even if Docker is not installed."""
    with patch("agentrelay.reset_graph.gh.pr_list", return_value=[]):
        plan = plan_reset("test-graph", reset_repo)

    with (patch("agentrelay.reset_graph.docker_ops") as mock_docker,):
        mock_docker.ps_by_label.side_effect = FileNotFoundError("docker")
        mock_docker.network_exists.side_effect = FileNotFoundError("docker")
        log = execute_reset(plan)

    # Non-Docker steps should still execute.
    assert any("Removed worktree directory" in msg for msg in log)
    assert any("Removed workflow directory" in msg for msg in log)
