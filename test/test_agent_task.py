import pytest

from agentrelaysmall.agent_task import (
    AgentRole,
    AgentTask,
    TaskPaths,
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
    assert state.agent_index is None


def test_task_state_agent_index_can_be_set():
    state = TaskState()
    state.agent_index = 3
    assert state.agent_index == 3


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
    assert AgentRole.SPEC_WRITER.value == "spec_writer"
    assert AgentRole.MERGER.value == "merger"


def test_agent_role_has_six_members():
    assert len(AgentRole) == 6


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


# ── AgentTask.model ───────────────────────────────────────────────────────────


def test_agent_task_default_model_is_none():
    task = AgentTask(id="t1", description="d")
    assert task.model is None


def test_agent_task_accepts_model():
    task = AgentTask(id="t1", description="d", model="claude-opus-4-6")
    assert task.model == "claude-opus-4-6"


def test_agent_task_model_is_immutable():
    task = AgentTask(id="t1", description="d", model="claude-sonnet-4-6")
    with pytest.raises(AttributeError):
        task.model = "claude-opus-4-6"  # type: ignore[misc]


# ── AgentTask.completion_gate ─────────────────────────────────────────────────


def test_agent_task_default_completion_gate_is_none():
    task = AgentTask(id="t1", description="d")
    assert task.completion_gate is None


def test_agent_task_accepts_completion_gate():
    task = AgentTask(id="t1", description="d", completion_gate="pixi run pytest")
    assert task.completion_gate == "pixi run pytest"


def test_agent_task_completion_gate_is_immutable():
    task = AgentTask(id="t1", description="d", completion_gate="pixi run pytest")
    with pytest.raises(AttributeError):
        task.completion_gate = "false"  # type: ignore[misc]


# ── AgentTask.task_params ─────────────────────────────────────────────────────


def test_agent_task_default_task_params_is_empty_dict():
    task = AgentTask(id="t1", description="d")
    assert task.task_params == {}


def test_agent_task_accepts_task_params():
    task = AgentTask(id="t1", description="d", task_params={"coverage_threshold": 95})
    assert task.task_params == {"coverage_threshold": 95}


def test_agent_task_task_params_is_immutable():
    task = AgentTask(id="t1", description="d", task_params={"coverage_threshold": 95})
    with pytest.raises(AttributeError):
        task.task_params = {}  # type: ignore[misc]


# ── AgentTask.review_model ────────────────────────────────────────────────────


def test_agent_task_default_review_model_is_none():
    task = AgentTask(id="t1", description="d")
    assert task.review_model is None


def test_agent_task_accepts_review_model():
    task = AgentTask(id="t1", description="d", review_model="claude-sonnet-4-6")
    assert task.review_model == "claude-sonnet-4-6"


def test_agent_task_review_model_is_immutable():
    task = AgentTask(id="t1", description="d", review_model="claude-sonnet-4-6")
    with pytest.raises(AttributeError):
        task.review_model = "claude-opus-4-6"  # type: ignore[misc]


# ── AgentTask.review_on_attempt ───────────────────────────────────────────────


def test_agent_task_default_review_on_attempt_is_one():
    task = AgentTask(id="t1", description="d")
    assert task.review_on_attempt == 1


def test_agent_task_accepts_review_on_attempt():
    task = AgentTask(id="t1", description="d", review_on_attempt=2)
    assert task.review_on_attempt == 2


def test_agent_task_review_on_attempt_is_immutable():
    task = AgentTask(id="t1", description="d", review_on_attempt=2)
    with pytest.raises(AttributeError):
        task.review_on_attempt = 3  # type: ignore[misc]


# ── AgentTask.max_gate_attempts ───────────────────────────────────────────────


def test_agent_task_default_max_gate_attempts_is_none():
    task = AgentTask(id="t1", description="d")
    assert task.max_gate_attempts is None


def test_agent_task_accepts_max_gate_attempts():
    task = AgentTask(id="t1", description="d", max_gate_attempts=3)
    assert task.max_gate_attempts == 3


def test_agent_task_max_gate_attempts_is_immutable():
    task = AgentTask(id="t1", description="d", max_gate_attempts=3)
    with pytest.raises(AttributeError):
        task.max_gate_attempts = 10  # type: ignore[misc]


# ── AgentTask.description optional ────────────────────────────────────────────


def test_agent_task_description_defaults_to_empty_string():
    task = AgentTask(id="t1")
    assert task.description == ""


def test_agent_task_accepts_description():
    task = AgentTask(id="t1", description="do something")
    assert task.description == "do something"


# ── AgentTask new roles ────────────────────────────────────────────────────────


def test_agent_task_accepts_spec_writer_role():
    task = AgentTask(id="t1", role=AgentRole.SPEC_WRITER)
    assert task.role == AgentRole.SPEC_WRITER


def test_agent_task_accepts_merger_role():
    task = AgentTask(id="t1", role=AgentRole.MERGER)
    assert task.role == AgentRole.MERGER


# ── TaskPaths ─────────────────────────────────────────────────────────────────


def test_task_paths_defaults():
    p = TaskPaths()
    assert p.src_paths == ()
    assert p.test_paths == ()
    assert p.spec_path is None


def test_task_paths_accepts_values():
    p = TaskPaths(
        src_paths=("src/foo.py", "src/bar.py"),
        test_paths=("tests/test_foo.py",),
        spec_path="specs/foo.md",
    )
    assert p.src_paths == ("src/foo.py", "src/bar.py")
    assert p.test_paths == ("tests/test_foo.py",)
    assert p.spec_path == "specs/foo.md"


def test_task_paths_is_frozen():
    p = TaskPaths(src_paths=("src/foo.py",))
    with pytest.raises(AttributeError):
        p.src_paths = ()  # type: ignore[misc]


# ── AgentTask.paths ────────────────────────────────────────────────────────────


def test_agent_task_paths_defaults_to_empty_task_paths():
    task = AgentTask(id="t1")
    assert task.paths == TaskPaths()
    assert task.paths.src_paths == ()
    assert task.paths.test_paths == ()
    assert task.paths.spec_path is None


def test_agent_task_accepts_paths():
    p = TaskPaths(src_paths=("src/foo.py",), test_paths=("tests/test_foo.py",))
    task = AgentTask(id="t1", paths=p)
    assert task.paths.src_paths == ("src/foo.py",)
    assert task.paths.test_paths == ("tests/test_foo.py",)


def test_agent_task_paths_is_immutable():
    task = AgentTask(id="t1", paths=TaskPaths(src_paths=("src/foo.py",)))
    with pytest.raises(AttributeError):
        task.paths = TaskPaths()  # type: ignore[misc]


def test_agent_task_each_instance_gets_own_paths():
    task_a = AgentTask(id="a")
    task_b = AgentTask(id="b")
    assert task_a.paths is not task_b.paths


# ── AgentTask.verbosity ────────────────────────────────────────────────────────


def test_agent_task_verbosity_defaults_to_none():
    task = AgentTask(id="t1")
    assert task.verbosity is None


def test_agent_task_accepts_verbosity():
    for level in ("standard", "detailed", "educational"):
        task = AgentTask(id="t1", verbosity=level)
        assert task.verbosity == level


def test_agent_task_verbosity_is_immutable():
    task = AgentTask(id="t1", verbosity="detailed")
    with pytest.raises(AttributeError):
        task.verbosity = "standard"  # type: ignore[misc]
