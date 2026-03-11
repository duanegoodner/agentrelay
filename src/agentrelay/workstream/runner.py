"""Workstream-level lifecycle runner.

This module defines :class:`WorkstreamRunner`, which drives a single
:class:`WorkstreamRuntime` through the workstream lifecycle steps
(prepare, merge, teardown), delegating each step to the corresponding
protocol implementation in its :attr:`io` boundary.

The orchestrator calls these methods at the appropriate points in the
scheduling loop — prepare before the first task in a workstream,
merge after all tasks succeed, and teardown at the end.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from agentrelay.workstream.io import WorkstreamRunnerIO
from agentrelay.workstream.runtime import WorkstreamRuntime, WorkstreamStatus


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
            status=runtime.state.status,
            error=runtime.state.error,
        )


@dataclass
class WorkstreamRunner:
    """Workstream lifecycle runner.

    Drives workstream-level operations (prepare, merge, teardown) by
    delegating to the per-step protocol implementations in :attr:`io`.
    The orchestrator calls these methods at appropriate scheduling points.

    Attributes:
        io: Composed I/O boundary for workstream operations.
    """

    io: WorkstreamRunnerIO

    def prepare(self, workstream_runtime: WorkstreamRuntime) -> None:
        """Provision workspace infrastructure for a workstream.

        Creates the worktree and integration branch. Transitions the
        workstream to ``ACTIVE`` on success, or ``FAILED`` on error.

        Args:
            workstream_runtime: Workstream runtime to provision.
        """
        try:
            self.io.preparer.prepare_workstream(workstream_runtime)
        except Exception as exc:
            workstream_runtime.state.status = WorkstreamStatus.FAILED
            workstream_runtime.state.error = f"{type(exc).__name__}: {exc}"
            raise

    def merge(self, workstream_runtime: WorkstreamRuntime) -> WorkstreamRunResult:
        """Merge the workstream integration branch into its target.

        Transitions to ``MERGED`` on success, or ``FAILED`` on error.

        Args:
            workstream_runtime: Workstream runtime to merge.

        Returns:
            WorkstreamRunResult: Snapshot of state after the operation.
        """
        try:
            self.io.merger.merge_workstream(workstream_runtime)
        except Exception as exc:
            workstream_runtime.state.status = WorkstreamStatus.FAILED
            workstream_runtime.state.error = f"{type(exc).__name__}: {exc}"
            return WorkstreamRunResult.from_runtime(workstream_runtime)

        workstream_runtime.state.status = WorkstreamStatus.MERGED
        return WorkstreamRunResult.from_runtime(workstream_runtime)

    def teardown(self, workstream_runtime: WorkstreamRuntime) -> None:
        """Clean up workstream workspace infrastructure.

        Deletes the worktree and integration branch. Failures are recorded
        as concerns rather than changing workstream status.

        Args:
            workstream_runtime: Workstream runtime to tear down.
        """
        try:
            self.io.teardown_handler.teardown_workstream(workstream_runtime)
        except Exception as exc:
            workstream_runtime.artifacts.concerns.append(f"teardown_failed: {exc}")


__all__ = [
    "WorkstreamRunResult",
    "WorkstreamRunner",
]
