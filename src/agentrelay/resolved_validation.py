"""Validation for comparing frozen resolved records against graph definitions.

Used during graph resumption to detect structural drift between the frozen
record written at completion time and the current graph YAML / CLI resolution.

Mismatches are informational (override report), not errors.  The only hard
error is a completed task ID missing from the current graph — its node is
needed for DAG dependency resolution.

Classes:
    FieldMismatch: One field-level difference between resolved record and graph.
    TaskValidationResult: Per-task validation outcome.
    FrozenValidationResult: Aggregate validation for all frozen tasks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentrelay.resolved import InputFromSpec, ResolvedTask, TaggedPathSpec
from agentrelay.task import Task


@dataclass(frozen=True)
class FieldMismatch:
    """One field-level difference between a frozen record and a graph definition.

    Attributes:
        field: Name of the differing field.
        resolved_value: Value from the frozen ``resolved.json``.
        current_value: Value from the current graph definition.
    """

    field: str
    resolved_value: Any
    current_value: Any


@dataclass(frozen=True)
class TaskValidationResult:
    """Per-task validation outcome.

    Attributes:
        task_id: Task identifier.
        mismatches: Tuple of per-field differences (empty = no drift).
    """

    task_id: str
    mismatches: tuple[FieldMismatch, ...]

    @property
    def has_overrides(self) -> bool:
        """True if the frozen record differs from the current definition."""
        return len(self.mismatches) > 0


@dataclass(frozen=True)
class FrozenValidationResult:
    """Aggregate validation result for all frozen tasks in a run.

    Attributes:
        task_results: Per-task validation outcomes (only for tasks with overrides).
        missing_task_ids: Task IDs present in frozen records but absent
            from the current graph — these are hard errors.
    """

    task_results: tuple[TaskValidationResult, ...]
    missing_task_ids: tuple[str, ...]

    @property
    def has_errors(self) -> bool:
        """True if any frozen task is missing from the current graph."""
        return len(self.missing_task_ids) > 0

    @property
    def has_overrides(self) -> bool:
        """True if any frozen task has definition-level overrides."""
        return any(r.has_overrides for r in self.task_results)


def validate_resolved_task(resolved: ResolvedTask, task: Task) -> TaskValidationResult:
    """Compare a frozen :class:`ResolvedTask` against a current :class:`Task`.

    Compares definition-level fields only — not execution artifacts like
    ``branch_name``, ``pr_url``, or ``completed_at_attempt``.

    Args:
        resolved: Frozen execution record from ``resolved.json``.
        task: Current task definition from the graph.

    Returns:
        TaskValidationResult: Mismatches (empty if identical).
    """
    mismatches: list[FieldMismatch] = []

    # Dependencies.
    if resolved.dependencies != task.dependencies:
        mismatches.append(
            FieldMismatch("dependencies", resolved.dependencies, task.dependencies)
        )

    # Role.
    current_role = task.role.value
    if resolved.role != current_role:
        mismatches.append(FieldMismatch("role", resolved.role, current_role))

    # Model.
    current_model = task.primary_agent.model
    if resolved.model != current_model:
        mismatches.append(FieldMismatch("model", resolved.model, current_model))

    # Tagged paths.
    current_tagged_paths = tuple(
        TaggedPathSpec(path=str(tp.path), category=tp.category)
        for tp in task.tagged_paths
    )
    if resolved.tagged_paths != current_tagged_paths:
        mismatches.append(
            FieldMismatch("tagged_paths", resolved.tagged_paths, current_tagged_paths)
        )

    # Inputs from.
    current_inputs_from = tuple(
        InputFromSpec(task=inp.task, category=inp.category) for inp in task.inputs_from
    )
    if resolved.inputs_from != current_inputs_from:
        mismatches.append(
            FieldMismatch("inputs_from", resolved.inputs_from, current_inputs_from)
        )

    # Workstream ID.
    if resolved.workstream_id != task.workstream_id:
        mismatches.append(
            FieldMismatch("workstream_id", resolved.workstream_id, task.workstream_id)
        )

    return TaskValidationResult(task_id=resolved.task_id, mismatches=tuple(mismatches))


def validate_frozen_tasks(
    frozen: dict[str, ResolvedTask],
    current_tasks: dict[str, Task],
) -> FrozenValidationResult:
    """Validate all frozen tasks against the current graph definitions.

    Args:
        frozen: Frozen records keyed by task ID.
        current_tasks: Current task definitions keyed by task ID.

    Returns:
        FrozenValidationResult: Aggregate validation result.
    """
    missing: list[str] = []
    results: list[TaskValidationResult] = []

    for task_id, resolved in frozen.items():
        if task_id not in current_tasks:
            missing.append(task_id)
            continue
        result = validate_resolved_task(resolved, current_tasks[task_id])
        if result.has_overrides:
            results.append(result)

    return FrozenValidationResult(
        task_results=tuple(results),
        missing_task_ids=tuple(missing),
    )


__all__ = [
    "FieldMismatch",
    "FrozenValidationResult",
    "TaskValidationResult",
    "validate_frozen_tasks",
    "validate_resolved_task",
]
