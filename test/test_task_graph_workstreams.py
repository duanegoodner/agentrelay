"""Tests for TaskGraph workstream metadata and validation behavior."""

import pytest

from agentrelay.task import AgentRole, Task
from agentrelay.task_graph import TaskGraph
from agentrelay.workstream import WorkstreamSpec


def _task(
    task_id: str,
    dependencies: tuple[str, ...] = (),
    workstream_id: str = "default",
) -> Task:
    return Task(
        id=task_id,
        role=AgentRole.GENERIC,
        dependencies=dependencies,
        workstream_id=workstream_id,
    )


def _workstream(
    workstream_id: str,
    parent_workstream_id: str | None = None,
) -> WorkstreamSpec:
    return WorkstreamSpec(
        id=workstream_id,
        parent_workstream_id=parent_workstream_id,
    )


def test_default_workstream_is_implicit_when_not_provided() -> None:
    task_a = _task("a")
    task_b = _task("b", dependencies=("a",))

    graph = TaskGraph.from_tasks([task_b, task_a])

    assert graph.workstream_ids() == ("default",)
    assert graph.workstream("default") == WorkstreamSpec(id="default")
    assert graph.tasks_in_workstream("default") == ("a", "b")
    assert graph.child_workstream_ids("default") == ()


def test_custom_task_workstream_requires_explicit_workstream_specs() -> None:
    task_a = _task("a", workstream_id="feature_a")

    with pytest.raises(
        ValueError,
        match="Unknown workstream id\\(s\\) referenced by tasks: feature_a",
    ):
        TaskGraph.from_tasks([task_a])


def test_explicit_workstreams_are_exposed_by_queries() -> None:
    task_a = _task("a", workstream_id="feature_a")
    task_b = _task("b", dependencies=("a",), workstream_id="feature_b")
    task_c = _task("c", dependencies=("a",), workstream_id="feature_a")

    graph = TaskGraph.from_tasks(
        [task_c, task_b, task_a],
        workstreams=[_workstream("feature_b"), _workstream("feature_a")],
    )

    assert graph.workstream_ids() == ("feature_a", "feature_b")
    assert graph.tasks_in_workstream("feature_a") == ("a", "c")
    assert graph.tasks_in_workstream("feature_b") == ("b",)


def test_unknown_workstream_id_queries_raise() -> None:
    graph = TaskGraph.from_tasks([_task("a")])

    with pytest.raises(KeyError, match="Unknown workstream id"):
        graph.workstream("missing")

    with pytest.raises(KeyError, match="Unknown workstream id"):
        graph.tasks_in_workstream("missing")

    with pytest.raises(KeyError, match="Unknown workstream id"):
        graph.child_workstream_ids("missing")


def test_parent_workstream_must_exist() -> None:
    task_a = _task("a", workstream_id="child")
    child = _workstream("child", parent_workstream_id="missing-parent")

    with pytest.raises(
        ValueError,
        match="references unknown parent_workstream_id 'missing-parent'",
    ):
        TaskGraph.from_tasks([task_a], workstreams=[child])


def test_workstream_parent_cycle_raises() -> None:
    task_a = _task("a", workstream_id="a")
    stream_a = _workstream("a", parent_workstream_id="b")
    stream_b = _workstream("b", parent_workstream_id="a")

    with pytest.raises(ValueError, match="Workstream hierarchy contains a cycle:"):
        TaskGraph.from_tasks([task_a], workstreams=[stream_a, stream_b])


def test_workstream_depth_greater_than_one_raises() -> None:
    task_c = _task("c", workstream_id="c")
    stream_a = _workstream("a")
    stream_b = _workstream("b", parent_workstream_id="a")
    stream_c = _workstream("c", parent_workstream_id="b")

    with pytest.raises(
        ValueError,
        match="exceeds maximum supported depth of 1",
    ):
        TaskGraph.from_tasks([task_c], workstreams=[stream_a, stream_b, stream_c])


def test_workstream_depth_can_be_extended_with_max_workstream_depth() -> None:
    task_c = _task("c", workstream_id="c")
    stream_a = _workstream("a")
    stream_b = _workstream("b", parent_workstream_id="a")
    stream_c = _workstream("c", parent_workstream_id="b")

    graph = TaskGraph.from_tasks(
        [task_c],
        workstreams=[stream_a, stream_b, stream_c],
        max_workstream_depth=2,
    )

    assert graph.max_workstream_depth == 2
    assert graph.child_workstream_ids("a") == ("b",)
    assert graph.child_workstream_ids("b") == ("c",)


def test_max_workstream_depth_less_than_one_raises() -> None:
    task_a = _task("a")

    with pytest.raises(ValueError, match="max_workstream_depth must be >= 1"):
        TaskGraph.from_tasks([task_a], max_workstream_depth=0)


def test_child_workstream_ids_are_sorted() -> None:
    task_root = _task("root", workstream_id="a")
    stream_a = _workstream("a")
    stream_a2 = _workstream("a.2", parent_workstream_id="a")
    stream_a1 = _workstream("a.1", parent_workstream_id="a")

    graph = TaskGraph.from_tasks(
        [task_root],
        workstreams=[stream_a2, stream_a, stream_a1],
    )

    assert graph.child_workstream_ids("a") == ("a.1", "a.2")


def test_duplicate_workstream_ids_in_from_tasks_raise() -> None:
    task_a = _task("a")

    with pytest.raises(ValueError, match="Duplicate workstream id 'dup'"):
        TaskGraph.from_tasks(
            [task_a],
            workstreams=[_workstream("dup"), _workstream("dup")],
        )


def test_constructor_rejects_workstream_key_id_mismatch() -> None:
    task_a = _task("a")

    with pytest.raises(ValueError, match="does not match WorkstreamSpec.id"):
        TaskGraph(
            tasks_by_id={"a": task_a},
            workstreams_by_id={"not-a": _workstream("a")},
        )
