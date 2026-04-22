"""Tests for reset_to module — batch rollback command."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentrelay.reset_to import (
    BranchReset,
    ResetToPlan,
    _transitive_dependents,
    build_plan,
    execute_plan,
    format_plan,
    resolve_target,
)
from agentrelay.resolved import ResolvedTask, ResolvedWorkstream
from agentrelay.task import AgentConfig, AgentRole, Task
from agentrelay.task_graph import TaskGraph
from agentrelay.workstream import WorkstreamSpec


def _git(args: list[str]) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True)


# ── Pure-data fixtures ──


@pytest.fixture
def three_task_graph() -> TaskGraph:
    """ws-a: task_a -> task_b -> task_c."""
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
def two_ws_independent_graph() -> TaskGraph:
    """ws-a: task_a, task_b; ws-b: task_c. Independent workstreams."""
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
            workstream_id="ws-b",
            role=AgentRole.GENERIC,
            primary_agent=AgentConfig(),
        ),
    ]
    workstreams = [WorkstreamSpec(id="ws-a"), WorkstreamSpec(id="ws-b")]
    return TaskGraph.from_tasks(tasks, name="test-graph", workstreams=workstreams)


@pytest.fixture
def cross_dep_graph() -> TaskGraph:
    """ws-a: task_a -> task_b; ws-b: task_c (depends on task_b)."""
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
            workstream_id="ws-b",
            role=AgentRole.GENERIC,
            primary_agent=AgentConfig(),
            dependencies=("task_b",),
        ),
    ]
    workstreams = [WorkstreamSpec(id="ws-a"), WorkstreamSpec(id="ws-b")]
    return TaskGraph.from_tasks(tasks, name="test-graph", workstreams=workstreams)


@pytest.fixture
def multi_ws_mixed_graph() -> TaskGraph:
    """ws-a: task_a; ws-b: task_b (depends on task_a); ws-c: task_c (independent)."""
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
            workstream_id="ws-b",
            role=AgentRole.GENERIC,
            primary_agent=AgentConfig(),
            dependencies=("task_a",),
        ),
        Task(
            id="task_c",
            description="Task C",
            workstream_id="ws-c",
            role=AgentRole.GENERIC,
            primary_agent=AgentConfig(),
        ),
    ]
    workstreams = [
        WorkstreamSpec(id="ws-a"),
        WorkstreamSpec(id="ws-b"),
        WorkstreamSpec(id="ws-c"),
    ]
    return TaskGraph.from_tasks(tasks, name="test-graph", workstreams=workstreams)


# ── Signal directory helpers ──


def _write_task_status(run_dir: Path, task_id: str, status: str) -> None:
    """Write a status signal file for a task."""
    status_dir = run_dir / "signals" / task_id / "status"
    status_dir.mkdir(parents=True, exist_ok=True)
    (status_dir / status).write_text("")


def _write_task_resolved(
    run_dir: Path,
    task_id: str,
    ws_id: str,
    graph_name: str,
    *,
    integration_branch_before_merge: str | None = "abc123",
) -> None:
    """Write a resolved.json for a task."""
    resolved = ResolvedTask(
        task_id=task_id,
        workstream_id=ws_id,
        dependencies=(),
        inputs_from=(),
        role="generic",
        model=None,
        tagged_paths=(),
        branch_name=f"agentrelay/{graph_name}/{task_id}",
        integration_branch=f"agentrelay/{graph_name}/{ws_id}/integration",
        integration_branch_before_merge=integration_branch_before_merge,
        completed_at_attempt=0,
        pr_url=f"https://github.com/org/repo/pull/{task_id}",
    )
    signal_dir = run_dir / "signals" / task_id
    signal_dir.mkdir(parents=True, exist_ok=True)
    (signal_dir / "resolved.json").write_text(json.dumps(resolved.to_dict(), indent=2))


def _write_ws_resolved(
    run_dir: Path,
    ws_id: str,
    *,
    target_branch_before_any_merge: str = "def456",
    merge_occurred: bool = True,
    merged_at: str | None = None,
    integration_pr_url: str | None = None,
) -> None:
    """Write a resolved.json for a workstream."""
    resolved = ResolvedWorkstream(
        workstream_id=ws_id,
        integration_pr_url=integration_pr_url
        or f"https://github.com/org/repo/pull/{ws_id}",
        target_branch="main",
        target_branch_before_any_merge=target_branch_before_any_merge,
        merge_occurred=merge_occurred,
        merged_at=merged_at or "2026-04-20T12:00:00+00:00",
    )
    ws_dir = run_dir / "workstreams" / ws_id
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "resolved.json").write_text(json.dumps(resolved.to_dict(), indent=2))


def _write_ws_merged_status(run_dir: Path, ws_id: str) -> None:
    """Write a merged status signal for a workstream."""
    ws_dir = run_dir / "workstreams" / ws_id
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "merged").write_text("")


# ── Git repo fixtures ──


@pytest.fixture
def three_task_repo(tmp_path: Path) -> tuple[Path, Path, TaskGraph]:
    """Bare+clone with 3 tasks merged to integration branch.

    Returns (clone, run_dir, graph).
    """
    bare = tmp_path / "remote.git"
    _git(["init", "--bare", "-b", "main", str(bare)])

    clone = tmp_path / "clone"
    _git(["clone", str(bare), str(clone)])
    _git(["-C", str(clone), "config", "user.email", "test@test.com"])
    _git(["-C", str(clone), "config", "user.name", "Test"])

    # Initial commit.
    (clone / "README.md").write_text("init")
    _git(["-C", str(clone), "add", "README.md"])
    _git(["-C", str(clone), "commit", "-m", "init"])
    _git(["-C", str(clone), "push", "origin", "main"])

    # Create integration branch.
    _git(["-C", str(clone), "checkout", "-b", "agentrelay/test-graph/ws-a/integration"])
    _git(["-C", str(clone), "push", "origin", "agentrelay/test-graph/ws-a/integration"])

    # Record pre-merge SHAs and merge tasks.
    pre_merge_shas: dict[str, str] = {}
    for tid in ["task_a", "task_b", "task_c"]:
        pre_merge_shas[tid] = subprocess.run(
            ["git", "-C", str(clone), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        branch = f"agentrelay/test-graph/{tid}"
        _git(["-C", str(clone), "checkout", "-b", branch])
        (clone / f"{tid}.txt").write_text(f"work: {tid}")
        _git(["-C", str(clone), "add", f"{tid}.txt"])
        _git(["-C", str(clone), "commit", "-m", f"work: {tid}"])
        _git(["-C", str(clone), "push", "origin", branch])
        _git(["-C", str(clone), "checkout", "agentrelay/test-graph/ws-a/integration"])
        _git(["-C", str(clone), "merge", "--no-ff", branch, "-m", f"merge {tid}"])
    _git(
        [
            "-C",
            str(clone),
            "push",
            "origin",
            "agentrelay/test-graph/ws-a/integration",
        ]
    )

    # Set up signal dirs and resolved.json.
    run_dir = clone / ".workflow" / "test-graph" / "runs" / "0"
    for tid in ["task_a", "task_b", "task_c"]:
        _write_task_status(run_dir, tid, "pr_merged")
        _write_task_resolved(
            run_dir,
            tid,
            "ws-a",
            "test-graph",
            integration_branch_before_merge=pre_merge_shas[tid],
        )

    # Build graph.
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
    graph = TaskGraph.from_tasks(tasks, name="test-graph", workstreams=workstreams)

    return clone, run_dir, graph


# ── TestResolveTarget ──


class TestResolveTarget:
    """Tests for resolve_target()."""

    def test_resolves_known_task_id(self, three_task_graph: TaskGraph) -> None:
        assert resolve_target(three_task_graph, "task_a") == ("task", "task_a")

    def test_resolves_known_ws_id(self, three_task_graph: TaskGraph) -> None:
        assert resolve_target(three_task_graph, "ws-a") == ("workstream", "ws-a")

    def test_unknown_id_raises_key_error(self, three_task_graph: TaskGraph) -> None:
        with pytest.raises(KeyError):
            resolve_target(three_task_graph, "nonexistent")

    def test_workstream_takes_precedence(self) -> None:
        """If an ID exists as both workstream and task, workstream wins."""
        tasks = [
            Task(
                id="shared_id",
                description="A task",
                workstream_id="shared_id",
                role=AgentRole.GENERIC,
                primary_agent=AgentConfig(),
            ),
        ]
        workstreams = [WorkstreamSpec(id="shared_id")]
        graph = TaskGraph.from_tasks(tasks, name="test-graph", workstreams=workstreams)
        assert resolve_target(graph, "shared_id") == ("workstream", "shared_id")


# ── TestTransitiveDependents ──


class TestTransitiveDependents:
    """Tests for _transitive_dependents()."""

    def test_no_dependents(self, three_task_graph: TaskGraph) -> None:
        result = _transitive_dependents(three_task_graph, {"task_c"})
        assert result == set()

    def test_direct_dependents(self, three_task_graph: TaskGraph) -> None:
        result = _transitive_dependents(three_task_graph, {"task_b"})
        assert result == {"task_c"}

    def test_transitive_chain(self, three_task_graph: TaskGraph) -> None:
        result = _transitive_dependents(three_task_graph, {"task_a"})
        assert result == {"task_b", "task_c"}

    def test_cross_workstream_transitive(self, cross_dep_graph: TaskGraph) -> None:
        result = _transitive_dependents(cross_dep_graph, {"task_b"})
        assert result == {"task_c"}


# ── TestTaskTargetPlan ──


class TestTaskTargetPlan:
    """Tests for build_plan() with task targets."""

    def test_removes_later_tasks_in_same_ws(
        self, three_task_graph: TaskGraph, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "0"
        _write_task_status(run_dir, "task_b", "pr_merged")
        _write_task_status(run_dir, "task_c", "failed")

        plan = build_plan("test-graph", three_task_graph, run_dir, after="task_a")
        assert set(plan.tasks_to_reset) == {"task_b", "task_c"}

    def test_single_integration_reset_for_multiple_tasks(
        self, three_task_graph: TaskGraph, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "0"
        _write_task_status(run_dir, "task_b", "pr_merged")
        _write_task_resolved(run_dir, "task_b", "ws-a", "test-graph")
        _write_task_status(run_dir, "task_c", "pr_merged")
        _write_task_resolved(run_dir, "task_c", "ws-a", "test-graph")

        plan = build_plan("test-graph", three_task_graph, run_dir, after="task_a")
        # One integration branch reset (for task_b, the first removed).
        assert len(plan.integration_branch_resets) == 1
        assert "task_b" in plan.integration_branch_resets[0].description

    def test_no_target_branch_reset(
        self, three_task_graph: TaskGraph, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "0"
        _write_task_status(run_dir, "task_b", "pr_merged")
        _write_task_resolved(run_dir, "task_b", "ws-a", "test-graph")

        plan = build_plan("test-graph", three_task_graph, run_dir, after="task_a")
        assert plan.target_branch_reset is None

    def test_cross_ws_dependent_included(
        self, cross_dep_graph: TaskGraph, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "0"
        _write_task_status(run_dir, "task_b", "pr_merged")
        _write_task_resolved(run_dir, "task_b", "ws-a", "test-graph")
        _write_task_status(run_dir, "task_c", "running")

        plan = build_plan("test-graph", cross_dep_graph, run_dir, after="task_a")
        assert "task_b" in plan.tasks_to_reset
        assert "task_c" in plan.tasks_to_reset

    def test_independent_ws_untouched(
        self, two_ws_independent_graph: TaskGraph, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "0"
        _write_task_status(run_dir, "task_b", "pr_merged")
        _write_task_resolved(run_dir, "task_b", "ws-a", "test-graph")
        _write_task_status(run_dir, "task_c", "running")

        plan = build_plan(
            "test-graph", two_ws_independent_graph, run_dir, after="task_a"
        )
        assert "task_b" in plan.tasks_to_reset
        # task_c is independent — should NOT be in the removal set.
        assert "task_c" not in plan.tasks_to_reset

    def test_nothing_to_remove_raises(
        self, three_task_graph: TaskGraph, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "0"
        # task_c is the last task; nothing after it.
        with pytest.raises(ValueError, match="Nothing to reset"):
            build_plan("test-graph", three_task_graph, run_dir, after="task_c")

    def test_non_merged_tasks_no_branch_reset(
        self, three_task_graph: TaskGraph, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "0"
        _write_task_status(run_dir, "task_b", "failed")
        _write_task_status(run_dir, "task_c", "failed")

        plan = build_plan("test-graph", three_task_graph, run_dir, after="task_a")
        assert len(plan.integration_branch_resets) == 0

    def test_workstream_teardown_when_all_tasks_removed(
        self, cross_dep_graph: TaskGraph, tmp_path: Path
    ) -> None:
        """Non-anchor ws with all tasks removed gets torn down."""
        run_dir = tmp_path / "runs" / "0"
        _write_task_status(run_dir, "task_b", "pr_merged")
        _write_task_resolved(run_dir, "task_b", "ws-a", "test-graph")
        _write_task_status(run_dir, "task_c", "running")

        plan = build_plan("test-graph", cross_dep_graph, run_dir, after="task_a")
        # ws-b has only task_c which is in the removal set.
        assert "ws-b" in plan.workstreams_to_teardown

    def test_independent_ws_not_torn_down(self, tmp_path: Path) -> None:
        """Independent in-progress workstream is not torn down."""
        # ws-a: task_a1 -> task_a2; ws-b: task_b (depends on task_a2);
        # ws-c: task_c (independent).
        tasks = [
            Task(
                id="task_a1",
                description="A1",
                workstream_id="ws-a",
                role=AgentRole.GENERIC,
                primary_agent=AgentConfig(),
            ),
            Task(
                id="task_a2",
                description="A2",
                workstream_id="ws-a",
                role=AgentRole.GENERIC,
                primary_agent=AgentConfig(),
                dependencies=("task_a1",),
            ),
            Task(
                id="task_b",
                description="B",
                workstream_id="ws-b",
                role=AgentRole.GENERIC,
                primary_agent=AgentConfig(),
                dependencies=("task_a2",),
            ),
            Task(
                id="task_c",
                description="C",
                workstream_id="ws-c",
                role=AgentRole.GENERIC,
                primary_agent=AgentConfig(),
            ),
        ]
        workstreams = [
            WorkstreamSpec(id="ws-a"),
            WorkstreamSpec(id="ws-b"),
            WorkstreamSpec(id="ws-c"),
        ]
        graph = TaskGraph.from_tasks(tasks, name="test-graph", workstreams=workstreams)

        run_dir = tmp_path / "runs" / "0"
        _write_task_status(run_dir, "task_a2", "pr_merged")
        _write_task_resolved(run_dir, "task_a2", "ws-a", "test-graph")
        _write_task_status(run_dir, "task_b", "running")
        _write_task_status(run_dir, "task_c", "running")

        plan = build_plan("test-graph", graph, run_dir, after="task_a1")
        # ws-b (depends on task_a2 being removed) should be torn down.
        assert "ws-b" in plan.workstreams_to_teardown
        # ws-c (independent) should NOT be torn down.
        assert "ws-c" not in plan.workstreams_to_teardown


# ── TestWsTargetPlan ──


class TestWsTargetPlan:
    """Tests for build_plan() with workstream targets."""

    def test_removes_later_merged_ws(
        self, two_ws_independent_graph: TaskGraph, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "0"
        # ws-a merged first.
        _write_ws_resolved(run_dir, "ws-a", merged_at="2026-04-20T10:00:00+00:00")
        _write_ws_merged_status(run_dir, "ws-a")
        # ws-b merged second.
        _write_ws_resolved(
            run_dir,
            "ws-b",
            merged_at="2026-04-20T11:00:00+00:00",
            target_branch_before_any_merge="sha_before_ws_b",
        )
        _write_ws_merged_status(run_dir, "ws-b")
        _write_task_status(run_dir, "task_c", "pr_merged")

        plan = build_plan("test-graph", two_ws_independent_graph, run_dir, after="ws-a")
        assert "ws-b" in plan.workstreams_to_unmerge

    def test_single_target_branch_reset(
        self, two_ws_independent_graph: TaskGraph, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "0"
        _write_ws_resolved(run_dir, "ws-a", merged_at="2026-04-20T10:00:00+00:00")
        _write_ws_merged_status(run_dir, "ws-a")
        _write_ws_resolved(
            run_dir,
            "ws-b",
            merged_at="2026-04-20T11:00:00+00:00",
            target_branch_before_any_merge="sha_before_ws_b",
        )
        _write_ws_merged_status(run_dir, "ws-b")
        _write_task_status(run_dir, "task_c", "pr_merged")

        plan = build_plan("test-graph", two_ws_independent_graph, run_dir, after="ws-a")
        assert plan.target_branch_reset is not None
        assert plan.target_branch_reset.target_sha == "sha_before_ws_b"

    def test_nothing_to_unmerge_raises(
        self, two_ws_independent_graph: TaskGraph, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "0"
        # Only ws-a is merged (last).
        _write_ws_resolved(run_dir, "ws-a", merged_at="2026-04-20T10:00:00+00:00")
        _write_ws_merged_status(run_dir, "ws-a")

        with pytest.raises(ValueError, match="Nothing to reset"):
            build_plan(
                "test-graph",
                two_ws_independent_graph,
                run_dir,
                after="ws-a",
            )

    def test_not_merged_ws_raises(
        self, two_ws_independent_graph: TaskGraph, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "0"
        with pytest.raises(ValueError, match="not in the merge order"):
            build_plan(
                "test-graph",
                two_ws_independent_graph,
                run_dir,
                after="ws-a",
            )

    def test_collects_pr_urls(
        self, two_ws_independent_graph: TaskGraph, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "0"
        _write_ws_resolved(
            run_dir,
            "ws-a",
            merged_at="2026-04-20T10:00:00+00:00",
        )
        _write_ws_merged_status(run_dir, "ws-a")
        _write_ws_resolved(
            run_dir,
            "ws-b",
            merged_at="2026-04-20T11:00:00+00:00",
            integration_pr_url="https://github.com/org/repo/pull/99",
        )
        _write_ws_merged_status(run_dir, "ws-b")
        _write_task_status(run_dir, "task_c", "pr_merged")

        plan = build_plan("test-graph", two_ws_independent_graph, run_dir, after="ws-a")
        assert "https://github.com/org/repo/pull/99" in plan.pr_urls_to_close

    def test_dependent_in_progress_torn_down(
        self, multi_ws_mixed_graph: TaskGraph, tmp_path: Path
    ) -> None:
        """In-progress ws with cross-ws deps on unmerged ws gets torn down."""
        run_dir = tmp_path / "runs" / "0"
        # ws-a merged first.
        _write_ws_resolved(run_dir, "ws-a", merged_at="2026-04-20T10:00:00+00:00")
        _write_ws_merged_status(run_dir, "ws-a")
        _write_task_status(run_dir, "task_a", "pr_merged")
        # ws-b merged second (depends on ws-a's tasks).
        _write_ws_resolved(run_dir, "ws-b", merged_at="2026-04-20T11:00:00+00:00")
        _write_ws_merged_status(run_dir, "ws-b")
        _write_task_status(run_dir, "task_b", "pr_merged")
        # ws-c is in-progress (independent).
        _write_task_status(run_dir, "task_c", "running")

        plan = build_plan("test-graph", multi_ws_mixed_graph, run_dir, after="ws-a")
        # ws-b is unmerged from target.
        assert "ws-b" in plan.workstreams_to_unmerge
        # ws-c is independent — should NOT be torn down.
        assert "ws-c" not in plan.workstreams_to_teardown


# ── TestFormatPlan ──


class TestFormatPlan:
    """Tests for format_plan()."""

    def test_format_with_target_branch_reset(self) -> None:
        plan = ResetToPlan(
            target_kind="workstream",
            target_id="ws-a",
            target_branch_reset=BranchReset("main", "abc123def456", "before ws-b"),
            integration_branch_resets=(),
            tasks_to_reset=("task_c",),
            workstreams_to_teardown=(),
            workstreams_to_unmerge=("ws-b",),
            pr_urls_to_close=(),
        )
        output = format_plan(plan)
        assert "main" in output
        assert "abc123def456"[:12] in output
        assert "ws-b" in output

    def test_format_without_target_branch_reset(self) -> None:
        plan = ResetToPlan(
            target_kind="task",
            target_id="task_a",
            target_branch_reset=None,
            integration_branch_resets=(
                BranchReset("integration", "sha123", "before task_b"),
            ),
            tasks_to_reset=("task_b", "task_c"),
            workstreams_to_teardown=(),
            workstreams_to_unmerge=(),
            pr_urls_to_close=(),
        )
        output = format_plan(plan)
        assert "Target branch reset" not in output
        assert "Integration branch resets: 1" in output
        assert "2 task(s) reset" in output

    def test_format_counts_accurate(self) -> None:
        plan = ResetToPlan(
            target_kind="workstream",
            target_id="ws-a",
            target_branch_reset=BranchReset("main", "abc", "before ws-b"),
            integration_branch_resets=(
                BranchReset("int-1", "sha1", "desc1"),
                BranchReset("int-2", "sha2", "desc2"),
            ),
            tasks_to_reset=("t1", "t2", "t3"),
            workstreams_to_teardown=("ws-c",),
            workstreams_to_unmerge=("ws-b",),
            pr_urls_to_close=("url1",),
        )
        output = format_plan(plan)
        assert "3 force-push(es)" in output
        assert "3 task(s) reset" in output
        assert "2 workstream(s) affected" in output


# ── TestExecutePlan ──


class TestExecutePlan:
    """Tests for execute_plan() with real git repos."""

    def test_task_target_resets_integration_branch(
        self, three_task_repo: tuple[Path, Path, TaskGraph]
    ) -> None:
        clone, run_dir, graph = three_task_repo
        plan = build_plan("test-graph", graph, run_dir, after="task_a")

        with patch("agentrelay.reset_to.gh.pr_close_by_url"):
            execute_plan("test-graph", graph, run_dir, clone, plan)

        # Integration branch should be at task_a's pre-merge SHA
        # (which is the SHA before task_b was merged).
        resolved_b = json.loads(
            (run_dir / "signals" / "task_b" / "resolved.json").read_text()
        )
        expected_sha = resolved_b["integration_branch_before_merge"]
        actual_sha = subprocess.run(
            [
                "git",
                "-C",
                str(clone),
                "rev-parse",
                "agentrelay/test-graph/ws-a/integration",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert actual_sha == expected_sha

    def test_marks_all_tasks_as_reset(
        self, three_task_repo: tuple[Path, Path, TaskGraph]
    ) -> None:
        clone, run_dir, graph = three_task_repo
        plan = build_plan("test-graph", graph, run_dir, after="task_a")

        with patch("agentrelay.reset_to.gh.pr_close_by_url"):
            execute_plan("test-graph", graph, run_dir, clone, plan)

        for tid in ["task_b", "task_c"]:
            assert (run_dir / "signals" / tid / "status" / "reset").exists()
        # task_a should NOT be reset.
        assert not (run_dir / "signals" / "task_a" / "status" / "reset").exists()

    def test_writes_rollback_entries_with_source(
        self, three_task_repo: tuple[Path, Path, TaskGraph]
    ) -> None:
        clone, run_dir, graph = three_task_repo
        plan = build_plan("test-graph", graph, run_dir, after="task_a")

        with patch("agentrelay.reset_to.gh.pr_close_by_url"):
            execute_plan("test-graph", graph, run_dir, clone, plan)

        log_path = run_dir / "workstreams" / "ws-a" / "rollback_log.json"
        assert log_path.is_file()
        entries = json.loads(log_path.read_text())
        # task_b and task_c were merged, so both get entries.
        assert len(entries) == 2
        for entry in entries:
            assert entry["source"] == "reset-to --after task_a"

    def test_pr_close_failure_continues(
        self, three_task_repo: tuple[Path, Path, TaskGraph]
    ) -> None:
        clone, run_dir, graph = three_task_repo
        # Build plan and inject a PR URL to close.
        plan = build_plan("test-graph", graph, run_dir, after="task_a")
        plan = ResetToPlan(
            target_kind=plan.target_kind,
            target_id=plan.target_id,
            target_branch_reset=plan.target_branch_reset,
            integration_branch_resets=plan.integration_branch_resets,
            tasks_to_reset=plan.tasks_to_reset,
            workstreams_to_teardown=plan.workstreams_to_teardown,
            workstreams_to_unmerge=plan.workstreams_to_unmerge,
            pr_urls_to_close=("https://github.com/org/repo/pull/1",),
        )

        with patch(
            "agentrelay.reset_to.gh.pr_close_by_url",
            side_effect=subprocess.CalledProcessError(1, "gh"),
        ):
            log = execute_plan("test-graph", graph, run_dir, clone, plan)

        # Should complete despite PR close failure.
        assert any("WARNING" in msg and "Could not close" in msg for msg in log)
        # Tasks should still be reset.
        assert (run_dir / "signals" / "task_b" / "status" / "reset").exists()

    def test_pr_body_update_best_effort(
        self, three_task_repo: tuple[Path, Path, TaskGraph]
    ) -> None:
        clone, run_dir, graph = three_task_repo
        # Add pr_created for the PR body updater.
        ws_dir = run_dir / "workstreams" / "ws-a"
        ws_dir.mkdir(parents=True, exist_ok=True)
        (ws_dir / "pr_created").write_text("https://github.com/org/repo/pull/1")

        plan = build_plan("test-graph", graph, run_dir, after="task_a")
        mock_updater = MagicMock()
        mock_updater.append_reset_activity.return_value = ["Updated PR"]

        with patch("agentrelay.reset_to.gh.pr_close_by_url"):
            log = execute_plan(
                "test-graph",
                graph,
                run_dir,
                clone,
                plan,
                pr_body_updater=mock_updater,
            )

        mock_updater.append_reset_activity.assert_called_once()
        assert "Updated PR" in log

    def test_surviving_worktree_checked_out_to_integration(
        self, three_task_repo: tuple[Path, Path, TaskGraph]
    ) -> None:
        """Worktree on a deleted task branch gets switched to integration."""
        clone, run_dir, graph = three_task_repo

        # Detach HEAD in main clone so we can check out branches in worktrees.
        _git(["-C", str(clone), "checkout", "--detach", "HEAD"])

        # Create a worktree checked out on task_c's branch.
        worktree_path = clone / ".worktrees" / "test-graph" / "ws-a"
        _git(
            [
                "-C",
                str(clone),
                "worktree",
                "add",
                str(worktree_path),
                "agentrelay/test-graph/task_c",
            ]
        )

        plan = build_plan("test-graph", graph, run_dir, after="task_a")

        with patch("agentrelay.reset_to.gh.pr_close_by_url"):
            log = execute_plan("test-graph", graph, run_dir, clone, plan)

        # Worktree should now be on the integration branch.
        current = subprocess.run(
            ["git", "-C", str(worktree_path), "rev-parse", "--abbrev-ref", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert current == "agentrelay/test-graph/ws-a/integration"
        assert any("Switched worktree" in msg for msg in log)

    def test_surviving_worktree_already_on_integration(
        self, three_task_repo: tuple[Path, Path, TaskGraph]
    ) -> None:
        """No-op if worktree is already on the integration branch."""
        clone, run_dir, graph = three_task_repo

        # Detach HEAD in main clone so the integration branch can be
        # checked out in the worktree.
        _git(["-C", str(clone), "checkout", "--detach", "HEAD"])

        worktree_path = clone / ".worktrees" / "test-graph" / "ws-a"
        _git(
            [
                "-C",
                str(clone),
                "worktree",
                "add",
                str(worktree_path),
                "agentrelay/test-graph/ws-a/integration",
            ]
        )

        plan = build_plan("test-graph", graph, run_dir, after="task_a")

        with patch("agentrelay.reset_to.gh.pr_close_by_url"):
            log = execute_plan("test-graph", graph, run_dir, clone, plan)

        # No "Switched" message since it was already on integration.
        assert not any("Switched worktree" in msg for msg in log)


# ── TestCLI ──


class TestCLIParsing:
    """Tests for CLI argument parsing."""

    def test_parser_reset_to_after_required(self) -> None:
        from agentrelay.cli import build_parser

        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["reset-to", "graph.yaml"])

    def test_parser_reset_to_defaults(self) -> None:
        from agentrelay.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["reset-to", "graph.yaml", "--after", "task_a"])
        assert args.after == "task_a"
        assert args.yes is False

    def test_parser_reset_to_yes_flag(self) -> None:
        from agentrelay.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(
            ["reset-to", "graph.yaml", "--after", "task_a", "--yes"]
        )
        assert args.yes is True
