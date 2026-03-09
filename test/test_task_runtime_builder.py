"""Tests for task_runtime_builder: graph -> initial runtime map."""

from pathlib import Path

from agentrelay.task import AgentRole, Task
from agentrelay.task_graph import TaskGraph
from agentrelay.task_runtime import TaskStatus
from agentrelay.task_runtime.builder import TaskRuntimeBuilder


def _task(task_id: str, dependencies: tuple[Task, ...] = ()) -> Task:
    return Task(id=task_id, role=AgentRole.GENERIC, dependencies=dependencies)


def _graph() -> TaskGraph:
    task_a = _task("a")
    task_b = _task("b", dependencies=(task_a,))
    task_c = _task("c", dependencies=(task_a,))
    return TaskGraph.from_tasks([task_c, task_b, task_a], name="demo")


def test_from_graph_builds_runtime_for_each_task() -> None:
    graph = _graph()

    runtimes = TaskRuntimeBuilder.from_graph(graph)

    assert tuple(runtimes.keys()) == graph.task_ids()
    assert set(runtimes.keys()) == {"a", "b", "c"}


def test_runtime_task_object_identity_matches_graph() -> None:
    graph = _graph()

    runtimes = TaskRuntimeBuilder.from_graph(graph)

    for task_id in graph.task_ids():
        assert runtimes[task_id].task is graph.task(task_id)


def test_runtime_defaults_state_artifacts_and_agent() -> None:
    graph = _graph()
    runtimes = TaskRuntimeBuilder.from_graph(graph)

    for runtime in runtimes.values():
        assert runtime.state.status == TaskStatus.PENDING
        assert runtime.state.worktree_path is None
        assert runtime.state.branch_name is None
        assert runtime.state.error is None
        assert runtime.state.attempt_num == 0
        assert runtime.artifacts.pr_url is None
        assert runtime.artifacts.concerns == []
        assert runtime.agent is None


def test_runtime_mutation_isolated_per_task_state() -> None:
    graph = _graph()
    runtimes = TaskRuntimeBuilder.from_graph(graph)

    runtimes["a"].state.status = TaskStatus.RUNNING
    runtimes["a"].state.worktree_path = Path("/tmp/worktree-a")

    assert runtimes["b"].state.status == TaskStatus.PENDING
    assert runtimes["b"].state.worktree_path is None
    assert runtimes["c"].state.status == TaskStatus.PENDING
    assert runtimes["c"].state.worktree_path is None


def test_runtime_mutation_isolated_per_task_artifacts() -> None:
    graph = _graph()
    runtimes = TaskRuntimeBuilder.from_graph(graph)

    runtimes["a"].artifacts.concerns.append("first concern")
    runtimes["a"].artifacts.pr_url = "https://example.com/pr/1"

    assert runtimes["b"].artifacts.concerns == []
    assert runtimes["b"].artifacts.pr_url is None
    assert runtimes["c"].artifacts.concerns == []
    assert runtimes["c"].artifacts.pr_url is None


def test_from_graph_returns_fresh_runtime_objects_each_call() -> None:
    graph = _graph()

    runtimes_1 = TaskRuntimeBuilder.from_graph(graph)
    runtimes_2 = TaskRuntimeBuilder.from_graph(graph)

    for task_id in graph.task_ids():
        assert runtimes_1[task_id] is not runtimes_2[task_id]
        assert runtimes_1[task_id].state is not runtimes_2[task_id].state
        assert runtimes_1[task_id].artifacts is not runtimes_2[task_id].artifacts


def test_from_graph_runtimes_can_track_different_lifecycle_states() -> None:
    graph = _graph()
    runtimes = TaskRuntimeBuilder.from_graph(graph)

    runtimes["a"].state.status = TaskStatus.PR_MERGED
    runtimes["b"].state.status = TaskStatus.RUNNING
    runtimes["c"].state.status = TaskStatus.FAILED

    assert runtimes["a"].state.status == TaskStatus.PR_MERGED
    assert runtimes["b"].state.status == TaskStatus.RUNNING
    assert runtimes["c"].state.status == TaskStatus.FAILED
