"""Task graph model for orchestration planning.

This module defines an immutable :class:`TaskGraph` for static task dependency
structure (a directed acyclic graph of :class:`agentrelay.task.Task` values).
It intentionally excludes runtime execution state, scheduling state transitions,
and side-effectful orchestration operations (for example git, tmux, or signal I/O).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Optional

from agentrelay.task import Task
from agentrelay.task_graph._indexing import (
    build_child_workstream_ids as _build_child_workstream_ids,
)
from agentrelay.task_graph._indexing import (
    build_dependency_ids as _build_dependency_ids,
)
from agentrelay.task_graph._indexing import build_dependent_ids as _build_dependent_ids
from agentrelay.task_graph._indexing import (
    build_task_ids_by_workstream as _build_task_ids_by_workstream,
)
from agentrelay.task_graph._indexing import (
    topological_order_or_raise as _topological_order_or_raise,
)
from agentrelay.task_graph._validation import (
    normalize_workstreams as _normalize_workstreams,
)
from agentrelay.task_graph._validation import (
    validate_dependencies_exist as _validate_dependencies_exist,
)
from agentrelay.task_graph._validation import validate_known_ids as _validate_known_ids
from agentrelay.task_graph._validation import (
    validate_task_workstream_ids as _validate_task_workstream_ids,
)
from agentrelay.task_graph._validation import (
    validate_workstream_hierarchy_acyclic as _validate_workstream_hierarchy_acyclic,
)
from agentrelay.task_graph._validation import (
    validate_workstream_max_depth as _validate_workstream_max_depth,
)
from agentrelay.task_graph._validation import (
    validate_workstream_parent_ids_exist as _validate_workstream_parent_ids_exist,
)
from agentrelay.workstream import WorkstreamSpec


@dataclass(frozen=True)
class TaskGraph:
    """Immutable DAG of :class:`Task` specifications keyed by task ID.

    Attributes:
        name: Optional human-readable graph name.
        max_workstream_depth: Maximum allowed parent-depth for workstream
            hierarchies. ``1`` allows parent -> child only.
        _tasks_by_id: Canonical task objects keyed by task ID.
        _dependency_ids: Dependency IDs for each task ID.
        _dependent_ids: Reverse dependency IDs for each task ID.
        _topological_order: Dependency-first stable task ordering.
        _workstreams_by_id: Workstream specs keyed by workstream ID.
        _task_ids_by_workstream: Task IDs grouped by workstream ID.
        _child_workstream_ids: Child workstream IDs grouped by parent workstream ID.
    """

    name: Optional[str]
    _tasks_by_id: Mapping[str, Task]
    _dependency_ids: Mapping[str, tuple[str, ...]]
    _dependent_ids: Mapping[str, tuple[str, ...]]
    _topological_order: tuple[str, ...]
    max_workstream_depth: int
    _workstreams_by_id: Mapping[str, WorkstreamSpec]
    _task_ids_by_workstream: Mapping[str, tuple[str, ...]]
    _child_workstream_ids: Mapping[str, tuple[str, ...]]

    def __init__(
        self,
        tasks_by_id: Mapping[str, Task],
        name: Optional[str] = None,
        workstreams_by_id: Optional[Mapping[str, WorkstreamSpec]] = None,
        max_workstream_depth: int = 1,
    ):
        """Initialize and validate an immutable task graph.

        Args:
            tasks_by_id: Mapping of task IDs to canonical :class:`Task` objects.
                Each key must match its corresponding ``Task.id``.
            name: Optional human-readable name for this graph.
            workstreams_by_id: Optional mapping of workstream IDs to
                :class:`WorkstreamSpec`. If omitted, a default single workstream
                ``"default"`` is assumed.
            max_workstream_depth: Maximum parent-depth allowed for workstream
                hierarchies. ``1`` allows parent -> child only.

        Raises:
            ValueError: If the graph is empty, contains mismatched key/ID pairs,
                contains conflicting task definitions for a shared task ID, contains
                invalid dependency declarations, contains dependency cycles, or
                contains invalid workstream declarations.
        """
        if max_workstream_depth < 1:
            raise ValueError("max_workstream_depth must be >= 1.")

        if not tasks_by_id:
            raise ValueError("TaskGraph requires at least one task.")

        canonical = dict(tasks_by_id)
        for key, task in canonical.items():
            if key != task.id:
                raise ValueError(
                    f"TaskGraph key '{key}' does not match task.id '{task.id}'."
                )

        dependency_ids = _build_dependency_ids(canonical)
        _validate_dependencies_exist(canonical, dependency_ids)
        dependent_ids = _build_dependent_ids(canonical, dependency_ids)
        topo = _topological_order_or_raise(dependency_ids, dependent_ids)
        workstreams = _normalize_workstreams(workstreams_by_id)
        _validate_task_workstream_ids(canonical, workstreams)
        _validate_workstream_parent_ids_exist(workstreams)
        _validate_workstream_hierarchy_acyclic(workstreams)
        _validate_workstream_max_depth(workstreams, max_depth=max_workstream_depth)
        task_ids_by_workstream = _build_task_ids_by_workstream(
            canonical, topo, workstreams
        )
        child_workstream_ids = _build_child_workstream_ids(workstreams)

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "_tasks_by_id", MappingProxyType(canonical))
        object.__setattr__(self, "_dependency_ids", MappingProxyType(dependency_ids))
        object.__setattr__(self, "_dependent_ids", MappingProxyType(dependent_ids))
        object.__setattr__(self, "_topological_order", topo)
        object.__setattr__(self, "max_workstream_depth", max_workstream_depth)
        object.__setattr__(self, "_workstreams_by_id", MappingProxyType(workstreams))
        object.__setattr__(
            self,
            "_task_ids_by_workstream",
            MappingProxyType(task_ids_by_workstream),
        )
        object.__setattr__(
            self,
            "_child_workstream_ids",
            MappingProxyType(child_workstream_ids),
        )

    @classmethod
    def from_tasks(
        cls,
        tasks: Iterable[Task],
        name: Optional[str] = None,
        workstreams: Optional[Iterable[WorkstreamSpec]] = None,
        max_workstream_depth: int = 1,
    ) -> "TaskGraph":
        """Build a :class:`TaskGraph` from an iterable of tasks.

        Args:
            tasks: Iterable of canonical graph tasks.
            name: Optional human-readable name for this graph.
            workstreams: Optional iterable of workstream specifications.
            max_workstream_depth: Maximum parent-depth allowed for workstream
                hierarchies. ``1`` allows parent -> child only.

        Raises:
            ValueError: If duplicate task IDs or duplicate workstream IDs are
                provided in input iterables.

        Returns:
            TaskGraph: A validated immutable task graph.
        """
        tasks_by_id: dict[str, Task] = {}
        for task in tasks:
            if task.id in tasks_by_id:
                raise ValueError(f"Duplicate task id '{task.id}' in input tasks.")
            tasks_by_id[task.id] = task
        workstreams_by_id: Optional[dict[str, WorkstreamSpec]] = None
        if workstreams is not None:
            workstreams_by_id = {}
            for workstream in workstreams:
                if workstream.id in workstreams_by_id:
                    raise ValueError(
                        f"Duplicate workstream id '{workstream.id}' in input workstreams."
                    )
                workstreams_by_id[workstream.id] = workstream
        return cls(
            tasks_by_id=tasks_by_id,
            name=name,
            workstreams_by_id=workstreams_by_id,
            max_workstream_depth=max_workstream_depth,
        )

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

    def workstream_ids(self) -> tuple[str, ...]:
        """Return all workstream IDs in stable sorted order.

        Returns:
            tuple[str, ...]: All workstream IDs in sorted order.
        """
        return tuple(sorted(self._workstreams_by_id))

    def workstream(self, workstream_id: str) -> WorkstreamSpec:
        """Return workstream specification for a workstream ID.

        Args:
            workstream_id: Workstream identifier to retrieve.

        Raises:
            KeyError: If ``workstream_id`` is not present in this graph.

        Returns:
            WorkstreamSpec: Immutable workstream specification.
        """
        self._require_workstream_id(workstream_id)
        return self._workstreams_by_id[workstream_id]

    def tasks_in_workstream(self, workstream_id: str) -> tuple[str, ...]:
        """Return task IDs in a workstream in graph topological order.

        Args:
            workstream_id: Workstream identifier to inspect.

        Raises:
            KeyError: If ``workstream_id`` is not present in this graph.

        Returns:
            tuple[str, ...]: Task IDs in the given workstream.
        """
        self._require_workstream_id(workstream_id)
        return self._task_ids_by_workstream[workstream_id]

    def child_workstream_ids(self, workstream_id: str) -> tuple[str, ...]:
        """Return child workstream IDs for a parent workstream.

        Args:
            workstream_id: Parent workstream identifier.

        Raises:
            KeyError: If ``workstream_id`` is not present in this graph.

        Returns:
            tuple[str, ...]: Child workstream IDs in stable sorted order.
        """
        self._require_workstream_id(workstream_id)
        return self._child_workstream_ids[workstream_id]

    def _require_task_id(self, task_id: str) -> None:
        """Assert that a task ID exists in this graph.

        Args:
            task_id: Task identifier to validate.

        Raises:
            KeyError: If ``task_id`` is not present in this graph.
        """
        if task_id not in self._tasks_by_id:
            raise KeyError(f"Unknown task id '{task_id}'.")

    def _require_workstream_id(self, workstream_id: str) -> None:
        """Assert that a workstream ID exists in this graph.

        Args:
            workstream_id: Workstream identifier to validate.

        Raises:
            KeyError: If ``workstream_id`` is not present in this graph.
        """
        if workstream_id not in self._workstreams_by_id:
            raise KeyError(f"Unknown workstream id '{workstream_id}'.")
