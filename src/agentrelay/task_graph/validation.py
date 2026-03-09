"""Validation helpers for TaskGraph construction and query inputs.

This module contains pure validation and normalization functions used by
``agentrelay.task_graph.TaskGraph``. Keeping these helpers separate allows the
TaskGraph type to stay focused on immutable graph state and query APIs.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Optional

from agentrelay.task import Task
from agentrelay.workstream import WorkstreamSpec


def normalize_workstreams(
    workstreams_by_id: Optional[Mapping[str, WorkstreamSpec]],
) -> dict[str, WorkstreamSpec]:
    """Normalize input workstream mapping with compatibility defaults.

    Args:
        workstreams_by_id: Optional input mapping of workstreams.

    Raises:
        ValueError: If workstream mapping keys mismatch ``WorkstreamSpec.id``.

    Returns:
        dict[str, WorkstreamSpec]: Canonical workstream mapping.
    """
    if workstreams_by_id is None:
        return {"default": WorkstreamSpec(id="default")}

    canonical = dict(workstreams_by_id)
    for key, spec in canonical.items():
        if key != spec.id:
            raise ValueError(
                f"TaskGraph workstream key '{key}' does not match "
                f"WorkstreamSpec.id '{spec.id}'."
            )
    return canonical


def validate_task_workstream_ids(
    tasks_by_id: Mapping[str, Task],
    workstreams_by_id: Mapping[str, WorkstreamSpec],
) -> None:
    """Validate that every task references a known workstream ID.

    Args:
        tasks_by_id: Canonical mapping of graph task IDs to tasks.
        workstreams_by_id: Canonical mapping of workstream IDs to specs.

    Raises:
        ValueError: If one or more task workstream IDs are unknown.
    """
    known = set(workstreams_by_id)
    unknown = {
        task.workstream_id
        for task in tasks_by_id.values()
        if task.workstream_id not in known
    }
    if unknown:
        unknown_str = ", ".join(sorted(unknown))
        raise ValueError(
            f"Unknown workstream id(s) referenced by tasks: {unknown_str}."
        )


def validate_workstream_parent_ids_exist(
    workstreams_by_id: Mapping[str, WorkstreamSpec],
) -> None:
    """Validate that each parent workstream reference exists.

    Args:
        workstreams_by_id: Canonical mapping of workstream IDs to specs.

    Raises:
        ValueError: If any ``parent_workstream_id`` is unknown.
    """
    known = set(workstreams_by_id)
    for workstream in workstreams_by_id.values():
        parent_id = workstream.parent_workstream_id
        if parent_id is not None and parent_id not in known:
            raise ValueError(
                f"Workstream '{workstream.id}' references unknown parent_workstream_id "
                f"'{parent_id}'."
            )


def validate_workstream_hierarchy_acyclic(
    workstreams_by_id: Mapping[str, WorkstreamSpec],
) -> None:
    """Validate that the workstream parent hierarchy has no cycles.

    Args:
        workstreams_by_id: Canonical mapping of workstream IDs to specs.

    Raises:
        ValueError: If a parent cycle exists.
    """
    done: set[str] = set()
    for workstream_id in sorted(workstreams_by_id):
        if workstream_id in done:
            continue
        path: list[str] = []
        index_by_id: dict[str, int] = {}
        current: Optional[str] = workstream_id

        while current is not None:
            if current in index_by_id:
                start = index_by_id[current]
                cycle = path[start:] + [current]
                raise ValueError(
                    "Workstream hierarchy contains a cycle: " f"{' -> '.join(cycle)}"
                )
            if current in done:
                break
            index_by_id[current] = len(path)
            path.append(current)
            current = workstreams_by_id[current].parent_workstream_id

        done.update(path)


def validate_workstream_max_depth(
    workstreams_by_id: Mapping[str, WorkstreamSpec],
    max_depth: int,
) -> None:
    """Validate that workstream hierarchy depth does not exceed ``max_depth``.

    Args:
        workstreams_by_id: Canonical mapping of workstream IDs to specs.
        max_depth: Maximum allowed ancestry depth.

    Raises:
        ValueError: If any workstream has ancestry depth greater than ``max_depth``.
    """
    for workstream in workstreams_by_id.values():
        depth = 0
        current = workstream.parent_workstream_id
        while current is not None:
            depth += 1
            if depth > max_depth:
                raise ValueError(
                    f"Workstream '{workstream.id}' exceeds maximum supported depth "
                    f"of {max_depth}."
                )
            current = workstreams_by_id[current].parent_workstream_id


def validate_task_identity_consistency(tasks_by_id: Mapping[str, Task]) -> None:
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


def validate_dependencies_exist(
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


def validate_known_ids(
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
