"""Task-level runtime execution — protocol, state machine, and standard lifecycle.

This module defines:

- :class:`TaskRunner` — the protocol boundary used by the orchestrator.
- :class:`StandardTaskRunner` — the concrete standard lifecycle implementation
  (prepare → launch → kickoff → wait → gate → merge → teardown).

The orchestrator depends only on the :class:`TaskRunner` protocol. Different
lifecycle variants (e.g., adding a review step) are separate classes satisfying
the same protocol.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Optional, Protocol, runtime_checkable

from agentrelay.errors import IntegrationFailureClass, classify_integration_error
from agentrelay.ops import gh, signals
from agentrelay.task_runner.core.dispatch import StepDispatch
from agentrelay.task_runner.core.io import (
    TaskCompletionChecker,
    TaskGateChecker,
    TaskKickoff,
    TaskLauncher,
    TaskMerger,
    TaskPreparer,
    TaskTeardown,
)
from agentrelay.task_runtime import SUCCESS_STATUSES, TaskRuntime, TaskStatus

# Allowed lifecycle transitions for one task execution.
ALLOWED_TASK_TRANSITIONS: Mapping[TaskStatus, tuple[TaskStatus, ...]] = (
    MappingProxyType(
        {
            TaskStatus.PENDING: (TaskStatus.RUNNING,),
            TaskStatus.RUNNING: (
                TaskStatus.PR_CREATED,
                TaskStatus.PR_MERGED,
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
            ),
            TaskStatus.PR_CREATED: (TaskStatus.PR_MERGED, TaskStatus.FAILED),
            TaskStatus.PR_MERGED: (),
            TaskStatus.COMPLETED: (),
            TaskStatus.FAILED: (),
        }
    )
)

# Maps non-failure TaskStatus values to the corresponding mark method name
# on TaskRuntime.  Used by StandardTaskRunner._transition().
_MARK_DISPATCH: Mapping[TaskStatus, str] = MappingProxyType(
    {
        TaskStatus.PENDING: "mark_pending",
        TaskStatus.RUNNING: "mark_running",
        TaskStatus.PR_CREATED: "mark_pr_created",
        TaskStatus.PR_MERGED: "mark_pr_merged",
        TaskStatus.COMPLETED: "mark_completed",
    }
)


#: Default max gate attempts when ``Task.max_gate_attempts`` is ``None``.
#: Matches the ``default_max_gate_attempts`` parameter in ``build_policies()``.
_DEFAULT_MAX_GATE_ATTEMPTS = 5


class TearDownMode(str, Enum):
    """Policy controlling whether runtime resources are torn down after run.

    Attributes:
        ALWAYS: Always call teardown at end of run.
        NEVER: Never call teardown.
        ON_SUCCESS: Call teardown only when task reaches a terminal success
            status (``PR_MERGED`` or ``COMPLETED``).
    """

    ALWAYS = "always"
    NEVER = "never"
    ON_SUCCESS = "on_success"


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
        failure_class: Integration error classification for I/O boundary
            failures.  ``None`` for agent-signaled failures and successes.
    """

    task_id: str
    status: TaskStatus
    pr_url: Optional[str]
    error: Optional[str]
    failure_class: Optional[IntegrationFailureClass] = None

    @classmethod
    def from_runtime(
        cls,
        runtime: TaskRuntime,
        failure_class: Optional[IntegrationFailureClass] = None,
    ) -> TaskRunResult:
        """Build a result snapshot from the current runtime state.

        Args:
            runtime: Runtime envelope to snapshot.
            failure_class: Optional integration error classification.

        Returns:
            TaskRunResult: Snapshot of task ID, status, PR URL, and error.
        """
        return cls(
            task_id=runtime.task.id,
            status=runtime.status,
            pr_url=runtime.artifacts.pr_url,
            error=runtime.state.error,
            failure_class=failure_class,
        )


@runtime_checkable
class TaskRunner(Protocol):
    """Protocol for the task runner boundary used by Orchestrator.

    Different lifecycle variants (standard, reviewing, dry-run) are
    different classes satisfying this protocol. The orchestrator does
    not know or care about internal step structure.
    """

    async def run(
        self,
        runtime: TaskRuntime,
        *,
        teardown_mode: TearDownMode = TearDownMode.ALWAYS,
    ) -> TaskRunResult:
        """Execute one task attempt and return terminal task fields."""
        ...


@dataclass
class StandardTaskRunner:
    """Standard task lifecycle: prepare → launch → kickoff → wait → gate → merge → teardown.

    Uses :class:`StepDispatch` tables for per-step implementation selection
    based on the task's ``AgentFramework`` and ``AgentEnvironment``.

    Step sensitivity reference:

    +-----------------------+----------------+----------------------+
    | Step                  | Varies by env? | Varies by framework? |
    +=======================+================+======================+
    | preparer              | No             | No                   |
    +-----------------------+----------------+----------------------+
    | launcher              | Yes            | Yes                  |
    +-----------------------+----------------+----------------------+
    | kickoff               | Yes            | Yes                  |
    +-----------------------+----------------+----------------------+
    | completion_checker    | Maybe          | No                   |
    +-----------------------+----------------+----------------------+
    | gate_checker          | No             | No                   |
    +-----------------------+----------------+----------------------+
    | merger                | No             | No                   |
    +-----------------------+----------------+----------------------+
    | teardown              | Partially      | No                   |
    +-----------------------+----------------+----------------------+

    Extension guide — adding a new framework or environment:
      Add entries to the ``StepDispatch`` tables for steps that have distinct
      implementations. Steps that don't vary can keep using ``default``.

    Extension guide — different lifecycle (e.g., adding a review step):
      Create a new class satisfying the :class:`TaskRunner` protocol. It can
      reuse ``StepDispatch`` tables and per-step protocol implementations.

    Attributes:
        _preparer: Dispatch table for :class:`TaskPreparer` selection.
        _launcher: Dispatch table for :class:`TaskLauncher` selection.
        _kickoff: Dispatch table for :class:`TaskKickoff` selection.
        _completion_checker: Dispatch table for :class:`TaskCompletionChecker` selection.
        _gate_checker: Completion gate checker (not dispatch-based — always
            a shell command, does not vary by framework/environment).
        _merger: Dispatch table for :class:`TaskMerger` selection.
        _teardown: Dispatch table for :class:`TaskTeardown` selection.
    """

    _preparer: StepDispatch[TaskPreparer]
    _launcher: StepDispatch[TaskLauncher]
    _kickoff: StepDispatch[TaskKickoff]
    _completion_checker: StepDispatch[TaskCompletionChecker]
    _gate_checker: TaskGateChecker
    _merger: StepDispatch[TaskMerger]
    _teardown: StepDispatch[TaskTeardown]
    on_event: Optional[Callable[..., None]] = field(default=None, repr=False)

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

        Returns:
            TaskRunResult: Convenience snapshot of terminal runtime fields.

        Raises:
            ValueError: If ``runtime`` does not enter in ``PENDING`` status.
        """
        if runtime.status != TaskStatus.PENDING:
            raise ValueError(
                "StandardTaskRunner.run() requires runtime.status == PENDING. "
                f"Received {runtime.status!r}."
            )

        try:
            try:
                self._preparer(runtime).prepare(runtime)
            except Exception as exc:
                fc = self._record_io_failure(runtime, exc)
                return TaskRunResult.from_runtime(runtime, failure_class=fc)
            self._transition(runtime, TaskStatus.RUNNING)
            self._emit_step(
                "task_prepared",
                runtime,
                f"branch={runtime.state.branch_name}",
            )

            try:
                agent = self._launcher(runtime).launch(runtime)
                runtime.artifacts.agent_address = agent.address
            except Exception as exc:
                fc = self._record_io_failure(runtime, exc)
                return TaskRunResult.from_runtime(runtime, failure_class=fc)
            addr = runtime.artifacts.agent_address
            self._emit_step(
                "task_launched",
                runtime,
                addr.label if addr else None,
            )

            try:
                self._kickoff(runtime).kickoff(runtime, agent)
            except Exception as exc:
                fc = self._record_io_failure(runtime, exc)
                return TaskRunResult.from_runtime(runtime, failure_class=fc)
            self._emit_step("task_waiting", runtime)

            try:
                signal = await self._completion_checker(runtime).wait_for_completion(
                    runtime
                )
            except Exception as exc:
                fc = self._record_io_failure(runtime, exc)
                return TaskRunResult.from_runtime(runtime, failure_class=fc)

            runtime.artifacts.concerns.extend(signal.concerns)
            runtime.artifacts.ops_concerns.extend(signal.ops_concerns)

            if signal.outcome == "failed":
                runtime.mark_failed(
                    signal.error or "Task failed without an error message."
                )
                return TaskRunResult.from_runtime(runtime)

            if signal.pr_url:
                # Standard path: merge the PR.
                runtime.artifacts.pr_url = signal.pr_url
                self._transition(runtime, TaskStatus.PR_CREATED)

                self._save_pr_summary(runtime, signal.pr_url)

                # Completion gate check (optional — only if task declares one).
                if runtime.task.completion_gate is not None:
                    gate_failed = self._run_gate(runtime)
                    if gate_failed is not None:
                        return gate_failed

                self._emit_step("task_pr_merging", runtime, signal.pr_url)
                try:
                    self._merger(runtime).merge_pr(runtime, signal.pr_url)
                except Exception as exc:
                    fc = self._record_io_failure(runtime, exc)
                    return TaskRunResult.from_runtime(runtime, failure_class=fc)

                self._transition(runtime, TaskStatus.PR_MERGED)
            else:
                # PR-less completion (e.g., review-only task with no changes).
                self._transition(runtime, TaskStatus.COMPLETED)
        finally:
            if self._should_teardown(teardown_mode, runtime.status):
                try:
                    self._teardown(runtime).teardown(runtime)
                except Exception as exc:
                    runtime.artifacts.concerns.append(f"teardown_failed: {exc}")

        return TaskRunResult.from_runtime(runtime)

    def _run_gate(self, runtime: TaskRuntime) -> Optional[TaskRunResult]:
        """Run the completion gate retry loop.

        Returns ``None`` if the gate passes, or a ``TaskRunResult`` if the
        gate fails all attempts or an exception occurs.
        """
        max_attempts = runtime.task.max_gate_attempts or _DEFAULT_MAX_GATE_ATTEMPTS
        command = runtime.task.completion_gate

        for attempt in range(max_attempts):
            self._emit_step(
                "task_gate_running",
                runtime,
                f"attempt {attempt + 1}/{max_attempts}: {command}",
            )
            try:
                gate_result = self._gate_checker.check_gate(runtime)
            except Exception as exc:
                fc = self._record_io_failure(runtime, exc)
                return TaskRunResult.from_runtime(runtime, failure_class=fc)
            if gate_result.passed:
                self._emit_step("task_gate_passed", runtime)
                return None
        # All attempts exhausted.
        self._emit_step("task_gate_failed", runtime, command)
        runtime.mark_failed(
            f"Completion gate failed after {max_attempts} attempt(s): {command}"
        )
        return TaskRunResult.from_runtime(runtime)

    def _emit_step(
        self,
        kind: str,
        runtime: TaskRuntime,
        message: Optional[str] = None,
    ) -> None:
        """Emit a step-level event if an event callback is registered."""
        if self.on_event is None:
            return
        # Local import to avoid circular dependency (orchestrator → task_runner).
        from agentrelay.orchestrator.orchestrator import OrchestratorEvent

        self.on_event(
            OrchestratorEvent(
                kind=kind,
                task_id=runtime.task.id,
                workstream_id=runtime.task.workstream_id,
                message=message,
            )
        )

    def _transition(self, runtime: TaskRuntime, target: TaskStatus) -> None:
        """Transition runtime status while enforcing legal lifecycle edges.

        Handles non-failure transitions; ``FAILED`` is written directly by
        callers via ``runtime.mark_failed(error)``.
        """
        current = runtime.status
        allowed = ALLOWED_TASK_TRANSITIONS[current]
        if target not in allowed:
            raise RuntimeError(
                f"Illegal task status transition: {current.value} -> {target.value}"
            )
        method_name = _MARK_DISPATCH[target]
        getattr(runtime, method_name)()

    def _save_pr_summary(self, runtime: TaskRuntime, pr_url: str) -> None:
        """Fetch PR body and write summary.md to the signal directory.

        Silently skips if the fetch fails or the body is empty — saving
        the summary must not block the merge.
        """
        if runtime.state.signal_dir is None:
            return
        try:
            body = gh.pr_body(pr_url)
        except Exception:
            return
        if body:
            signals.write_text(runtime.state.signal_dir, "summary.md", body)

    def _record_io_failure(
        self, runtime: TaskRuntime, exc: Exception
    ) -> IntegrationFailureClass:
        """Record an I/O boundary failure and return its classification."""
        if runtime.status != TaskStatus.FAILED:
            runtime.mark_failed(f"{type(exc).__name__}: {exc}")
        return classify_integration_error(exc)

    def _should_teardown(
        self, teardown_mode: TearDownMode, terminal_status: TaskStatus
    ) -> bool:
        """Return whether teardown should run for the given policy/status."""
        if teardown_mode == TearDownMode.ALWAYS:
            return True
        if teardown_mode == TearDownMode.NEVER:
            return False
        return terminal_status in SUCCESS_STATUSES
