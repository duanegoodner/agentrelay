"""Tests for workstream runtime read-only view protocols."""

from collections.abc import Sequence
from pathlib import Path

from agentrelay.workstream import (
    WorkstreamArtifacts,
    WorkstreamArtifactsView,
    WorkstreamRuntime,
    WorkstreamRuntimeView,
    WorkstreamSpec,
    WorkstreamState,
    WorkstreamStateView,
    WorkstreamStatus,
)

# ── Tests for WorkstreamStateView ──


class TestWorkstreamStateView:
    """Tests for WorkstreamStateView protocol."""

    def test_workstreamstate_satisfies_protocol(self) -> None:
        """WorkstreamState structurally satisfies WorkstreamStateView."""
        assert isinstance(WorkstreamState(), WorkstreamStateView)

    def test_all_fields_readable_through_view(self) -> None:
        """All WorkstreamState fields are accessible through the view."""
        state = WorkstreamState(
            status=WorkstreamStatus.ACTIVE,
            worktree_path=Path("/tmp/ws-work"),
            branch_name="ws/feature",
            error="something wrong",
            active_task_id="task_1",
        )
        view: WorkstreamStateView = state
        assert view.status == WorkstreamStatus.ACTIVE
        assert view.worktree_path == Path("/tmp/ws-work")
        assert view.branch_name == "ws/feature"
        assert view.error == "something wrong"
        assert view.active_task_id == "task_1"

    def test_default_fields_through_view(self) -> None:
        """Default WorkstreamState values are accessible through the view."""
        view: WorkstreamStateView = WorkstreamState()
        assert view.status == WorkstreamStatus.PENDING
        assert view.worktree_path is None
        assert view.branch_name is None
        assert view.error is None
        assert view.active_task_id is None


# ── Tests for WorkstreamArtifactsView ──


class TestWorkstreamArtifactsView:
    """Tests for WorkstreamArtifactsView protocol."""

    def test_workstreamartifacts_satisfies_protocol(self) -> None:
        """WorkstreamArtifacts structurally satisfies WorkstreamArtifactsView."""
        assert isinstance(WorkstreamArtifacts(), WorkstreamArtifactsView)

    def test_all_fields_readable_through_view(self) -> None:
        """All WorkstreamArtifacts fields are accessible through the view."""
        artifacts = WorkstreamArtifacts(
            merge_pr_url="https://github.com/org/repo/pull/10",
            concerns=["concern1"],
        )
        view: WorkstreamArtifactsView = artifacts
        assert view.merge_pr_url == "https://github.com/org/repo/pull/10"
        assert len(view.concerns) == 1

    def test_concerns_is_sequence(self) -> None:
        """Concerns viewed through the protocol are typed as Sequence."""
        artifacts = WorkstreamArtifacts(concerns=["a", "b"])
        view: WorkstreamArtifactsView = artifacts
        assert isinstance(view.concerns, Sequence)

    def test_default_fields_through_view(self) -> None:
        """Default WorkstreamArtifacts values are accessible through the view."""
        view: WorkstreamArtifactsView = WorkstreamArtifacts()
        assert view.merge_pr_url is None
        assert view.concerns == []


# ── Tests for WorkstreamRuntimeView ──


class TestWorkstreamRuntimeView:
    """Tests for WorkstreamRuntimeView protocol."""

    def test_workstreamruntime_satisfies_protocol(self) -> None:
        """WorkstreamRuntime structurally satisfies WorkstreamRuntimeView."""
        spec = WorkstreamSpec(id="ws1")
        runtime = WorkstreamRuntime(spec=spec)
        assert isinstance(runtime, WorkstreamRuntimeView)

    def test_nested_state_satisfies_view(self) -> None:
        """WorkstreamRuntime.state satisfies WorkstreamStateView through the view."""
        spec = WorkstreamSpec(id="ws1")
        view: WorkstreamRuntimeView = WorkstreamRuntime(spec=spec)
        assert isinstance(view.state, WorkstreamStateView)

    def test_nested_artifacts_satisfies_view(self) -> None:
        """WorkstreamRuntime.artifacts satisfies WorkstreamArtifactsView through the view."""
        spec = WorkstreamSpec(id="ws1")
        view: WorkstreamRuntimeView = WorkstreamRuntime(spec=spec)
        assert isinstance(view.artifacts, WorkstreamArtifactsView)

    def test_spec_accessible_through_view(self) -> None:
        """WorkstreamRuntime.spec is accessible through the view."""
        spec = WorkstreamSpec(id="ws1", base_branch="develop")
        view: WorkstreamRuntimeView = WorkstreamRuntime(spec=spec)
        assert view.spec.id == "ws1"
        assert view.spec.base_branch == "develop"

    def test_full_state_readable_through_view(self) -> None:
        """A fully populated WorkstreamRuntime is readable through the view."""
        spec = WorkstreamSpec(id="ws1", parent_workstream_id="parent")
        runtime = WorkstreamRuntime(
            spec=spec,
            state=WorkstreamState(
                status=WorkstreamStatus.ACTIVE,
                worktree_path=Path("/tmp/ws"),
                branch_name="ws/feature",
                active_task_id="task_2",
            ),
            artifacts=WorkstreamArtifacts(
                merge_pr_url="https://github.com/org/repo/pull/55",
                concerns=["performance"],
            ),
        )
        view: WorkstreamRuntimeView = runtime

        assert view.spec.id == "ws1"
        assert view.spec.parent_workstream_id == "parent"
        assert view.state.status == WorkstreamStatus.ACTIVE
        assert view.state.worktree_path == Path("/tmp/ws")
        assert view.state.branch_name == "ws/feature"
        assert view.state.active_task_id == "task_2"
        assert view.artifacts.merge_pr_url == "https://github.com/org/repo/pull/55"
        assert view.artifacts.concerns == ["performance"]
