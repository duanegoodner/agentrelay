import pytest

from agentrelaysmall.agent_task import AgentTask, TaskState, TaskStatus


def test_task_status_values():
    assert TaskStatus.PENDING.value == "pending"
    assert TaskStatus.READY.value == "ready"
    assert TaskStatus.RUNNING.value == "running"
    assert TaskStatus.NEEDS_REVIEW.value == "needs_review"
    assert TaskStatus.DONE.value == "done"
    assert TaskStatus.FAILED.value == "failed"


def test_task_state_defaults():
    state = TaskState()
    assert state.status == TaskStatus.PENDING
    assert state.worktree_path is None
    assert state.branch_name is None
    assert state.tmux_session is None
    assert state.pane_id is None
    assert state.pr_url is None
    assert state.result is None
    assert state.error is None
    assert state.retries == 0


def test_task_state_is_mutable():
    state = TaskState()
    state.status = TaskStatus.RUNNING
    assert state.status == TaskStatus.RUNNING


def test_agent_task_basic_creation():
    task = AgentTask(id="task_001", description="do something")
    assert task.id == "task_001"
    assert task.description == "do something"
    assert task.dependencies == ()


def test_agent_task_with_dependencies():
    task = AgentTask(
        id="task_002", description="depends on 001", dependencies=("task_001",)
    )
    assert "task_001" in task.dependencies


def test_agent_task_default_state():
    task = AgentTask(id="task_001", description="d")
    assert task.state.status == TaskStatus.PENDING


def test_agent_task_state_is_mutable():
    task = AgentTask(id="task_001", description="d")
    task.state.status = TaskStatus.RUNNING
    assert task.state.status == TaskStatus.RUNNING


def test_agent_task_identity_is_immutable():
    task = AgentTask(id="task_001", description="d")
    with pytest.raises(AttributeError):
        task.id = "other"  # type: ignore[misc]


def test_agent_task_each_instance_gets_own_state():
    task_a = AgentTask(id="a", description="a")
    task_b = AgentTask(id="b", description="b")
    task_a.state.status = TaskStatus.DONE
    assert task_b.state.status == TaskStatus.PENDING
