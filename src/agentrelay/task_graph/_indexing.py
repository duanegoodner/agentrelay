"""Index-building and ordering helpers for TaskGraph.

This module contains pure functions that build task/workstream indexes and
compute topological order for ``agentrelay.task_graph.TaskGraph``.
"""

from __future__ import annotations

from bisect import insort
from collections.abc import Mapping

from agentrelay.task import Task
from agentrelay.workstream import WorkstreamSpec


def build_dependency_ids(
    tasks_by_id: Mapping[str, Task],
) -> dict[str, tuple[str, ...]]:
    """Build dependency ID index and validate per-task dependency declarations.

    Args:
        tasks_by_id: Canonical mapping of graph task IDs to tasks.

    Raises:
        ValueError: If a task depends on itself or repeats dependency IDs.

    Returns:
        dict[str, tuple[str, ...]]: Dependency IDs keyed by task ID.
    """
    dependency_ids: dict[str, tuple[str, ...]] = {}
    for task_id, task in tasks_by_id.items():
        dep_ids = task.dependencies
        if task_id in dep_ids:
            raise ValueError(f"Task '{task_id}' has a self-dependency.")
        if len(dep_ids) != len(set(dep_ids)):
            raise ValueError(f"Task '{task_id}' has duplicate dependency IDs.")
        dependency_ids[task_id] = dep_ids
    return dependency_ids


def build_dependent_ids(
    tasks_by_id: Mapping[str, Task],
    dependency_ids: Mapping[str, tuple[str, ...]],
) -> dict[str, tuple[str, ...]]:
    """Build reverse dependency index.

    Args:
        tasks_by_id: Canonical mapping of graph task IDs to tasks.
        dependency_ids: Dependency ID index keyed by task ID.

    Returns:
        dict[str, tuple[str, ...]]: Dependent IDs keyed by task ID.
    """
    dependents: dict[str, list[str]] = {task_id: [] for task_id in tasks_by_id}
    for task_id, dep_ids in dependency_ids.items():
        for dep_id in dep_ids:
            dependents[dep_id].append(task_id)
    return {task_id: tuple(sorted(ids)) for task_id, ids in dependents.items()}


def topological_order_or_raise(
    dependency_ids: Mapping[str, tuple[str, ...]],
    dependent_ids: Mapping[str, tuple[str, ...]],
) -> tuple[str, ...]:
    """Compute stable topological order or raise on cyclic graphs.

    Args:
        dependency_ids: Dependency ID index keyed by task ID.
        dependent_ids: Reverse dependency ID index keyed by task ID.

    Raises:
        ValueError: If the graph contains one or more cycles.

    Returns:
        tuple[str, ...]: Stable dependency-first topological order.
    """
    in_degree = {task_id: len(dep_ids) for task_id, dep_ids in dependency_ids.items()}
    queue = sorted(task_id for task_id, degree in in_degree.items() if degree == 0)
    ordered: list[str] = []

    while queue:
        task_id = queue.pop(0)
        ordered.append(task_id)
        for dependent_id in dependent_ids[task_id]:
            in_degree[dependent_id] -= 1
            if in_degree[dependent_id] == 0:
                insort(queue, dependent_id)

    if len(ordered) == len(dependency_ids):
        return tuple(ordered)

    cycle = _find_cycle(dependency_ids)
    if cycle:
        raise ValueError(f"Task graph contains a cycle: {' -> '.join(cycle)}")
    raise ValueError("Task graph contains one or more cycles.")


def build_task_ids_by_workstream(
    tasks_by_id: Mapping[str, Task],
    topological_order: tuple[str, ...],
    workstreams_by_id: Mapping[str, WorkstreamSpec],
) -> dict[str, tuple[str, ...]]:
    """Build a topological-order task ID index for each workstream.

    Args:
        tasks_by_id: Canonical mapping of graph task IDs to tasks.
        topological_order: Graph topological task ID order.
        workstreams_by_id: Canonical mapping of workstream IDs to specs.

    Returns:
        dict[str, tuple[str, ...]]: Task IDs keyed by workstream ID.
    """
    grouped: dict[str, list[str]] = {
        workstream_id: [] for workstream_id in workstreams_by_id
    }
    for task_id in topological_order:
        grouped[tasks_by_id[task_id].workstream_id].append(task_id)
    return {
        workstream_id: tuple(task_ids) for workstream_id, task_ids in grouped.items()
    }


def build_child_workstream_ids(
    workstreams_by_id: Mapping[str, WorkstreamSpec],
) -> dict[str, tuple[str, ...]]:
    """Build an index of child workstream IDs for each workstream.

    Args:
        workstreams_by_id: Canonical mapping of workstream IDs to specs.

    Returns:
        dict[str, tuple[str, ...]]: Child IDs keyed by parent workstream ID.
    """
    children: dict[str, list[str]] = {
        workstream_id: [] for workstream_id in workstreams_by_id
    }
    for workstream in workstreams_by_id.values():
        parent_id = workstream.parent_workstream_id
        if parent_id is not None:
            children[parent_id].append(workstream.id)
    return {
        workstream_id: tuple(sorted(child_ids))
        for workstream_id, child_ids in children.items()
    }


def _find_cycle(
    dependency_ids: Mapping[str, tuple[str, ...]],
) -> tuple[str, ...] | None:
    """Find one cycle path in a dependency graph if present.

    Args:
        dependency_ids: Dependency ID index keyed by task ID.

    Returns:
        tuple[str, ...] | None: A cycle path ending at its starting node, or
            ``None`` if no cycle is found.
    """
    unvisited = 0
    visiting = 1
    done = 2
    state: dict[str, int] = {task_id: unvisited for task_id in dependency_ids}
    stack: list[str] = []
    stack_index: dict[str, int] = {}

    def dfs(task_id: str) -> tuple[str, ...] | None:
        state[task_id] = visiting
        stack_index[task_id] = len(stack)
        stack.append(task_id)

        for dep_id in dependency_ids[task_id]:
            dep_state = state[dep_id]
            if dep_state == unvisited:
                cycle = dfs(dep_id)
                if cycle is not None:
                    return cycle
            elif dep_state == visiting:
                start = stack_index[dep_id]
                return tuple(stack[start:] + [dep_id])

        stack.pop()
        del stack_index[task_id]
        state[task_id] = done
        return None

    for task_id in sorted(dependency_ids):
        if state[task_id] == unvisited:
            cycle = dfs(task_id)
            if cycle is not None:
                return cycle
    return None
