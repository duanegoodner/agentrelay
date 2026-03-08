"""Task graph model for orchestration planning.

This module defines an immutable :class:`TaskGraph` for static task dependency
structure (a directed acyclic graph of :class:`agentrelay.task.Task` values).
It intentionally excludes runtime execution state, scheduling state transitions,
and side-effectful orchestration operations (for example git, tmux, or signal I/O).
"""

from __future__ import annotations

from bisect import insort
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Optional

from agentrelay.task import Task


@dataclass(frozen=True)
class TaskGraph:
    """Immutable DAG of :class:`Task` specifications keyed by task ID.

    Attributes:
        name: Optional human-readable graph name.
        _tasks_by_id: Canonical task objects keyed by task ID.
        _dependency_ids: Dependency IDs for each task ID.
        _dependent_ids: Reverse dependency IDs for each task ID.
        _topological_order: Dependency-first stable task ordering.
    """

    name: Optional[str]
    _tasks_by_id: Mapping[str, Task]
    _dependency_ids: Mapping[str, tuple[str, ...]]
    _dependent_ids: Mapping[str, tuple[str, ...]]
    _topological_order: tuple[str, ...]

    def __init__(self, tasks_by_id: Mapping[str, Task], name: Optional[str] = None):
        """Initialize and validate an immutable task graph.

        Args:
            tasks_by_id: Mapping of task IDs to canonical :class:`Task` objects.
                Each key must match its corresponding ``Task.id``.
            name: Optional human-readable name for this graph.

        Raises:
            ValueError: If the graph is empty, contains mismatched key/ID pairs,
                contains conflicting task definitions for a shared task ID, contains
                invalid dependency declarations, or contains dependency cycles.
        """
        if not tasks_by_id:
            raise ValueError("TaskGraph requires at least one task.")

        canonical = dict(tasks_by_id)
        for key, task in canonical.items():
            if key != task.id:
                raise ValueError(
                    f"TaskGraph key '{key}' does not match task.id '{task.id}'."
                )

        _validate_task_identity_consistency(canonical)
        dependency_ids = _build_dependency_ids(canonical)
        _validate_dependencies_exist(canonical, dependency_ids)
        dependent_ids = _build_dependent_ids(canonical, dependency_ids)
        topo = _topological_order_or_raise(dependency_ids, dependent_ids)

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "_tasks_by_id", MappingProxyType(canonical))
        object.__setattr__(self, "_dependency_ids", MappingProxyType(dependency_ids))
        object.__setattr__(self, "_dependent_ids", MappingProxyType(dependent_ids))
        object.__setattr__(self, "_topological_order", topo)

    @classmethod
    def from_tasks(
        cls,
        tasks: Iterable[Task],
        name: Optional[str] = None,
    ) -> "TaskGraph":
        """Build a :class:`TaskGraph` from an iterable of tasks.

        Args:
            tasks: Iterable of canonical graph tasks.
            name: Optional human-readable name for this graph.

        Raises:
            ValueError: If duplicate task IDs are provided in ``tasks``.

        Returns:
            TaskGraph: A validated immutable task graph.
        """
        tasks_by_id: dict[str, Task] = {}
        for task in tasks:
            if task.id in tasks_by_id:
                raise ValueError(f"Duplicate task id '{task.id}' in input tasks.")
            tasks_by_id[task.id] = task
        return cls(tasks_by_id=tasks_by_id, name=name)

    def task(self, task_id: str) -> Task:
        """Return the task specification for a task ID.

        Args:
            task_id: Task identifier to retrieve.

        Raises:
            KeyError: If ``task_id`` is not present in this graph.

        Returns:
            Task: The immutable task specification.
        """
        self._require_task_id(task_id)
        return self._tasks_by_id[task_id]

    def task_ids(self) -> tuple[str, ...]:
        """Return all task IDs in dependency-first topological order.

        Returns:
            tuple[str, ...]: All task IDs in stable topological order.
        """
        return self._topological_order

    def dependency_ids(self, task_id: str) -> tuple[str, ...]:
        """Return dependency IDs for a task in declared order.

        Args:
            task_id: Task identifier to inspect.

        Raises:
            KeyError: If ``task_id`` is not present in this graph.

        Returns:
            tuple[str, ...]: Dependency task IDs for ``task_id``.
        """
        self._require_task_id(task_id)
        return self._dependency_ids[task_id]

    def dependent_ids(self, task_id: str) -> tuple[str, ...]:
        """Return task IDs that depend on a task.

        Args:
            task_id: Task identifier to inspect.

        Raises:
            KeyError: If ``task_id`` is not present in this graph.

        Returns:
            tuple[str, ...]: Dependent task IDs in stable sorted order.
        """
        self._require_task_id(task_id)
        return self._dependent_ids[task_id]

    def roots(self) -> tuple[str, ...]:
        """Return IDs of tasks with no dependencies.

        Returns:
            tuple[str, ...]: Root task IDs in stable topological order.
        """
        return tuple(
            task_id
            for task_id in self._topological_order
            if not self._dependency_ids[task_id]
        )

    def leaves(self) -> tuple[str, ...]:
        """Return IDs of tasks with no dependents.

        Returns:
            tuple[str, ...]: Leaf task IDs in stable topological order.
        """
        return tuple(
            task_id
            for task_id in self._topological_order
            if not self._dependent_ids[task_id]
        )

    def topological_order(self) -> tuple[str, ...]:
        """Return dependency-first stable ordering of task IDs.

        Returns:
            tuple[str, ...]: Task IDs in stable topological order.
        """
        return self._topological_order

    def ready_ids(
        self,
        completed_ids: Iterable[str],
        running_ids: Iterable[str] = (),
    ) -> tuple[str, ...]:
        """Return runnable task IDs from pure set inputs.

        A task is ready when:
        - it is not in ``completed_ids``
        - it is not in ``running_ids``
        - every dependency ID is in ``completed_ids``

        Args:
            completed_ids: IDs currently considered completed by the caller.
            running_ids: IDs currently considered in progress by the caller.

        Raises:
            ValueError: If ``completed_ids`` or ``running_ids`` contains an
                unknown task ID.

        Returns:
            tuple[str, ...]: Runnable task IDs in stable topological order.
        """
        completed = set(completed_ids)
        running = set(running_ids)
        _validate_known_ids(completed, self._tasks_by_id, "completed_ids")
        _validate_known_ids(running, self._tasks_by_id, "running_ids")

        blocked = completed | running
        ready: list[str] = []
        for task_id in self._topological_order:
            if task_id in blocked:
                continue
            deps = self._dependency_ids[task_id]
            if all(dep_id in completed for dep_id in deps):
                ready.append(task_id)
        return tuple(ready)

    def _require_task_id(self, task_id: str) -> None:
        """Assert that a task ID exists in this graph.

        Args:
            task_id: Task identifier to validate.

        Raises:
            KeyError: If ``task_id`` is not present in this graph.
        """
        if task_id not in self._tasks_by_id:
            raise KeyError(f"Unknown task id '{task_id}'.")


def _validate_task_identity_consistency(tasks_by_id: Mapping[str, Task]) -> None:
    """Validate shared-ID task references are definition-consistent.

    Args:
        tasks_by_id: Canonical mapping of graph task IDs to tasks.

    Raises:
        ValueError: If a dependency reference uses an existing task ID with
            different task content.
    """
    seen: dict[str, Task] = {}
    visited_objects: set[int] = set()

    def visit(task: Task) -> None:
        existing = seen.get(task.id)
        if existing is None:
            seen[task.id] = task
        elif existing != task:
            raise ValueError(
                f"Conflicting task definitions for id '{task.id}'. "
                "All references to a task ID must be equal."
            )

        obj_id = id(task)
        if obj_id in visited_objects:
            return
        visited_objects.add(obj_id)

        for dep in task.dependencies:
            visit(dep)

    for task in tasks_by_id.values():
        visit(task)


def _build_dependency_ids(
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
        dep_ids = tuple(dep.id for dep in task.dependencies)
        if task_id in dep_ids:
            raise ValueError(f"Task '{task_id}' has a self-dependency.")
        if len(dep_ids) != len(set(dep_ids)):
            raise ValueError(f"Task '{task_id}' has duplicate dependency IDs.")
        dependency_ids[task_id] = dep_ids
    return dependency_ids


def _validate_dependencies_exist(
    tasks_by_id: Mapping[str, Task],
    dependency_ids: Mapping[str, tuple[str, ...]],
) -> None:
    """Validate that every dependency ID exists as a graph task.

    Args:
        tasks_by_id: Canonical mapping of graph task IDs to tasks.
        dependency_ids: Dependency ID index keyed by task ID.

    Raises:
        ValueError: If any dependency ID is unknown.
    """
    all_task_ids = set(tasks_by_id)
    missing: set[str] = set()
    for dep_ids in dependency_ids.values():
        for dep_id in dep_ids:
            if dep_id not in all_task_ids:
                missing.add(dep_id)
    if missing:
        missing_str = ", ".join(sorted(missing))
        raise ValueError(f"Unknown dependency id(s): {missing_str}.")


def _build_dependent_ids(
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


def _topological_order_or_raise(
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


def _validate_known_ids(
    ids: set[str],
    tasks_by_id: Mapping[str, Task],
    source_name: str,
) -> None:
    """Validate that an input ID set only references known graph tasks.

    Args:
        ids: Input task IDs to validate.
        tasks_by_id: Canonical mapping of graph task IDs to tasks.
        source_name: Human-readable source label for error reporting.

    Raises:
        ValueError: If ``ids`` contains unknown task IDs.
    """
    unknown = sorted(task_id for task_id in ids if task_id not in tasks_by_id)
    if unknown:
        unknown_str = ", ".join(unknown)
        raise ValueError(f"{source_name} contains unknown task id(s): {unknown_str}.")
