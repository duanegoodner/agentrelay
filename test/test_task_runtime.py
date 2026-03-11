"""Tests for agentrelay.v2.task_runtime: runtime state and addressing."""

from pathlib import Path

import pytest

from agentrelay.agent import AgentAddress, TmuxAddress
from agentrelay.task import AgentConfig, AgentRole, Task
from agentrelay.task_runtime import (
    TaskArtifacts,
    TaskRuntime,
    TaskState,
    TaskStatus,
)

# ── Tests for TaskState ──


class TestTaskState:
    """Tests for TaskState (operational state)."""

    def test_default_state(self) -> None:
        """TaskState defaults to PENDING with no paths or error."""
        state = TaskState()
        assert state.status == TaskStatus.PENDING
        assert state.worktree_path is None
        assert state.branch_name is None
        assert state.error is None
        assert state.attempt_num == 0

    def test_set_status(self) -> None:
        """TaskState status can be set."""
        state = TaskState(status=TaskStatus.RUNNING)
        assert state.status == TaskStatus.RUNNING

    def test_set_worktree_path(self) -> None:
        """TaskState can track worktree path."""
        state = TaskState(worktree_path=Path("/tmp/worktree-abc123"))
        assert state.worktree_path == Path("/tmp/worktree-abc123")

    def test_set_branch_name(self) -> None:
        """TaskState can track branch name."""
        state = TaskState(branch_name="feat/my-feature")
        assert state.branch_name == "feat/my-feature"

    def test_set_error(self) -> None:
        """TaskState can track error messages."""
        state = TaskState(error="Compilation failed")
        assert state.error == "Compilation failed"

    def test_set_attempt_num(self) -> None:
        """TaskState can track attempt number."""
        state = TaskState(attempt_num=2)
        assert state.attempt_num == 2

    def test_is_mutable(self) -> None:
        """TaskState can be modified."""
        state = TaskState()
        assert state.status == TaskStatus.PENDING

        state.status = TaskStatus.RUNNING
        assert state.status == TaskStatus.RUNNING

        state.attempt_num = 1
        assert state.attempt_num == 1

        state.error = "Some error"
        assert state.error == "Some error"

    def test_state_progression(self) -> None:
        """TaskState can be mutated to represent execution progress."""
        state = TaskState()
        assert state.status == TaskStatus.PENDING

        state.status = TaskStatus.RUNNING
        state.worktree_path = Path("/tmp/work-123")
        state.branch_name = "feat/task-123"
        assert state.status == TaskStatus.RUNNING
        assert state.worktree_path == Path("/tmp/work-123")

        state.status = TaskStatus.PR_CREATED
        state.attempt_num = 1
        assert state.status == TaskStatus.PR_CREATED
        assert state.attempt_num == 1


# ── Tests for TaskArtifacts ──


class TestTaskArtifacts:
    """Tests for TaskArtifacts (outputs and observations)."""

    def test_default_artifacts(self) -> None:
        """TaskArtifacts defaults to no PR and no concerns."""
        artifacts = TaskArtifacts()
        assert artifacts.pr_url is None
        assert artifacts.concerns == []

    def test_set_pr_url(self) -> None:
        """TaskArtifacts can track PR URL."""
        artifacts = TaskArtifacts(pr_url="https://github.com/user/repo/pull/123")
        assert artifacts.pr_url == "https://github.com/user/repo/pull/123"

    def test_set_concerns(self) -> None:
        """TaskArtifacts can track concerns."""
        concerns = ["Performance issue noted", "TODO: refactor"]
        artifacts = TaskArtifacts(concerns=concerns)
        assert artifacts.concerns == concerns

    def test_is_mutable(self) -> None:
        """TaskArtifacts can be modified."""
        artifacts = TaskArtifacts()
        assert artifacts.pr_url is None

        artifacts.pr_url = "https://github.com/user/repo/pull/42"
        assert artifacts.pr_url == "https://github.com/user/repo/pull/42"

    def test_concerns_accumulate(self) -> None:
        """Concerns can be appended to TaskArtifacts."""
        artifacts = TaskArtifacts()
        assert len(artifacts.concerns) == 0

        artifacts.concerns.append("First concern")
        assert len(artifacts.concerns) == 1

        artifacts.concerns.append("Second concern")
        assert len(artifacts.concerns) == 2
        assert artifacts.concerns == ["First concern", "Second concern"]

    def test_full_artifact_accumulation(self) -> None:
        """TaskArtifacts can accumulate outputs during execution."""
        artifacts = TaskArtifacts()

        # Agent observes a concern
        artifacts.concerns.append("Possible optimization")

        # Agent creates PR
        artifacts.pr_url = "https://github.com/org/repo/pull/99"

        # Agent notes another concern
        artifacts.concerns.append("Edge case not covered")

        assert artifacts.pr_url == "https://github.com/org/repo/pull/99"
        assert len(artifacts.concerns) == 2


# ── Tests for AgentAddress and TmuxAddress ──


class TestAgentAddress:
    """Tests for AgentAddress abstract base."""

    def test_cannot_instantiate_abstract_base(self) -> None:
        """AgentAddress is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            AgentAddress()  # type: ignore


class TestTmuxAddress:
    """Tests for TmuxAddress."""

    def test_basic_address(self) -> None:
        """TmuxAddress can be created with session and pane_id."""
        addr = TmuxAddress(session="agentrelay", pane_id="%1")
        assert addr.session == "agentrelay"
        assert addr.pane_id == "%1"

    def test_label_property(self) -> None:
        """TmuxAddress.label combines session and pane_id."""
        addr = TmuxAddress(session="agentrelay", pane_id="%3")
        assert addr.label == "agentrelay:%3"

    def test_label_different_ids(self) -> None:
        """TmuxAddress.label works with different pane IDs."""
        addr1 = TmuxAddress(session="work", pane_id="%0")
        addr2 = TmuxAddress(session="work", pane_id="%1")

        assert addr1.label == "work:%0"
        assert addr2.label == "work:%1"

    def test_label_different_sessions(self) -> None:
        """TmuxAddress.label works with different sessions."""
        addr1 = TmuxAddress(session="session1", pane_id="%0")
        addr2 = TmuxAddress(session="session2", pane_id="%0")

        assert addr1.label == "session1:%0"
        assert addr2.label == "session2:%0"

    def test_is_frozen(self) -> None:
        """TmuxAddress is immutable."""
        addr = TmuxAddress(session="agentrelay", pane_id="%1")
        with pytest.raises(AttributeError):
            addr.session = "new_session"  # type: ignore

    def test_is_hashable(self) -> None:
        """TmuxAddress can be hashed."""
        addr1 = TmuxAddress(session="agentrelay", pane_id="%1")
        addr2 = TmuxAddress(session="agentrelay", pane_id="%1")
        assert hash(addr1) == hash(addr2)

    def test_equality(self) -> None:
        """TmuxAddresses with same values are equal."""
        addr1 = TmuxAddress(session="agentrelay", pane_id="%1")
        addr2 = TmuxAddress(session="agentrelay", pane_id="%1")
        assert addr1 == addr2

    def test_inequality(self) -> None:
        """TmuxAddresses with different values are not equal."""
        addr1 = TmuxAddress(session="agentrelay", pane_id="%1")
        addr2 = TmuxAddress(session="agentrelay", pane_id="%2")
        assert addr1 != addr2

    def test_is_agent_address(self) -> None:
        """TmuxAddress is an AgentAddress."""
        addr = TmuxAddress(session="agentrelay", pane_id="%1")
        assert isinstance(addr, AgentAddress)


# ── Tests for TaskRuntime ──


class TestTaskRuntime:
    """Tests for TaskRuntime envelope."""

    def test_minimal_runtime(self) -> None:
        """TaskRuntime can be created with just a Task."""
        task = Task(id="my_task", role=AgentRole.GENERIC)
        runtime = TaskRuntime(task=task)

        assert runtime.task == task
        assert isinstance(runtime.state, TaskState)
        assert isinstance(runtime.artifacts, TaskArtifacts)
        assert runtime.artifacts.agent_address is None

    def test_default_state_created(self) -> None:
        """TaskRuntime creates default TaskState if not provided."""
        task = Task(id="task", role=AgentRole.GENERIC)
        runtime = TaskRuntime(task=task)

        assert runtime.state.status == TaskStatus.PENDING
        assert runtime.state.worktree_path is None
        assert runtime.state.attempt_num == 0

    def test_default_artifacts_created(self) -> None:
        """TaskRuntime creates default TaskArtifacts if not provided."""
        task = Task(id="task", role=AgentRole.GENERIC)
        runtime = TaskRuntime(task=task)

        assert runtime.artifacts.pr_url is None
        assert runtime.artifacts.concerns == []

    def test_custom_state(self) -> None:
        """TaskRuntime can use a provided TaskState."""
        task = Task(id="task", role=AgentRole.GENERIC)
        state = TaskState(status=TaskStatus.RUNNING, attempt_num=1)
        runtime = TaskRuntime(task=task, state=state)

        assert runtime.state == state
        assert runtime.state.status == TaskStatus.RUNNING

    def test_custom_artifacts(self) -> None:
        """TaskRuntime can use provided TaskArtifacts."""
        task = Task(id="task", role=AgentRole.GENERIC)
        artifacts = TaskArtifacts(pr_url="https://github.com/user/repo/pull/1")
        runtime = TaskRuntime(task=task, artifacts=artifacts)

        assert runtime.artifacts == artifacts
        assert runtime.artifacts.pr_url == "https://github.com/user/repo/pull/1"

    def test_agent_address_initially_none(self) -> None:
        """TaskArtifacts.agent_address is None until agent is launched."""
        task = Task(id="task", role=AgentRole.GENERIC)
        runtime = TaskRuntime(task=task)
        assert runtime.artifacts.agent_address is None

    def test_set_agent_address(self) -> None:
        """TaskArtifacts.agent_address can be set after creation."""
        task = Task(id="task", role=AgentRole.GENERIC)
        runtime = TaskRuntime(task=task)

        assert runtime.artifacts.agent_address is None
        address = TmuxAddress(session="agentrelay", pane_id="%1")
        runtime.artifacts.agent_address = address
        assert runtime.artifacts.agent_address is not None
        assert runtime.artifacts.agent_address.label == "agentrelay:%1"

    def test_modify_state_in_runtime(self) -> None:
        """TaskRuntime.state can be modified."""
        task = Task(id="task", role=AgentRole.GENERIC)
        runtime = TaskRuntime(task=task)

        runtime.state.status = TaskStatus.RUNNING
        runtime.state.worktree_path = Path("/tmp/work")
        runtime.state.attempt_num = 1

        assert runtime.state.status == TaskStatus.RUNNING
        assert runtime.state.worktree_path == Path("/tmp/work")
        assert runtime.state.attempt_num == 1

    def test_modify_artifacts_in_runtime(self) -> None:
        """TaskRuntime.artifacts can be modified."""
        task = Task(id="task", role=AgentRole.GENERIC)
        runtime = TaskRuntime(task=task)

        runtime.artifacts.pr_url = "https://github.com/user/repo/pull/123"
        runtime.artifacts.concerns.append("Performance note")

        assert runtime.artifacts.pr_url == "https://github.com/user/repo/pull/123"
        assert len(runtime.artifacts.concerns) == 1

    def test_full_execution_lifecycle(self) -> None:
        """TaskRuntime can track a full execution lifecycle."""
        # Create task and runtime
        task = Task(
            id="implement",
            role=AgentRole.IMPLEMENTER,
            completion_gate="pytest",
        )
        runtime = TaskRuntime(task=task)

        # Agent is launched
        runtime.artifacts.agent_address = TmuxAddress(
            session="agentrelay", pane_id="%2"
        )
        runtime.state.status = TaskStatus.RUNNING

        # Agent starts working
        runtime.state.worktree_path = Path("/tmp/worktree-abc")
        runtime.state.branch_name = "feat/impl"

        # Agent encounters an issue and notes it
        runtime.artifacts.concerns.append("Refactoring needed here")

        # Agent completes and creates PR
        runtime.artifacts.pr_url = "https://github.com/org/repo/pull/42"
        runtime.state.status = TaskStatus.PR_CREATED

        # Orchestrator merges the PR
        runtime.state.status = TaskStatus.PR_MERGED

        # Verify final state
        assert runtime.artifacts.agent_address.label == "agentrelay:%2"
        assert runtime.state.status == TaskStatus.PR_MERGED
        assert runtime.state.worktree_path == Path("/tmp/worktree-abc")
        assert runtime.state.branch_name == "feat/impl"
        assert len(runtime.artifacts.concerns) == 1
        assert runtime.artifacts.pr_url == "https://github.com/org/repo/pull/42"

    def test_task_spec_unchanged(self) -> None:
        """TaskRuntime holds frozen Task; spec doesn't change."""
        task = Task(
            id="task",
            role=AgentRole.IMPLEMENTER,
            description="Implementation task",
        )
        runtime = TaskRuntime(task=task)

        # Modify runtime state
        runtime.state.status = TaskStatus.RUNNING
        runtime.artifacts.pr_url = "https://github.com/user/repo/pull/1"

        # Task spec is unchanged
        assert runtime.task.id == "task"
        assert runtime.task.role == AgentRole.IMPLEMENTER
        assert runtime.task.description == "Implementation task"

    def test_multiple_runtimes_independent(self) -> None:
        """Multiple TaskRuntimes for the same Task are independent."""
        task = Task(id="task", role=AgentRole.GENERIC)
        runtime1 = TaskRuntime(task=task)
        runtime2 = TaskRuntime(task=task)

        runtime1.state.attempt_num = 1
        runtime2.state.attempt_num = 2

        assert runtime1.state.attempt_num == 1
        assert runtime2.state.attempt_num == 2

    def test_runtime_with_complex_task(self) -> None:
        """TaskRuntime works with complex Task specifications."""
        impl_task = Task(
            id="impl",
            role=AgentRole.IMPLEMENTER,
            dependencies=("spec", "tests"),
            completion_gate="pytest",
            primary_agent=AgentConfig(model="claude-opus-4-6"),
        )

        runtime = TaskRuntime(task=impl_task)

        assert runtime.task.id == "impl"
        assert len(runtime.task.dependencies) == 2
        assert runtime.task.completion_gate == "pytest"
        assert runtime.state.status == TaskStatus.PENDING
        assert runtime.artifacts.agent_address is None
