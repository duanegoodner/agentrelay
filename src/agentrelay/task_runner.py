"""Task-level runtime execution interface.

This module defines the API contract for running one :class:`TaskRuntime`
through its lifecycle state machine:

``PENDING -> RUNNING -> PR_CREATED -> PR_MERGED``

with failure transitions to ``FAILED``.

This is an interface-first module in the non-prototype architecture track.
Behavioral implementation is intentionally deferred to a follow-up change.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Optional, Protocol, runtime_checkable

from agentrelay.agent import Agent
from agentrelay.task_runtime import TaskRuntime, TaskStatus

# Allowed lifecycle transitions for one task execution.
ALLOWED_TASK_TRANSITIONS: Mapping[TaskStatus, tuple[TaskStatus, ...]] = (
    MappingProxyType(
        {
            TaskStatus.PENDING: (TaskStatus.RUNNING,),
            TaskStatus.RUNNING: (TaskStatus.PR_CREATED, TaskStatus.FAILED),
            TaskStatus.PR_CREATED: (TaskStatus.PR_MERGED, TaskStatus.FAILED),
            TaskStatus.PR_MERGED: (),
            TaskStatus.FAILED: (),
        }
    )
)


@dataclass(frozen=True)
class TaskCompletionSignal:
    """Signal payload returned by the runtime I/O boundary.

    Attributes:
        outcome: Terminal completion signal from external execution.
            ``"done"`` indicates the task finished and produced a PR.
            ``"failed"`` indicates the task failed before successful completion.
        pr_url: Pull request URL for a ``"done"`` outcome, if available.
        error: Failure detail for a ``"failed"`` outcome, if available.
    """

    outcome: Literal["done", "failed"]
    pr_url: Optional[str] = None
    error: Optional[str] = None


@runtime_checkable
class TaskRunnerIO(Protocol):
    """Side-effect boundary used by :class:`TaskRunner`.

    Concrete implementations handle environment- and framework-specific actions
    (worktree setup, agent launch, completion polling, PR merge, and teardown).
    """

    def prepare(self, runtime: TaskRuntime) -> None:
        """Prepare runtime execution prerequisites before launch.

        Args:
            runtime: Runtime envelope to prepare (for example worktree/signal files).
        """
        ...

    def launch(self, runtime: TaskRuntime) -> Agent:
        """Launch and return the primary agent for this task runtime.

        Args:
            runtime: Runtime envelope to launch against.

        Returns:
            Agent: Live agent handle bound to this task.
        """
        ...

    def kickoff(self, runtime: TaskRuntime) -> None:
        """Send kickoff instructions to the launched task agent.

        Args:
            runtime: Runtime envelope whose agent should be activated.
        """
        ...

    async def wait_for_completion(self, runtime: TaskRuntime) -> TaskCompletionSignal:
        """Wait for terminal task signal from the external execution boundary.

        Args:
            runtime: Runtime envelope being observed.

        Returns:
            TaskCompletionSignal: Terminal signal payload with outcome data.
        """
        ...

    def merge_pr(self, runtime: TaskRuntime, pr_url: str) -> None:
        """Merge the completed task PR into the integration target.

        Args:
            runtime: Runtime envelope being merged.
            pr_url: Pull request URL to merge.
        """
        ...

    def teardown(self, runtime: TaskRuntime) -> None:
        """Release runtime resources after terminal completion.

        Args:
            runtime: Runtime envelope whose resources should be cleaned up.
        """
        ...


@dataclass(frozen=True)
class TaskRunResult:
    """Convenience return value mirroring terminal fields on :class:`TaskRuntime`.

    ``TaskRuntime`` remains the single source of truth; this result is a snapshot
    for ergonomic call-site consumption.

    Attributes:
        task_id: Task identifier.
        status: Terminal task status after ``TaskRunner.run(...)``.
        pr_url: Task PR URL, if one was recorded.
        error: Task failure message, if one was recorded.
    """

    task_id: str
    status: TaskStatus
    pr_url: Optional[str]
    error: Optional[str]

    @classmethod
    def from_runtime(cls, runtime: TaskRuntime) -> TaskRunResult:
        """Build a result snapshot from the current runtime state.

        Args:
            runtime: Runtime envelope to snapshot.

        Returns:
            TaskRunResult: Snapshot of task ID, status, PR URL, and error.
        """
        return cls(
            task_id=runtime.task.id,
            status=runtime.state.status,
            pr_url=runtime.artifacts.pr_url,
            error=runtime.state.error,
        )


@dataclass
class TaskRunner:
    """One-task lifecycle state machine executor.

    This class will drive a single ``TaskRuntime`` through legal transitions
    defined in :data:`ALLOWED_TASK_TRANSITIONS`.

    Attributes:
        io: Side-effect adapter used for environment/framework operations.
    """

    io: TaskRunnerIO

    async def run(self, runtime: TaskRuntime) -> TaskRunResult:
        """Execute one task lifecycle run and return a convenience snapshot.

        Args:
            runtime: Mutable task runtime to execute. Must enter in ``PENDING``
                state for this first implementation milestone.

        Returns:
            TaskRunResult: Convenience snapshot of terminal runtime fields.

        Raises:
            NotImplementedError: Interface-first stub. Behavioral logic is
                implemented in a follow-up change.
        """
        raise NotImplementedError(
            "TaskRunner.run() lifecycle behavior is intentionally deferred. "
            "This module currently locks the API contract only."
        )
