"""Workstream-level lifecycle runner.

This module defines :class:`WorkstreamRunner` (a Protocol) and
:class:`StandardWorkstreamRunner` (the standard implementation),
which drive a :class:`WorkstreamRuntime` through the workstream lifecycle
steps (prepare, integrate, teardown).

The orchestrator calls these methods at the appropriate points in the
scheduling loop — prepare before the first task in a workstream,
integrate after all tasks succeed, and teardown at the end.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from agentrelay.workstream.core.io import (
    WorkstreamIntegrator,
    WorkstreamPreparer,
    WorkstreamTeardown,
)
from agentrelay.workstream.core.runtime import WorkstreamRuntime, WorkstreamStatus


@dataclass(frozen=True)
class WorkstreamRunResult:
    """Snapshot of workstream state after a lifecycle operation.

    Attributes:
        workstream_id: Workstream identifier.
        status: Current workstream status after the operation.
        error: Error message if the operation failed, or ``None``.
    """

    workstream_id: str
    status: WorkstreamStatus
    error: Optional[str]

    @classmethod
    def from_runtime(cls, runtime: WorkstreamRuntime) -> WorkstreamRunResult:
        """Build a result snapshot from the current workstream runtime state.

        Args:
            runtime: Workstream runtime to snapshot.

        Returns:
            WorkstreamRunResult: Snapshot of workstream ID, status, and error.
        """
        return cls(
            workstream_id=runtime.spec.id,
            status=runtime.status,
            error=runtime.state.error,
        )


@runtime_checkable
class WorkstreamRunner(Protocol):
    """Protocol for the workstream runner boundary used by Orchestrator.

    Different lifecycle variants (standard, dry-run) are different classes
    satisfying this protocol. The orchestrator does not know or care about
    internal step structure.
    """

    def prepare(self, workstream_runtime: WorkstreamRuntime) -> None:
        """Provision workspace infrastructure for a workstream."""
        ...

    def integrate(self, workstream_runtime: WorkstreamRuntime) -> WorkstreamRunResult:
        """Create the integration PR for the workstream."""
        ...

    def teardown(self, workstream_runtime: WorkstreamRuntime) -> None:
        """Clean up workstream workspace infrastructure."""
        ...


@dataclass
class StandardWorkstreamRunner:
    """Standard workstream lifecycle runner.

    Drives workstream-level operations (prepare, integrate, teardown) by
    delegating to per-step protocol implementations. The orchestrator
    calls these methods at appropriate scheduling points.

    Attributes:
        _preparer: Provision worktree and integration branch.
        _integrator: Create integration PR.
        _teardown: Clean up worktree and integration branch.
    """

    _preparer: WorkstreamPreparer
    _integrator: WorkstreamIntegrator
    _teardown: WorkstreamTeardown

    def prepare(self, workstream_runtime: WorkstreamRuntime) -> None:
        """Provision workspace infrastructure for a workstream.

        Creates the worktree and integration branch. Transitions from
        ``PENDING`` to ``ACTIVE`` on success, or ``FAILED`` on error.

        Args:
            workstream_runtime: Workstream runtime to provision.
        """
        try:
            self._preparer.prepare_workstream(workstream_runtime)
        except Exception as exc:
            workstream_runtime.mark_failed(f"{type(exc).__name__}: {exc}")
            raise
        workstream_runtime.mark_active()

    def integrate(self, workstream_runtime: WorkstreamRuntime) -> WorkstreamRunResult:
        """Create the integration PR for the workstream.

        Transitions to ``PR_CREATED`` on success, or ``FAILED`` on error.
        When the integration PR is skipped (no commits ahead), stores the
        authoritative target branch SHA on the runtime artifacts.

        Args:
            workstream_runtime: Workstream runtime to integrate.

        Returns:
            WorkstreamRunResult: Snapshot of state after the operation.
        """
        try:
            result = self._integrator.create_integration_pr(workstream_runtime)
        except Exception as exc:
            workstream_runtime.mark_failed(f"{type(exc).__name__}: {exc}")
            return WorkstreamRunResult.from_runtime(workstream_runtime)

        if result.skipped:
            workstream_runtime.artifacts.target_branch_before_any_merge = (
                result.target_branch_authoritative_sha
            )

        return WorkstreamRunResult.from_runtime(workstream_runtime)

    def teardown(self, workstream_runtime: WorkstreamRuntime) -> None:
        """Clean up workstream workspace infrastructure.

        Deletes the worktree and integration branch. Failures are recorded
        as concerns rather than changing workstream status.

        Args:
            workstream_runtime: Workstream runtime to tear down.
        """
        try:
            self._teardown.teardown_workstream(workstream_runtime)
        except Exception as exc:
            workstream_runtime.artifacts.concerns.append(f"teardown_failed: {exc}")


__all__ = [
    "WorkstreamRunResult",
    "WorkstreamRunner",
    "StandardWorkstreamRunner",
]
