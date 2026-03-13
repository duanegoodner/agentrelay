"""Tests for task runtime read-only view protocols."""

from collections.abc import Sequence
from pathlib import Path

from agentrelay.agent import TmuxAddress
from agentrelay.task import AgentConfig, AgentRole, Task
from agentrelay.task_runtime import (
    TaskArtifacts,
    TaskArtifactsView,
    TaskRuntime,
    TaskRuntimeView,
    TaskState,
    TaskStateView,
    TaskStatus,
)

# ── Tests for TaskStateView ──


class TestTaskStateView:
    """Tests for TaskStateView protocol."""

    def test_taskstate_satisfies_protocol(self) -> None:
        """TaskState structurally satisfies TaskStateView."""
        assert isinstance(TaskState(), TaskStateView)

    def test_all_fields_readable_through_view(self) -> None:
        """All TaskState fields are accessible through the view."""
        state = TaskState(
            status=TaskStatus.RUNNING,
            worktree_path=Path("/tmp/work"),
            branch_name="feat/x",
            error="oops",
            attempt_num=3,
        )
        view: TaskStateView = state
        assert view.status == TaskStatus.RUNNING
        assert view.worktree_path == Path("/tmp/work")
        assert view.branch_name == "feat/x"
        assert view.error == "oops"
        assert view.attempt_num == 3

    def test_default_fields_through_view(self) -> None:
        """Default TaskState values are accessible through the view."""
        view: TaskStateView = TaskState()
        assert view.status == TaskStatus.PENDING
        assert view.worktree_path is None
        assert view.branch_name is None
        assert view.error is None
        assert view.attempt_num == 0


# ── Tests for TaskArtifactsView ──


class TestTaskArtifactsView:
    """Tests for TaskArtifactsView protocol."""

    def test_taskartifacts_satisfies_protocol(self) -> None:
        """TaskArtifacts structurally satisfies TaskArtifactsView."""
        assert isinstance(TaskArtifacts(), TaskArtifactsView)

    def test_all_fields_readable_through_view(self) -> None:
        """All TaskArtifacts fields are accessible through the view."""
        addr = TmuxAddress(session="agentrelay", pane_id="%1")
        artifacts = TaskArtifacts(
            pr_url="https://github.com/org/repo/pull/42",
            concerns=["concern1", "concern2"],
            agent_address=addr,
        )
        view: TaskArtifactsView = artifacts
        assert view.pr_url == "https://github.com/org/repo/pull/42"
        assert view.agent_address is addr
        assert len(view.concerns) == 2

    def test_concerns_is_sequence(self) -> None:
        """Concerns viewed through the protocol are typed as Sequence."""
        artifacts = TaskArtifacts(concerns=["a", "b"])
        view: TaskArtifactsView = artifacts
        assert isinstance(view.concerns, Sequence)

    def test_default_fields_through_view(self) -> None:
        """Default TaskArtifacts values are accessible through the view."""
        view: TaskArtifactsView = TaskArtifacts()
        assert view.pr_url is None
        assert view.concerns == []
        assert view.agent_address is None


# ── Tests for TaskRuntimeView ──


class TestTaskRuntimeView:
    """Tests for TaskRuntimeView protocol."""

    def test_taskruntime_satisfies_protocol(self) -> None:
        """TaskRuntime structurally satisfies TaskRuntimeView."""
        task = Task(id="t", role=AgentRole.GENERIC)
        runtime = TaskRuntime(task=task)
        assert isinstance(runtime, TaskRuntimeView)

    def test_nested_state_satisfies_view(self) -> None:
        """TaskRuntime.state satisfies TaskStateView through the view."""
        task = Task(id="t", role=AgentRole.GENERIC)
        view: TaskRuntimeView = TaskRuntime(task=task)
        assert isinstance(view.state, TaskStateView)

    def test_nested_artifacts_satisfies_view(self) -> None:
        """TaskRuntime.artifacts satisfies TaskArtifactsView through the view."""
        task = Task(id="t", role=AgentRole.GENERIC)
        view: TaskRuntimeView = TaskRuntime(task=task)
        assert isinstance(view.artifacts, TaskArtifactsView)

    def test_task_accessible_through_view(self) -> None:
        """TaskRuntime.task is accessible through the view."""
        task = Task(id="impl", role=AgentRole.IMPLEMENTER)
        view: TaskRuntimeView = TaskRuntime(task=task)
        assert view.task.id == "impl"
        assert view.task.role == AgentRole.IMPLEMENTER

    def test_full_state_readable_through_view(self) -> None:
        """A fully populated TaskRuntime is readable through the view."""
        task = Task(
            id="impl",
            role=AgentRole.IMPLEMENTER,
            primary_agent=AgentConfig(model="claude-opus-4-6"),
        )
        runtime = TaskRuntime(
            task=task,
            state=TaskState(
                status=TaskStatus.PR_CREATED,
                worktree_path=Path("/tmp/wt"),
                branch_name="feat/impl",
                attempt_num=2,
            ),
            artifacts=TaskArtifacts(
                pr_url="https://github.com/org/repo/pull/99",
                concerns=["edge case"],
                agent_address=TmuxAddress(session="agentrelay", pane_id="%3"),
            ),
        )
        view: TaskRuntimeView = runtime

        assert view.task.id == "impl"
        assert view.state.status == TaskStatus.PR_CREATED
        assert view.state.worktree_path == Path("/tmp/wt")
        assert view.state.branch_name == "feat/impl"
        assert view.state.attempt_num == 2
        assert view.artifacts.pr_url == "https://github.com/org/repo/pull/99"
        assert view.artifacts.concerns == ["edge case"]
        assert view.artifacts.agent_address is not None
        assert view.artifacts.agent_address.label == "agentrelay:%3"
