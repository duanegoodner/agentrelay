import pytest

from agentrelaysmall.agent_task import (
    AgentRole,
    AgentTask,
    TaskGroup,
    TaskState,
    TaskStatus,
)


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
    dep = AgentTask(id="task_001", description="the dep")
    task = AgentTask(id="task_002", description="depends on 001", dependencies=(dep,))
    assert "task_001" in task.dependency_ids


def test_agent_task_dependency_ids_returns_ids_as_strings():
    dep_a = AgentTask(id="a", description="a")
    dep_b = AgentTask(id="b", description="b")
    task = AgentTask(id="c", description="c", dependencies=(dep_a, dep_b))
    assert task.dependency_ids == ("a", "b")


def test_agent_task_dependency_ids_empty_when_no_deps():
    task = AgentTask(id="task_001", description="d")
    assert task.dependency_ids == ()


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


# ── AgentRole ─────────────────────────────────────────────────────────────────


def test_agent_role_values():
    assert AgentRole.GENERIC.value == "generic"
    assert AgentRole.TEST_WRITER.value == "test_writer"
    assert AgentRole.TEST_REVIEWER.value == "test_reviewer"
    assert AgentRole.IMPLEMENTER.value == "implementer"


def test_agent_role_has_four_members():
    assert len(AgentRole) == 4


# ── AgentTask.role ────────────────────────────────────────────────────────────


def test_agent_task_default_role_is_generic():
    task = AgentTask(id="t1", description="d")
    assert task.role == AgentRole.GENERIC


def test_agent_task_accepts_explicit_role():
    task = AgentTask(id="t1", description="d", role=AgentRole.TEST_WRITER)
    assert task.role == AgentRole.TEST_WRITER


def test_agent_task_accepts_all_non_generic_roles():
    for role in (AgentRole.TEST_WRITER, AgentRole.TEST_REVIEWER, AgentRole.IMPLEMENTER):
        task = AgentTask(id="t", description="d", role=role)
        assert task.role == role


def test_agent_task_role_is_immutable():
    task = AgentTask(id="t1", description="d", role=AgentRole.TEST_WRITER)
    with pytest.raises(AttributeError):
        task.role = AgentRole.GENERIC  # type: ignore[misc]


def test_agent_task_role_does_not_affect_state_independence():
    task_a = AgentTask(id="a", description="a", role=AgentRole.TEST_WRITER)
    task_b = AgentTask(id="b", description="b", role=AgentRole.IMPLEMENTER)
    task_a.state.status = TaskStatus.DONE
    assert task_b.state.status == TaskStatus.PENDING


# ── AgentTask.tdd_group_id ────────────────────────────────────────────────────


def test_agent_task_default_tdd_group_id_is_none():
    task = AgentTask(id="t1", description="d")
    assert task.tdd_group_id is None


def test_agent_task_accepts_tdd_group_id():
    task = AgentTask(id="t1", description="d", tdd_group_id="my_group")
    assert task.tdd_group_id == "my_group"


def test_agent_task_tdd_group_id_is_immutable():
    task = AgentTask(id="t1", description="d", tdd_group_id="my_group")
    with pytest.raises(AttributeError):
        task.tdd_group_id = "other"  # type: ignore[misc]


# ── TaskGroup ABC ─────────────────────────────────────────────────────────────


def test_task_group_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        TaskGroup(id="g", description="d")  # type: ignore[abstract]
