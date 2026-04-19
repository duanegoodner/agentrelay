"""Tests for reset_workstream module — teardown and workstream-level undo."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from agentrelay.ops import git
from agentrelay.reset_workstream import reset_workstream, teardown_workstream
from agentrelay.task import AgentConfig, AgentRole, Task
from agentrelay.task_graph import TaskGraph
from agentrelay.workstream import WorkstreamSpec


def _git(args: list[str]) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True)


# ── Fixtures ──


@pytest.fixture
def single_ws_graph() -> TaskGraph:
    """Graph with 2 tasks in 1 workstream: task_a -> task_b."""
    tasks = [
        Task(
            id="task_a",
            description="Task A",
            workstream_id="ws-a",
            role=AgentRole.GENERIC,
            primary_agent=AgentConfig(),
        ),
        Task(
            id="task_b",
            description="Task B",
            workstream_id="ws-a",
            role=AgentRole.GENERIC,
            primary_agent=AgentConfig(),
            dependencies=("task_a",),
        ),
    ]
    workstreams = [WorkstreamSpec(id="ws-a")]
    return TaskGraph.from_tasks(tasks, name="test-graph", workstreams=workstreams)


@pytest.fixture
def two_ws_graph() -> TaskGraph:
    """Graph with 2 workstreams, 1 task each."""
    tasks = [
        Task(
            id="task_x",
            description="Task X",
            workstream_id="ws-1",
            role=AgentRole.GENERIC,
            primary_agent=AgentConfig(),
        ),
        Task(
            id="task_y",
            description="Task Y",
            workstream_id="ws-2",
            role=AgentRole.GENERIC,
            primary_agent=AgentConfig(),
        ),
    ]
    workstreams = [WorkstreamSpec(id="ws-1"), WorkstreamSpec(id="ws-2")]
    return TaskGraph.from_tasks(tasks, name="test-graph", workstreams=workstreams)


@pytest.fixture
def ws_teardown_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Repo with integration branch and worktree (no task signals).

    Returns (clone, run_dir).
    """
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

    # Create integration branch.
    _git(["-C", str(clone), "checkout", "-b", "agentrelay/test-graph/ws-a/integration"])
    _git(
        [
            "-C",
            str(clone),
            "push",
            "-u",
            "origin",
            "agentrelay/test-graph/ws-a/integration",
        ]
    )
    _git(["-C", str(clone), "checkout", "main"])

    # Create worktree directory (simulated).
    worktree_dir = clone / ".worktrees" / "test-graph" / "ws-a"
    worktree_dir.mkdir(parents=True)
    (worktree_dir / "placeholder").write_text("")

    # Create workstream signal dir (no task signals).
    run_dir = clone / ".workflow" / "test-graph" / "runs" / "0"
    ws_signal_dir = run_dir / "workstreams" / "ws-a"
    ws_signal_dir.mkdir(parents=True)

    return clone, run_dir


@pytest.fixture
def ws_reset_repo(tmp_path: Path) -> tuple[Path, Path, str]:
    """Repo with a merged workstream (integration merged to main).

    Returns (clone, run_dir, pre_merge_sha).
    """
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

    pre_merge_sha = git.rev_parse_head(clone)

    # Create integration branch with work.
    _git(["-C", str(clone), "checkout", "-b", "agentrelay/test-graph/ws-a/integration"])
    (clone / "ws_work.txt").write_text("integration work\n")
    _git(["-C", str(clone), "add", "ws_work.txt"])
    _git(["-C", str(clone), "commit", "-m", "workstream work"])
    _git(
        [
            "-C",
            str(clone),
            "push",
            "-u",
            "origin",
            "agentrelay/test-graph/ws-a/integration",
        ]
    )

    # Create task branch.
    _git(["-C", str(clone), "checkout", "-b", "agentrelay/test-graph/task_a"])
    _git(["-C", str(clone), "push", "-u", "origin", "agentrelay/test-graph/task_a"])
    _git(["-C", str(clone), "checkout", "agentrelay/test-graph/ws-a/integration"])

    # Merge integration to main (simulates integration PR merge).
    _git(["-C", str(clone), "checkout", "main"])
    _git(
        [
            "-C",
            str(clone),
            "merge",
            "agentrelay/test-graph/ws-a/integration",
            "--no-ff",
            "-m",
            "merge integration",
        ]
    )
    _git(["-C", str(clone), "push", "origin", "main"])

    # Create worktree directory (simulated).
    worktree_dir = clone / ".worktrees" / "test-graph" / "ws-a"
    worktree_dir.mkdir(parents=True)
    (worktree_dir / "placeholder").write_text("")

    # Create signal dirs and resolved.json.
    run_dir = clone / ".workflow" / "test-graph" / "runs" / "0"

    # Task signal dir.
    task_a_dir = run_dir / "signals" / "task_a"
    (task_a_dir / "status").mkdir(parents=True)
    (task_a_dir / "status" / "pr_merged").write_text("")

    # Workstream signal dir with resolved.json.
    ws_dir = run_dir / "workstreams" / "ws-a"
    ws_dir.mkdir(parents=True)
    (ws_dir / "merged").write_text("")
    (ws_dir / "resolved.json").write_text(
        json.dumps(
            {
                "workstream_id": "ws-a",
                "integration_pr_url": "https://github.com/org/repo/pull/10",
                "target_branch": "main",
                "target_branch_before_any_merge": pre_merge_sha,
                "merge_occurred": True,
                "merged_at": "2026-04-12T10:00:00Z",
            }
        )
    )

    return clone, run_dir, pre_merge_sha


# ── teardown_workstream tests ──


class TestTeardownWorkstream:
    """Tests for teardown_workstream."""

    def test_removes_infrastructure(
        self, ws_teardown_repo: tuple[Path, Path], single_ws_graph: TaskGraph
    ) -> None:
        """Removes worktree, branches; marks workstream as RESET."""
        clone, run_dir = ws_teardown_repo

        log = teardown_workstream("test-graph", single_ws_graph, run_dir, clone, "ws-a")

        assert not (clone / ".worktrees" / "test-graph" / "ws-a").exists()
        # Signal dir preserved, reset file written.
        assert (run_dir / "workstreams" / "ws-a" / "reset").is_file()
        remaining = git.ls_remote_branches(
            clone, "refs/heads/agentrelay/test-graph/ws-a/integration"
        )
        assert remaining == []
        assert any("Teardown workstream" in msg for msg in log)

    def test_accepts_reset_tasks(
        self, ws_teardown_repo: tuple[Path, Path], single_ws_graph: TaskGraph
    ) -> None:
        """Teardown succeeds when tasks have RESET status (already peeled)."""
        clone, run_dir = ws_teardown_repo

        # Create task signal dirs with RESET status.
        for tid in ("task_a", "task_b"):
            status_dir = run_dir / "signals" / tid / "status"
            status_dir.mkdir(parents=True)
            (status_dir / "reset").write_text("")

        # Should not raise — RESET tasks are considered peeled.
        log = teardown_workstream("test-graph", single_ws_graph, run_dir, clone, "ws-a")
        assert any("Teardown workstream" in msg for msg in log)

    def test_rejects_tasks_with_active_state(
        self, ws_teardown_repo: tuple[Path, Path], single_ws_graph: TaskGraph
    ) -> None:
        """Raises ValueError when a task has non-RESET active state."""
        clone, run_dir = ws_teardown_repo

        # Create a task signal dir with pr_merged status (not RESET).
        status_dir = run_dir / "signals" / "task_a" / "status"
        status_dir.mkdir(parents=True)
        (status_dir / "pr_merged").write_text("")

        with pytest.raises(
            ValueError, match="Task 'task_a' still has active execution state"
        ):
            teardown_workstream("test-graph", single_ws_graph, run_dir, clone, "ws-a")

    def test_unknown_workstream_raises_key_error(
        self, ws_teardown_repo: tuple[Path, Path], single_ws_graph: TaskGraph
    ) -> None:
        """Unknown workstream ID raises KeyError."""
        clone, run_dir = ws_teardown_repo

        with pytest.raises(KeyError, match="nonexistent"):
            teardown_workstream(
                "test-graph", single_ws_graph, run_dir, clone, "nonexistent"
            )

    def test_missing_worktree_is_best_effort(
        self, ws_teardown_repo: tuple[Path, Path], single_ws_graph: TaskGraph
    ) -> None:
        """No error when worktree is already gone."""
        clone, run_dir = ws_teardown_repo

        import shutil

        shutil.rmtree(clone / ".worktrees" / "test-graph" / "ws-a")

        # Should not raise.
        log = teardown_workstream("test-graph", single_ws_graph, run_dir, clone, "ws-a")
        assert any("Teardown workstream" in msg for msg in log)


# ── reset_workstream tests ──


class TestResetWorkstream:
    """Tests for reset_workstream."""

    def test_resets_target_branch(
        self,
        ws_reset_repo: tuple[Path, Path, str],
        single_ws_graph: TaskGraph,
    ) -> None:
        """Target branch (main) is reset to pre-merge SHA."""
        clone, run_dir, pre_merge_sha = ws_reset_repo

        with patch("agentrelay.reset_workstream.gh.pr_close_by_url"):
            log = reset_workstream(
                "test-graph", single_ws_graph, run_dir, clone, "ws-a"
            )

        current_head = git.rev_parse_head(clone)
        assert current_head == pre_merge_sha
        assert any("Reset 'main'" in msg for msg in log)
        assert any("rolled back" in msg for msg in log)

    def test_closes_integration_pr(
        self,
        ws_reset_repo: tuple[Path, Path, str],
        single_ws_graph: TaskGraph,
    ) -> None:
        """Integration PR is closed via gh CLI."""
        clone, run_dir, _ = ws_reset_repo

        with patch("agentrelay.reset_workstream.gh.pr_close_by_url") as mock_close:
            reset_workstream("test-graph", single_ws_graph, run_dir, clone, "ws-a")

        mock_close.assert_called_once_with("https://github.com/org/repo/pull/10")

    def test_marks_all_tasks_as_reset(
        self,
        ws_reset_repo: tuple[Path, Path, str],
        single_ws_graph: TaskGraph,
    ) -> None:
        """All task signal dirs preserved with status/reset."""
        clone, run_dir, _ = ws_reset_repo

        with patch("agentrelay.reset_workstream.gh.pr_close_by_url"):
            reset_workstream("test-graph", single_ws_graph, run_dir, clone, "ws-a")

        # task_a had a signal dir — should be marked RESET.
        assert (run_dir / "signals" / "task_a" / "status" / "reset").is_file()
        # task_b had no signal dir — no change (reset_task_state is a no-op).

    def test_marks_workstream_as_reset(
        self,
        ws_reset_repo: tuple[Path, Path, str],
        single_ws_graph: TaskGraph,
    ) -> None:
        """Workstream worktree and branches removed; signal dir preserved with reset."""
        clone, run_dir, _ = ws_reset_repo

        with patch("agentrelay.reset_workstream.gh.pr_close_by_url"):
            reset_workstream("test-graph", single_ws_graph, run_dir, clone, "ws-a")

        assert not (clone / ".worktrees" / "test-graph" / "ws-a").exists()
        assert (run_dir / "workstreams" / "ws-a" / "reset").is_file()

    def test_non_merged_raises_value_error(
        self, ws_teardown_repo: tuple[Path, Path], single_ws_graph: TaskGraph
    ) -> None:
        """Raises ValueError when workstream has no resolved.json."""
        clone, run_dir = ws_teardown_repo

        with pytest.raises(ValueError, match="no resolved.json"):
            reset_workstream("test-graph", single_ws_graph, run_dir, clone, "ws-a")

    def test_merge_not_occurred_raises_value_error(
        self, tmp_path: Path, single_ws_graph: TaskGraph
    ) -> None:
        """Raises ValueError when merge_occurred is False."""
        run_dir = tmp_path / "runs" / "0"
        ws_dir = run_dir / "workstreams" / "ws-a"
        ws_dir.mkdir(parents=True)
        (ws_dir / "resolved.json").write_text(
            json.dumps(
                {
                    "workstream_id": "ws-a",
                    "integration_pr_url": None,
                    "target_branch": "main",
                    "target_branch_before_any_merge": "abc123",
                    "merge_occurred": False,
                    "merged_at": None,
                }
            )
        )

        with pytest.raises(ValueError, match="not merged"):
            reset_workstream("test-graph", single_ws_graph, run_dir, tmp_path, "ws-a")

    def test_not_most_recent_raises_value_error(
        self, tmp_path: Path, two_ws_graph: TaskGraph
    ) -> None:
        """Raises ValueError when another workstream was merged later."""
        run_dir = tmp_path / "runs" / "0"

        # ws-1 merged first.
        ws1_dir = run_dir / "workstreams" / "ws-1"
        ws1_dir.mkdir(parents=True)
        (ws1_dir / "resolved.json").write_text(
            json.dumps(
                {
                    "workstream_id": "ws-1",
                    "integration_pr_url": None,
                    "target_branch": "main",
                    "target_branch_before_any_merge": "abc123",
                    "merge_occurred": True,
                    "merged_at": "2026-04-12T10:00:00Z",
                }
            )
        )

        # ws-2 merged second.
        ws2_dir = run_dir / "workstreams" / "ws-2"
        ws2_dir.mkdir(parents=True)
        (ws2_dir / "resolved.json").write_text(
            json.dumps(
                {
                    "workstream_id": "ws-2",
                    "integration_pr_url": None,
                    "target_branch": "main",
                    "target_branch_before_any_merge": "def456",
                    "merge_occurred": True,
                    "merged_at": "2026-04-12T11:00:00Z",
                }
            )
        )

        with pytest.raises(
            ValueError, match="not the most recently merged.*Reset 'ws-2'"
        ):
            reset_workstream("test-graph", two_ws_graph, run_dir, tmp_path, "ws-1")

    def test_no_integration_pr_skips_close(
        self,
        ws_reset_repo: tuple[Path, Path, str],
        single_ws_graph: TaskGraph,
    ) -> None:
        """When integration_pr_url is None, PR close is skipped."""
        clone, run_dir, _ = ws_reset_repo

        # Rewrite resolved.json without PR URL.
        ws_dir = run_dir / "workstreams" / "ws-a"
        (ws_dir / "resolved.json").write_text(
            json.dumps(
                {
                    "workstream_id": "ws-a",
                    "integration_pr_url": None,
                    "target_branch": "main",
                    "target_branch_before_any_merge": git.rev_parse(clone, "main~1"),
                    "merge_occurred": True,
                    "merged_at": "2026-04-12T10:00:00Z",
                }
            )
        )

        with patch("agentrelay.reset_workstream.gh.pr_close_by_url") as mock_close:
            log = reset_workstream(
                "test-graph", single_ws_graph, run_dir, clone, "ws-a"
            )

        mock_close.assert_not_called()
        assert any("rolled back" in msg for msg in log)
