"""Tests for task_graph: immutable DAG structure and pure graph queries."""

import pytest

from agentrelay.task import AgentRole, Task
from agentrelay.task_graph import TaskGraph


def _task(task_id: str, dependencies: tuple[str, ...] = (), desc: str = "") -> Task:
    return Task(
        id=task_id,
        role=AgentRole.GENERIC,
        description=desc or None,
        dependencies=dependencies,
    )


def test_graph_basic_queries_and_topological_order() -> None:
    task_a = _task("a")
    task_b = _task("b", dependencies=("a",))
    task_c = _task("c", dependencies=("a",))

    graph = TaskGraph.from_tasks([task_c, task_b, task_a], name="demo")

    assert graph.name == "demo"
    assert graph.task_ids() == ("a", "b", "c")
    assert graph.topological_order() == ("a", "b", "c")
    assert graph.task("b") == task_b
    assert graph.dependency_ids("a") == ()
    assert graph.dependency_ids("b") == ("a",)
    assert graph.dependent_ids("a") == ("b", "c")
    assert graph.roots() == ("a",)
    assert graph.leaves() == ("b", "c")


def test_topological_order_is_deterministic_for_same_graph() -> None:
    task_a = _task("a")
    task_b = _task("b", dependencies=("a",))
    task_c = _task("c", dependencies=("a",))
    task_d = _task("d", dependencies=("b", "c"))

    graph_1 = TaskGraph.from_tasks([task_d, task_c, task_b, task_a])
    graph_2 = TaskGraph.from_tasks([task_a, task_b, task_c, task_d])

    assert graph_1.topological_order() == graph_2.topological_order()
    assert graph_1.topological_order() == ("a", "b", "c", "d")


def test_ready_ids_is_pure_from_completed_and_running_sets() -> None:
    task_a = _task("a")
    task_b = _task("b", dependencies=("a",))
    task_c = _task("c", dependencies=("a",))

    graph = TaskGraph.from_tasks([task_a, task_b, task_c])

    assert graph.ready_ids(completed_ids=()) == ("a",)
    assert graph.ready_ids(completed_ids={"a"}) == ("b", "c")
    assert graph.ready_ids(completed_ids={"a"}, running_ids={"b"}) == ("c",)


def test_missing_dependency_raises() -> None:
    task_a = _task("a", dependencies=("missing",))

    with pytest.raises(ValueError, match="Unknown dependency id\\(s\\): missing"):
        TaskGraph.from_tasks([task_a])


def test_self_dependency_raises() -> None:
    task_a = _task("a", dependencies=("a",))

    with pytest.raises(ValueError, match="self-dependency"):
        TaskGraph.from_tasks([task_a])


def test_cycle_raises_with_cycle_path() -> None:
    task_a = _task("a", dependencies=("b",))
    task_b = _task("b", dependencies=("c",))
    task_c = _task("c", dependencies=("a",))

    with pytest.raises(ValueError, match="Task graph contains a cycle:"):
        TaskGraph.from_tasks([task_a, task_b, task_c])


def test_constructor_rejects_key_id_mismatch() -> None:
    task_a = _task("a")

    with pytest.raises(ValueError, match="does not match task.id"):
        TaskGraph(tasks_by_id={"not-a": task_a})


def test_ready_ids_rejects_unknown_ids() -> None:
    task_a = _task("a")
    graph = TaskGraph.from_tasks([task_a])

    with pytest.raises(ValueError, match="completed_ids contains unknown"):
        graph.ready_ids(completed_ids={"nope"})
