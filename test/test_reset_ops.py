"""Tests for reset_ops module — shared reset utilities."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agentrelay.ops import git
from agentrelay.reset_ops import (
    find_workstream_tip,
    reset_branch,
    reset_task_state,
    reset_workstream_state,
    workstream_merge_order,
    write_rollback_entry,
)
from agentrelay.task import AgentConfig, AgentRole, Task
from agentrelay.task_graph import TaskGraph
from agentrelay.workstream import WorkstreamSpec


def _git(args: list[str]) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True)


# ── Fixtures ──


@pytest.fixture
def reset_ops_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Create a bare+clone repo with task branch, integration branch, worktree.

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

    # Create task branch with a commit.
    _git(["-C", str(clone), "checkout", "-b", "agentrelay/test-graph/task_a"])
    (clone / "task_a.txt").write_text("work\n")
    _git(["-C", str(clone), "add", "task_a.txt"])
    _git(["-C", str(clone), "commit", "-m", "task_a work"])
    _git(["-C", str(clone), "push", "-u", "origin", "agentrelay/test-graph/task_a"])

    # Create integration branch off main and push.
    _git(["-C", str(clone), "checkout", "main"])
    _git(
        [
            "-C",
            str(clone),
            "checkout",
            "-b",
            "agentrelay/test-graph/ws-a/integration",
        ]
    )
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

    # Create worktree directory (simulated — not a real git worktree to
    # avoid complexity; tests that need real worktrees create their own).
    worktree_dir = clone / ".worktrees" / "test-graph" / "ws-a"
    worktree_dir.mkdir(parents=True)
    (worktree_dir / "placeholder").write_text("")

    # Create signal directories.
    run_dir = clone / ".workflow" / "test-graph" / "runs" / "0"
    task_signal_dir = run_dir / "signals" / "task_a"
    task_signal_dir.mkdir(parents=True)
    (task_signal_dir / "status").mkdir()
    (task_signal_dir / "status" / "pr_merged").write_text("")

    ws_signal_dir = run_dir / "workstreams" / "ws-a"
    ws_signal_dir.mkdir(parents=True)

    return clone, run_dir


@pytest.fixture
def simple_graph() -> TaskGraph:
    """A graph with 3 tasks in 1 workstream: task_a -> task_b -> task_c."""
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
        Task(
            id="task_c",
            description="Task C",
            workstream_id="ws-a",
            role=AgentRole.GENERIC,
            primary_agent=AgentConfig(),
            dependencies=("task_b",),
        ),
    ]
    workstreams = [WorkstreamSpec(id="ws-a")]
    return TaskGraph.from_tasks(tasks, name="test-graph", workstreams=workstreams)


@pytest.fixture
def two_ws_graph() -> TaskGraph:
    """A graph with 2 workstreams, 1 task each."""
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


# ── reset_branch ──


class TestResetBranch:
    """Tests for reset_branch."""

    def test_resets_and_force_pushes(self, reset_ops_repo: tuple[Path, Path]) -> None:
        """Branch is reset to target SHA locally and on remote."""
        clone, _ = reset_ops_repo
        branch = "agentrelay/test-graph/ws-a/integration"

        # Record original SHA.
        original_sha = git.rev_parse(clone, branch)

        # Add a commit to the branch.
        _git(["-C", str(clone), "checkout", branch])
        (clone / "extra.txt").write_text("extra\n")
        _git(["-C", str(clone), "add", "extra.txt"])
        _git(["-C", str(clone), "commit", "-m", "extra"])
        _git(["-C", str(clone), "push", "origin", branch])
        _git(["-C", str(clone), "checkout", "main"])

        # Reset to original.
        reset_branch(clone, branch, original_sha)

        # Local and remote should be at original SHA.
        assert git.rev_parse(clone, branch) == original_sha
        remote_sha = git.rev_parse(clone, f"origin/{branch}")
        assert remote_sha == original_sha


# ── reset_task_state ──


class TestResetTaskState:
    """Tests for reset_task_state."""

    def test_marks_reset_and_deletes_branches(
        self, reset_ops_repo: tuple[Path, Path]
    ) -> None:
        """Signal directory preserved with status/reset; branches deleted."""
        clone, run_dir = reset_ops_repo

        log = reset_task_state(run_dir, "task_a", "test-graph", clone)

        # Signal dir preserved, status/reset written.
        assert (run_dir / "signals" / "task_a").is_dir()
        assert (run_dir / "signals" / "task_a" / "status" / "reset").is_file()
        assert any("RESET" in msg for msg in log)

        # Remote branch should be gone.
        remaining = git.ls_remote_branches(
            clone, "refs/heads/agentrelay/test-graph/task_a"
        )
        assert remaining == []

    def test_missing_signal_dir_is_noop(
        self, reset_ops_repo: tuple[Path, Path]
    ) -> None:
        """No error when signal directory does not exist."""
        clone, run_dir = reset_ops_repo

        # Delete signal dir first, then call again.
        log = reset_task_state(run_dir, "nonexistent_task", "test-graph", clone)

        # Should not raise — just returns (possibly empty) log.
        assert isinstance(log, list)

    def test_missing_remote_branch_is_best_effort(
        self, reset_ops_repo: tuple[Path, Path]
    ) -> None:
        """No error when remote branch does not exist."""
        clone, run_dir = reset_ops_repo

        # Delete remote branch first.
        _git(
            [
                "-C",
                str(clone),
                "push",
                "origin",
                "--delete",
                "agentrelay/test-graph/task_a",
            ]
        )

        # Should not raise.
        log = reset_task_state(run_dir, "task_a", "test-graph", clone)
        assert any("RESET" in msg for msg in log)


# ── reset_workstream_state ──


class TestResetWorkstreamState:
    """Tests for reset_workstream_state."""

    def test_marks_reset_removes_worktree_and_branches(
        self, reset_ops_repo: tuple[Path, Path]
    ) -> None:
        """Worktree and branches removed; signal dir preserved with reset file."""
        clone, run_dir = reset_ops_repo

        log = reset_workstream_state(run_dir, "ws-a", "test-graph", clone)

        # Worktree dir should be gone.
        assert not (clone / ".worktrees" / "test-graph" / "ws-a").exists()
        # Signal dir preserved, reset file written.
        assert (run_dir / "workstreams" / "ws-a").is_dir()
        assert (run_dir / "workstreams" / "ws-a" / "reset").is_file()
        # Remote branch should be gone.
        remaining = git.ls_remote_branches(
            clone, "refs/heads/agentrelay/test-graph/ws-a/integration"
        )
        assert remaining == []
        assert any("worktree" in msg.lower() for msg in log)
        assert any("RESET" in msg for msg in log)

    def test_missing_worktree_is_best_effort(
        self, reset_ops_repo: tuple[Path, Path]
    ) -> None:
        """No error when worktree directory does not exist."""
        clone, run_dir = reset_ops_repo

        # Remove worktree dir first.
        import shutil

        shutil.rmtree(clone / ".worktrees" / "test-graph" / "ws-a")

        # Should not raise.
        log = reset_workstream_state(run_dir, "ws-a", "test-graph", clone)
        assert isinstance(log, list)

    def test_missing_signal_dir_is_noop(
        self, reset_ops_repo: tuple[Path, Path]
    ) -> None:
        """No error when workstream signal directory does not exist."""
        clone, run_dir = reset_ops_repo

        # Remove signal dir first.
        import shutil

        shutil.rmtree(run_dir / "workstreams" / "ws-a")

        log = reset_workstream_state(run_dir, "ws-a", "test-graph", clone)
        assert isinstance(log, list)


# ── find_workstream_tip ──


class TestFindWorkstreamTip:
    """Tests for find_workstream_tip."""

    def test_returns_last_task_with_signals(
        self, tmp_path: Path, simple_graph: TaskGraph
    ) -> None:
        """Returns the last task (in topo order) that has a signal dir."""
        run_dir = tmp_path / "runs" / "0"
        (run_dir / "signals" / "task_a").mkdir(parents=True)
        (run_dir / "signals" / "task_b").mkdir(parents=True)
        # task_c has no signal dir.

        tip = find_workstream_tip(run_dir, simple_graph, "ws-a")
        assert tip == "task_b"

    def test_returns_none_when_no_signals(
        self, tmp_path: Path, simple_graph: TaskGraph
    ) -> None:
        """Returns None when no task has a signal directory."""
        run_dir = tmp_path / "runs" / "0"
        run_dir.mkdir(parents=True)

        tip = find_workstream_tip(run_dir, simple_graph, "ws-a")
        assert tip is None

    def test_returns_single_task_with_signals(
        self, tmp_path: Path, simple_graph: TaskGraph
    ) -> None:
        """Returns the only task that has a signal dir."""
        run_dir = tmp_path / "runs" / "0"
        (run_dir / "signals" / "task_a").mkdir(parents=True)

        tip = find_workstream_tip(run_dir, simple_graph, "ws-a")
        assert tip == "task_a"

    def test_returns_last_when_all_have_signals(
        self, tmp_path: Path, simple_graph: TaskGraph
    ) -> None:
        """Returns the last task in topo order when all have signal dirs."""
        run_dir = tmp_path / "runs" / "0"
        (run_dir / "signals" / "task_a").mkdir(parents=True)
        (run_dir / "signals" / "task_b").mkdir(parents=True)
        (run_dir / "signals" / "task_c").mkdir(parents=True)

        tip = find_workstream_tip(run_dir, simple_graph, "ws-a")
        assert tip == "task_c"

    def test_skips_reset_tasks(self, tmp_path: Path, simple_graph: TaskGraph) -> None:
        """RESET tasks are skipped — tip is the last non-RESET task."""
        run_dir = tmp_path / "runs" / "0"
        (run_dir / "signals" / "task_a" / "status").mkdir(parents=True)
        (run_dir / "signals" / "task_a" / "status" / "pr_merged").write_text("")
        (run_dir / "signals" / "task_b" / "status").mkdir(parents=True)
        (run_dir / "signals" / "task_b" / "status" / "pr_merged").write_text("")
        # task_c is RESET.
        (run_dir / "signals" / "task_c" / "status").mkdir(parents=True)
        (run_dir / "signals" / "task_c" / "status" / "reset").write_text("")

        tip = find_workstream_tip(run_dir, simple_graph, "ws-a")
        assert tip == "task_b"

    def test_returns_none_when_all_reset(
        self, tmp_path: Path, simple_graph: TaskGraph
    ) -> None:
        """Returns None when all tasks with signal dirs are RESET."""
        run_dir = tmp_path / "runs" / "0"
        (run_dir / "signals" / "task_a" / "status").mkdir(parents=True)
        (run_dir / "signals" / "task_a" / "status" / "reset").write_text("")

        tip = find_workstream_tip(run_dir, simple_graph, "ws-a")
        assert tip is None


# ── workstream_merge_order ──


class TestWorkstreamMergeOrder:
    """Tests for workstream_merge_order."""

    def test_sorts_by_merged_at(self, tmp_path: Path, two_ws_graph: TaskGraph) -> None:
        """Returns workstream IDs in merge order (oldest first)."""
        run_dir = tmp_path / "runs" / "0"

        # ws-2 merged first, ws-1 merged second.
        ws2_dir = run_dir / "workstreams" / "ws-2"
        ws2_dir.mkdir(parents=True)
        (ws2_dir / "resolved.json").write_text(
            json.dumps(
                {
                    "workstream_id": "ws-2",
                    "integration_pr_url": None,
                    "target_branch": "main",
                    "target_branch_before_any_merge": "abc123",
                    "merge_occurred": True,
                    "merged_at": "2026-04-12T10:00:00Z",
                }
            )
        )

        ws1_dir = run_dir / "workstreams" / "ws-1"
        ws1_dir.mkdir(parents=True)
        (ws1_dir / "resolved.json").write_text(
            json.dumps(
                {
                    "workstream_id": "ws-1",
                    "integration_pr_url": None,
                    "target_branch": "main",
                    "target_branch_before_any_merge": "def456",
                    "merge_occurred": True,
                    "merged_at": "2026-04-12T11:00:00Z",
                }
            )
        )

        order = workstream_merge_order(run_dir, two_ws_graph)
        assert order == ["ws-2", "ws-1"]

    def test_excludes_non_merged(self, tmp_path: Path, two_ws_graph: TaskGraph) -> None:
        """Workstreams with merge_occurred=False are excluded."""
        run_dir = tmp_path / "runs" / "0"

        ws1_dir = run_dir / "workstreams" / "ws-1"
        ws1_dir.mkdir(parents=True)
        (ws1_dir / "resolved.json").write_text(
            json.dumps(
                {
                    "workstream_id": "ws-1",
                    "integration_pr_url": None,
                    "target_branch": "main",
                    "target_branch_before_any_merge": "abc123",
                    "merge_occurred": False,
                    "merged_at": None,
                }
            )
        )

        order = workstream_merge_order(run_dir, two_ws_graph)
        assert order == []

    def test_empty_when_no_merged(
        self, tmp_path: Path, two_ws_graph: TaskGraph
    ) -> None:
        """Returns empty list when no workstreams have resolved.json."""
        run_dir = tmp_path / "runs" / "0"
        run_dir.mkdir(parents=True)

        order = workstream_merge_order(run_dir, two_ws_graph)
        assert order == []

    def test_excludes_reset_workstreams(
        self, tmp_path: Path, two_ws_graph: TaskGraph
    ) -> None:
        """RESET workstreams are excluded even if resolved.json exists."""
        run_dir = tmp_path / "runs" / "0"

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
        # Write reset signal — this workstream was undone.
        (ws1_dir / "reset").write_text("")

        order = workstream_merge_order(run_dir, two_ws_graph)
        assert order == []


# ── WriteRollbackEntry ──


class TestWriteRollbackEntry:
    """Tests for write_rollback_entry."""

    def test_creates_file_on_first_call(self, tmp_path: Path) -> None:
        """Creates rollback_log.json with a single entry."""
        ws_dir = tmp_path / "workstreams" / "ws-a"
        ws_dir.mkdir(parents=True)

        write_rollback_entry(ws_dir, "task_a", "pr_merged", "aaa", "bbb")

        log_path = ws_dir / "rollback_log.json"
        assert log_path.is_file()
        entries = json.loads(log_path.read_text())
        assert len(entries) == 1
        assert entries[0]["task_id"] == "task_a"

    def test_appends_to_existing_log(self, tmp_path: Path) -> None:
        """Appends to an existing rollback_log.json."""
        ws_dir = tmp_path / "workstreams" / "ws-a"
        ws_dir.mkdir(parents=True)

        write_rollback_entry(ws_dir, "task_a", "pr_merged", "aaa", "bbb")
        write_rollback_entry(ws_dir, "task_b", "completed", "bbb", "ccc")

        entries = json.loads((ws_dir / "rollback_log.json").read_text())
        assert len(entries) == 2
        assert entries[0]["task_id"] == "task_a"
        assert entries[1]["task_id"] == "task_b"

    def test_entry_fields_match(self, tmp_path: Path) -> None:
        """All expected fields are present with correct values."""
        ws_dir = tmp_path / "workstreams" / "ws-a"
        ws_dir.mkdir(parents=True)

        write_rollback_entry(ws_dir, "task_x", "pr_merged", "sha1", "sha2")

        entries = json.loads((ws_dir / "rollback_log.json").read_text())
        entry = entries[0]
        assert entry["task_id"] == "task_x"
        assert entry["prior_status"] == "pr_merged"
        assert entry["integration_branch_sha_before"] == "sha1"
        assert entry["integration_branch_sha_after"] == "sha2"
        # Timestamp is an ISO string.
        assert "T" in entry["timestamp"]

    def test_creates_signal_dir_if_missing(self, tmp_path: Path) -> None:
        """Creates the workstream signal directory if it does not exist."""
        ws_dir = tmp_path / "workstreams" / "ws-new"
        assert not ws_dir.exists()

        write_rollback_entry(ws_dir, "task_a", "pr_merged", "aaa", "bbb")

        assert ws_dir.is_dir()
        assert (ws_dir / "rollback_log.json").is_file()
