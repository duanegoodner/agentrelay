"""Task-level runtime execution interface.

This module defines the runtime behavior for running one :class:`TaskRuntime`
through its lifecycle state machine:

``PENDING -> RUNNING -> PR_CREATED -> PR_MERGED``

with failure transitions to ``FAILED``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
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


class TearDownMode(str, Enum):
    """Policy controlling whether runtime resources are torn down after run.

    Attributes:
        ALWAYS: Always call ``io.teardown(...)`` at end of run.
        NEVER: Never call ``io.teardown(...)``.
        ON_SUCCESS: Call ``io.teardown(...)`` only when task reaches
            ``TaskStatus.PR_MERGED``.
    """

    ALWAYS = "always"
    NEVER = "never"
    ON_SUCCESS = "on_success"


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

    async def run(
        self,
        runtime: TaskRuntime,
        *,
        teardown_mode: TearDownMode = TearDownMode.ALWAYS,
    ) -> TaskRunResult:
        """Execute one task lifecycle run and return a result snapshot.

        Args:
            runtime: Mutable task runtime to execute. Must enter in ``PENDING``
                state.
            teardown_mode: Resource teardown policy after run completion.
                ``ALWAYS`` tears down for all outcomes.
                ``NEVER`` leaves resources in place.
                ``ON_SUCCESS`` tears down only when status is ``PR_MERGED``.

        Returns:
            TaskRunResult: Convenience snapshot of terminal runtime fields.

        Raises:
            ValueError: If ``runtime`` does not enter in ``PENDING`` status.
        """
        if runtime.state.status != TaskStatus.PENDING:
            raise ValueError(
                "TaskRunner.run() requires runtime.state.status == PENDING. "
                f"Received {runtime.state.status!r}."
            )

        self._transition(runtime, TaskStatus.RUNNING)
        try:
            try:
                self.io.prepare(runtime)
            except Exception as exc:
                self._record_io_failure(runtime, exc)
                return TaskRunResult.from_runtime(runtime)

            try:
                runtime.agent = self.io.launch(runtime)
            except Exception as exc:
                self._record_io_failure(runtime, exc)
                return TaskRunResult.from_runtime(runtime)

            try:
                self.io.kickoff(runtime)
            except Exception as exc:
                self._record_io_failure(runtime, exc)
                return TaskRunResult.from_runtime(runtime)

            try:
                signal = await self.io.wait_for_completion(runtime)
            except Exception as exc:
                self._record_io_failure(runtime, exc)
                return TaskRunResult.from_runtime(runtime)

            if signal.outcome == "failed":
                self._transition(runtime, TaskStatus.FAILED)
                runtime.state.error = (
                    signal.error or "Task failed without an error message."
                )
                return TaskRunResult.from_runtime(runtime)

            if not signal.pr_url:
                self._transition(runtime, TaskStatus.FAILED)
                runtime.state.error = (
                    "Task completion signaled 'done' but did not include pr_url."
                )
                return TaskRunResult.from_runtime(runtime)

            runtime.artifacts.pr_url = signal.pr_url
            self._transition(runtime, TaskStatus.PR_CREATED)

            try:
                self.io.merge_pr(runtime, signal.pr_url)
            except Exception as exc:
                self._record_io_failure(runtime, exc)
                return TaskRunResult.from_runtime(runtime)

            self._transition(runtime, TaskStatus.PR_MERGED)
        finally:
            if self._should_teardown(teardown_mode, runtime.state.status):
                try:
                    self.io.teardown(runtime)
                except Exception as exc:
                    runtime.artifacts.concerns.append(f"teardown_failed: {exc}")

        return TaskRunResult.from_runtime(runtime)

    def _transition(self, runtime: TaskRuntime, target: TaskStatus) -> None:
        """Transition runtime status while enforcing legal lifecycle edges."""
        current = runtime.state.status
        allowed = ALLOWED_TASK_TRANSITIONS[current]
        if target not in allowed:
            raise RuntimeError(
                f"Illegal task status transition: {current.value} -> {target.value}"
            )
        runtime.state.status = target

    def _transition_to_failed(self, runtime: TaskRuntime) -> None:
        """Move runtime to ``FAILED`` from a non-terminal in-progress state."""
        if runtime.state.status == TaskStatus.FAILED:
            return
        if TaskStatus.FAILED in ALLOWED_TASK_TRANSITIONS[runtime.state.status]:
            self._transition(runtime, TaskStatus.FAILED)
            return
        runtime.state.status = TaskStatus.FAILED

    def _record_io_failure(self, runtime: TaskRuntime, exc: Exception) -> None:
        """Record an I/O boundary failure on the runtime."""
        self._transition_to_failed(runtime)
        runtime.state.error = f"{type(exc).__name__}: {exc}"

    def _should_teardown(
        self, teardown_mode: TearDownMode, terminal_status: TaskStatus
    ) -> bool:
        """Return whether teardown should run for the given policy/status."""
        if teardown_mode == TearDownMode.ALWAYS:
            return True
        if teardown_mode == TearDownMode.NEVER:
            return False
        return terminal_status == TaskStatus.PR_MERGED
