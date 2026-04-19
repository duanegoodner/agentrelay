"""Tests for reset_task module — single-task undo."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agentrelay.ops import git
from agentrelay.reset_task import reset_task
from agentrelay.task import AgentConfig, AgentRole, Task
from agentrelay.task_graph import TaskGraph
from agentrelay.workstream import WorkstreamSpec


def _git(args: list[str]) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True)


# ── Fixtures ──


@pytest.fixture
def two_task_graph() -> TaskGraph:
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
def task_reset_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Create a bare+clone repo for task reset tests.

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

    integration_sha = git.rev_parse_head(clone)

    # Create task_a branch off integration with a commit, merge to integration.
    _git(["-C", str(clone), "checkout", "-b", "agentrelay/test-graph/task_a"])
    (clone / "task_a.txt").write_text("work\n")
    _git(["-C", str(clone), "add", "task_a.txt"])
    _git(["-C", str(clone), "commit", "-m", "task_a work"])
    _git(["-C", str(clone), "push", "-u", "origin", "agentrelay/test-graph/task_a"])

    # Merge task_a into integration branch.
    _git(["-C", str(clone), "checkout", "agentrelay/test-graph/ws-a/integration"])
    _git(
        [
            "-C",
            str(clone),
            "merge",
            "agentrelay/test-graph/task_a",
            "--no-ff",
            "-m",
            "merge task_a",
        ]
    )
    _git(["-C", str(clone), "push", "origin", "agentrelay/test-graph/ws-a/integration"])

    # Create task_b branch off integration with a commit.
    _git(["-C", str(clone), "checkout", "-b", "agentrelay/test-graph/task_b"])
    (clone / "task_b.txt").write_text("work\n")
    _git(["-C", str(clone), "add", "task_b.txt"])
    _git(["-C", str(clone), "commit", "-m", "task_b work"])
    _git(["-C", str(clone), "push", "-u", "origin", "agentrelay/test-graph/task_b"])

    _git(["-C", str(clone), "checkout", "main"])

    # Create signal dirs.
    run_dir = clone / ".workflow" / "test-graph" / "runs" / "0"

    # task_a: PR_MERGED with resolved.json.
    task_a_dir = run_dir / "signals" / "task_a"
    (task_a_dir / "status").mkdir(parents=True)
    (task_a_dir / "status" / "pr_merged").write_text("")
    (task_a_dir / "resolved.json").write_text(
        json.dumps(
            {
                "task_id": "task_a",
                "workstream_id": "ws-a",
                "dependencies": [],
                "inputs_from": [],
                "role": "generic",
                "model": None,
                "tagged_paths": [],
                "branch_name": "agentrelay/test-graph/task_a",
                "integration_branch": "agentrelay/test-graph/ws-a/integration",
                "integration_branch_before_merge": integration_sha,
                "completed_at_attempt": 0,
                "pr_url": "https://github.com/org/repo/pull/1",
            }
        )
    )

    # task_b: FAILED (no resolved.json).
    task_b_dir = run_dir / "signals" / "task_b"
    (task_b_dir / "status").mkdir(parents=True)
    (task_b_dir / "status" / "failed").write_text("")

    return clone, run_dir


# ── Tests ──


class TestResetNonMergedTask:
    """Tests for resetting non-merged (FAILED) tasks."""

    def test_deletes_state(
        self, task_reset_repo: tuple[Path, Path], two_task_graph: TaskGraph
    ) -> None:
        """FAILED tip task: signal dir and branch deleted."""
        clone, run_dir = task_reset_repo

        log = reset_task("test-graph", two_task_graph, run_dir, clone, task_id="task_b")

        assert not (run_dir / "signals" / "task_b").exists()
        remaining = git.ls_remote_branches(
            clone, "refs/heads/agentrelay/test-graph/task_b"
        )
        assert remaining == []
        assert any("Reset task 'task_b'" in msg for msg in log)
        assert any("tip is now 'task_a'" in msg for msg in log)


class TestResetMergedTask:
    """Tests for resetting merged (PR_MERGED) tasks."""

    def test_resets_integration_branch(
        self, task_reset_repo: tuple[Path, Path], two_task_graph: TaskGraph
    ) -> None:
        """PR_MERGED task: integration branch is reset to pre-merge SHA."""
        clone, run_dir = task_reset_repo

        # First reset task_b (the tip).
        reset_task("test-graph", two_task_graph, run_dir, clone, task_id="task_b")

        # Read the stored pre-merge SHA for task_a.
        resolved_path = run_dir / "signals" / "task_a" / "resolved.json"
        data = json.loads(resolved_path.read_text())
        pre_merge_sha = data["integration_branch_before_merge"]

        # Now reset task_a (the new tip).
        log = reset_task("test-graph", two_task_graph, run_dir, clone, task_id="task_a")

        # Integration branch should be reset to pre-merge SHA.
        integration_sha = git.rev_parse(clone, "agentrelay/test-graph/ws-a/integration")
        assert integration_sha == pre_merge_sha

        assert not (run_dir / "signals" / "task_a").exists()
        assert any("Reset integration branch" in msg for msg in log)
        assert any("no remaining tasks" in msg for msg in log)


class TestResetTaskValidation:
    """Tests for validation in reset_task."""

    def test_non_tip_raises_value_error(
        self, task_reset_repo: tuple[Path, Path], two_task_graph: TaskGraph
    ) -> None:
        """Resetting a non-tip task raises ValueError with guidance."""
        clone, run_dir = task_reset_repo

        with pytest.raises(ValueError, match="not the workstream tip.*Reset 'task_b'"):
            reset_task("test-graph", two_task_graph, run_dir, clone, task_id="task_a")

    def test_pending_task_raises_value_error(
        self, task_reset_repo: tuple[Path, Path], two_task_graph: TaskGraph
    ) -> None:
        """Resetting a PENDING task raises ValueError."""
        clone, run_dir = task_reset_repo

        # Remove task_b signal dir to make it "never started".
        import shutil

        shutil.rmtree(run_dir / "signals" / "task_b")

        # Now task_a is the tip but let's try a task with no state at all.
        # Add a task_c with no state by removing both signals.
        shutil.rmtree(run_dir / "signals" / "task_a")

        with pytest.raises(ValueError, match="No tasks have execution state"):
            reset_task("test-graph", two_task_graph, run_dir, clone, ws_id="ws-a")

    def test_unknown_task_raises_key_error(
        self, task_reset_repo: tuple[Path, Path], two_task_graph: TaskGraph
    ) -> None:
        """Unknown task ID raises KeyError."""
        clone, run_dir = task_reset_repo

        with pytest.raises(KeyError, match="nonexistent"):
            reset_task(
                "test-graph", two_task_graph, run_dir, clone, task_id="nonexistent"
            )

    def test_unknown_workstream_raises_key_error(
        self, task_reset_repo: tuple[Path, Path], two_task_graph: TaskGraph
    ) -> None:
        """Unknown workstream ID raises KeyError."""
        clone, run_dir = task_reset_repo

        with pytest.raises(KeyError, match="nonexistent"):
            reset_task(
                "test-graph", two_task_graph, run_dir, clone, ws_id="nonexistent"
            )

    def test_neither_task_nor_ws_raises(
        self, task_reset_repo: tuple[Path, Path], two_task_graph: TaskGraph
    ) -> None:
        """Neither task_id nor ws_id raises ValueError."""
        clone, run_dir = task_reset_repo

        with pytest.raises(ValueError, match="Either task_id or ws_id"):
            reset_task("test-graph", two_task_graph, run_dir, clone)


class TestResetTaskAutoDetect:
    """Tests for auto-detecting tip via --workstream."""

    def test_auto_detects_tip(
        self, task_reset_repo: tuple[Path, Path], two_task_graph: TaskGraph
    ) -> None:
        """Auto-detects task_b as the tip and resets it."""
        clone, run_dir = task_reset_repo

        log = reset_task("test-graph", two_task_graph, run_dir, clone, ws_id="ws-a")

        assert not (run_dir / "signals" / "task_b").exists()
        # task_a should still have state.
        assert (run_dir / "signals" / "task_a").is_dir()
        assert any("Reset task 'task_b'" in msg for msg in log)


class TestSuccessiveResets:
    """Tests for peeling back a workstream one task at a time."""

    def test_successive_resets_peel_workstream(
        self, task_reset_repo: tuple[Path, Path], two_task_graph: TaskGraph
    ) -> None:
        """Resetting task_b then task_a fully peels the workstream."""
        clone, run_dir = task_reset_repo

        # Reset task_b (FAILED tip).
        log_b = reset_task(
            "test-graph", two_task_graph, run_dir, clone, task_id="task_b"
        )
        assert any("tip is now 'task_a'" in msg for msg in log_b)
        assert not (run_dir / "signals" / "task_b").exists()
        assert (run_dir / "signals" / "task_a").is_dir()

        # Reset task_a (PR_MERGED, now the tip).
        log_a = reset_task(
            "test-graph", two_task_graph, run_dir, clone, task_id="task_a"
        )
        assert any("no remaining tasks" in msg for msg in log_a)
        assert not (run_dir / "signals" / "task_a").exists()
