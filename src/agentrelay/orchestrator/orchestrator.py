"""Graph-level orchestration loop for task and workstream runtimes.

This module schedules tasks from a :class:`agentrelay.task_graph.TaskGraph`
using dependency readiness and workstream constraints, then delegates one-task
execution to :class:`agentrelay.task_runner.TaskRunner`.
"""

from __future__ import annotations

import asyncio
import time
import traceback
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Optional, Protocol, runtime_checkable

from agentrelay.errors import IntegrationFailureClass
from agentrelay.orchestrator.builders import (
    TaskRuntimeBuilder,
    WorkstreamRuntimeBuilder,
)
from agentrelay.task_graph import TaskGraph
from agentrelay.task_runner import TaskRunner, TaskRunResult, TearDownMode
from agentrelay.task_runtime import SUCCESS_STATUSES, TaskRuntime, TaskStatus
from agentrelay.workstream import (
    IntegrationAutoMerger,
    IntegrationMergeChecker,
    WorkstreamRunner,
    WorkstreamRuntime,
    WorkstreamStatus,
)


class TaskOutcomeClass(str, Enum):
    """Classification of one task attempt outcome from the orchestrator boundary.

    Attributes:
        SUCCESS: Task reached a terminal success status (``PR_MERGED`` or ``COMPLETED``).
        EXPECTED_FAILURE: Task run returned ``FAILED``.
        INTERNAL_ERROR: Task run raised an exception.
    """

    SUCCESS = "success"  # Task reached a terminal success status
    EXPECTED_FAILURE = "expected_failure"
    INTERNAL_ERROR = "internal_error"


class OrchestratorOutcome(str, Enum):
    """Terminal outcome for one orchestrator run.

    Attributes:
        SUCCEEDED: All tasks reached a terminal success status.
        COMPLETED_WITH_FAILURES: No fatal internal error, but one or more tasks
            ended ``FAILED``.
        FATAL_INTERNAL_ERROR: A task run raised and orchestration failed fast.
    """

    SUCCEEDED = "succeeded"
    COMPLETED_WITH_FAILURES = "completed_with_failures"
    FATAL_INTERNAL_ERROR = "fatal_internal_error"


@dataclass(frozen=True)
class OrchestratorConfig:
    """Configuration for one orchestrator scheduling run.

    Attributes:
        max_concurrency: Maximum number of task attempts to run concurrently.
        max_task_attempts: Maximum attempts per task (including first attempt).
        task_teardown_mode: Teardown policy forwarded to ``TaskRunner.run(...)``.
        fail_fast_on_internal_error: Stop scheduling immediately when a task run
            raises (internal/system failure).
        fail_fast_on_workstream_error: When ``True``, a workstream-level failure
            prevents preparing any new (PENDING) workstreams. In-flight work
            in already-active workstreams is not cancelled.  Defaults to
            ``False``.
        merge_poll_interval: Seconds between polls for integration PR merge
            status.  Only used when an :class:`IntegrationMergeChecker` is
            configured on the :class:`Orchestrator`.
    """

    max_concurrency: int = 1
    max_task_attempts: int = 1
    task_teardown_mode: TearDownMode = TearDownMode.ON_SUCCESS
    fail_fast_on_internal_error: bool = True
    fail_fast_on_workstream_error: bool = False
    merge_poll_interval: float = 30.0


@dataclass(frozen=True)
class OrchestratorEvent:
    """Structured event emitted by the orchestration loop.

    Attributes:
        kind: Event type identifier.
        task_id: Optional task ID associated with the event.
        workstream_id: Optional workstream ID associated with the event.
        attempt_num: Optional 0-indexed attempt number for task-run events.
        outcome_class: Optional classified task outcome.
        message: Optional event detail.
    """

    kind: str
    timestamp: float = field(default_factory=time.time)
    task_id: Optional[str] = None
    workstream_id: Optional[str] = None
    attempt_num: Optional[int] = None
    outcome_class: Optional[TaskOutcomeClass] = None
    message: Optional[str] = None


@runtime_checkable
class OrchestratorListener(Protocol):
    """Callback protocol for real-time orchestration event observation."""

    def on_event(self, event: OrchestratorEvent) -> None:
        """Called each time the orchestrator produces an event.

        Args:
            event: The event that was just produced.
        """
        ...


@dataclass(frozen=True)
class OrchestratorResult:
    """Terminal result for one orchestrator run.

    Attributes:
        outcome: Overall run outcome classification.
        task_runtimes: Final task runtimes keyed by task ID.
        workstream_runtimes: Final workstream runtimes keyed by workstream ID.
        events: Ordered structured events produced during scheduling/execution.
        fatal_error: Traceback text for fatal internal errors, if any.
    """

    outcome: OrchestratorOutcome
    task_runtimes: Mapping[str, TaskRuntime]
    workstream_runtimes: Mapping[str, WorkstreamRuntime]
    events: tuple[OrchestratorEvent, ...]
    fatal_error: Optional[str] = None


@dataclass
class Orchestrator:
    """Async graph scheduler using dependency + workstream constraints.

    Immutable configuration holder. The :meth:`run` method creates an
    :class:`_OrchestratorRun` that owns all mutable execution state.
    """

    graph: TaskGraph
    task_runner: TaskRunner
    workstream_runner: WorkstreamRunner
    config: OrchestratorConfig = field(default_factory=OrchestratorConfig)
    listener: Optional[OrchestratorListener] = None
    integration_merge_checker: Optional[IntegrationMergeChecker] = None
    integration_auto_merger: Optional[IntegrationAutoMerger] = None

    async def run(
        self,
        task_runtimes: Optional[Mapping[str, TaskRuntime]] = None,
        workstream_runtimes: Optional[Mapping[str, WorkstreamRuntime]] = None,
    ) -> OrchestratorResult:
        """Run graph orchestration until terminal success/failure.

        Args:
            task_runtimes: Optional prebuilt task runtime map for resume-like runs.
                If omitted, built fresh from graph.
            workstream_runtimes: Optional prebuilt workstream runtime map for
                resume-like runs. If omitted, built fresh from graph.

        Returns:
            OrchestratorResult: Terminal orchestration result with mutated runtimes.

        Raises:
            ValueError: If configuration values are invalid or runtime maps do not
                align with graph IDs.
        """
        session = _OrchestratorRun(self, task_runtimes, workstream_runtimes)
        return await session.execute()


class _OrchestratorRun:
    """Mutable execution context for a single :meth:`Orchestrator.run` call.

    Holds a reference to the parent :class:`Orchestrator` for read-only access
    to configuration (graph, runners, config, listener). All mutable state for
    the scheduling loop lives on this object.
    """

    def __init__(
        self,
        orchestrator: Orchestrator,
        task_runtimes: Optional[Mapping[str, TaskRuntime]],
        workstream_runtimes: Optional[Mapping[str, WorkstreamRuntime]],
    ) -> None:
        self._orchestrator = orchestrator
        self._validate_config()

        self._task_runtimes = self._init_task_runtimes(task_runtimes)
        self._workstream_runtimes = self._init_workstream_runtimes(workstream_runtimes)

        self._events: list[OrchestratorEvent] = []
        self._completed_ids: set[str] = {
            task_id
            for task_id, runtime in self._task_runtimes.items()
            if runtime.status in SUCCESS_STATUSES
        }
        self._attempts_used = self._initialize_attempts_used()
        self._normalize_failed_for_retry()
        self._refresh_workstream_terminal_states()
        self._process_merge_ready_workstreams()

        self._running: dict[str, asyncio.Task[TaskRunResult]] = {}
        self._running_attempts: dict[str, int] = {}
        self._fatal_error: Optional[str] = None

        # Wire step-level event emission into the task runner if supported.
        from agentrelay.task_runner.core.runner import StandardTaskRunner

        if isinstance(orchestrator.task_runner, StandardTaskRunner):
            orchestrator.task_runner.on_event = self._emit

    # -- Public entry point --------------------------------------------------

    async def execute(self) -> OrchestratorResult:
        """Run the scheduling loop and return the terminal result."""
        config = self._orchestrator.config
        while True:
            if self._all_tasks_terminal() or self._fatal_error is not None:
                break

            self._poll_integration_merges()
            self._dispatch_ready_tasks()

            if not self._running:
                if self._has_pending_integration_merges():
                    self._emit(
                        OrchestratorEvent(
                            kind="waiting_for_integration_merge",
                        ),
                    )
                    await asyncio.sleep(config.merge_poll_interval)
                    continue
                if not self._handle_deadlock():
                    break
                continue

            wait_timeout: Optional[float] = None
            if self._has_pending_integration_merges():
                wait_timeout = config.merge_poll_interval

            done, _ = await asyncio.wait(
                self._running.values(),
                return_when=asyncio.FIRST_COMPLETED,
                timeout=wait_timeout,
            )
            if done:
                await self._process_completed_tasks(done)

        return self._build_result()

    # -- Initialization helpers ----------------------------------------------

    def _validate_config(self) -> None:
        config = self._orchestrator.config
        if config.max_concurrency < 1:
            raise ValueError("OrchestratorConfig.max_concurrency must be >= 1.")
        if config.max_task_attempts < 1:
            raise ValueError("OrchestratorConfig.max_task_attempts must be >= 1.")
        if config.merge_poll_interval <= 0:
            raise ValueError("OrchestratorConfig.merge_poll_interval must be > 0.")

    def _init_task_runtimes(
        self, task_runtimes: Optional[Mapping[str, TaskRuntime]]
    ) -> dict[str, TaskRuntime]:
        graph = self._orchestrator.graph
        if task_runtimes is None:
            return TaskRuntimeBuilder.from_graph(graph)
        runtimes = dict(task_runtimes)
        expected = set(graph.task_ids())
        actual = set(runtimes.keys())
        if actual != expected:
            raise ValueError(
                "task_runtimes keys must match graph.task_ids(). "
                f"Missing={sorted(expected - actual)}, extra={sorted(actual - expected)}."
            )
        return runtimes

    def _init_workstream_runtimes(
        self, workstream_runtimes: Optional[Mapping[str, WorkstreamRuntime]]
    ) -> dict[str, WorkstreamRuntime]:
        graph = self._orchestrator.graph
        if workstream_runtimes is None:
            return WorkstreamRuntimeBuilder.from_graph(graph)
        runtimes = dict(workstream_runtimes)
        expected = set(graph.workstream_ids())
        actual = set(runtimes.keys())
        if actual != expected:
            raise ValueError(
                "workstream_runtimes keys must match graph.workstream_ids(). "
                f"Missing={sorted(expected - actual)}, extra={sorted(actual - expected)}."
            )
        return runtimes

    def _initialize_attempts_used(self) -> dict[str, int]:
        attempts_used: dict[str, int] = {}
        for task_id, runtime in self._task_runtimes.items():
            status = runtime.status
            if status in (TaskStatus.RUNNING, TaskStatus.PR_CREATED):
                raise ValueError(
                    "Resume from RUNNING/PR_CREATED is not yet supported. "
                    f"Task '{task_id}' is in state {status.value!r}."
                )
            if status in SUCCESS_STATUSES or status == TaskStatus.FAILED:
                attempts_used[task_id] = runtime.state.attempt_num + 1
            else:
                attempts_used[task_id] = runtime.state.attempt_num
        return attempts_used

    def _normalize_failed_for_retry(self) -> None:
        max_attempts = self._orchestrator.config.max_task_attempts
        for task_id, runtime in self._task_runtimes.items():
            if runtime.status != TaskStatus.FAILED:
                continue
            if self._attempts_used[task_id] < max_attempts:
                runtime.mark_pending()

    # -- Main loop phases ----------------------------------------------------

    def _dispatch_ready_tasks(self) -> None:
        """Find dependency-ready tasks and launch them."""
        graph = self._orchestrator.graph
        config = self._orchestrator.config

        ready_ids = graph.ready_ids(
            completed_ids=self._completed_ids,
            running_ids=self._running.keys(),
        )
        for task_id in ready_ids:
            if len(self._running) >= config.max_concurrency:
                break
            runtime = self._task_runtimes[task_id]
            if runtime.status != TaskStatus.PENDING:
                continue
            if not self._workstream_can_run(task_id):
                continue

            ws_runtime = self._workstream_runtimes[runtime.task.workstream_id]
            if ws_runtime.status == WorkstreamStatus.PENDING:
                if self._should_block_new_workstreams():
                    continue
                try:
                    self._orchestrator.workstream_runner.prepare(ws_runtime)
                except Exception:
                    self._emit(
                        OrchestratorEvent(
                            kind="workstream_prepare_failed",
                            workstream_id=runtime.task.workstream_id,
                            message=ws_runtime.state.error,
                        ),
                    )
                    continue
                self._emit(
                    OrchestratorEvent(
                        kind="workstream_prepared",
                        workstream_id=runtime.task.workstream_id,
                    ),
                )

            attempt_num = self._attempts_used[task_id]
            runtime.prepare_for_attempt(attempt_num)
            runtime.state.integration_branch = ws_runtime.state.branch_name
            runtime.state.workstream_worktree_path = ws_runtime.state.worktree_path
            self._emit(
                OrchestratorEvent(
                    kind="task_started",
                    task_id=task_id,
                    workstream_id=runtime.task.workstream_id,
                    attempt_num=attempt_num,
                ),
            )
            self._running[task_id] = asyncio.create_task(
                self._orchestrator.task_runner.run(
                    runtime, teardown_mode=config.task_teardown_mode
                )
            )
            self._running_attempts[task_id] = attempt_num

    def _handle_deadlock(self) -> bool:
        """Mark blocked tasks failed when nothing is running.

        Returns:
            True if progress was made (loop should continue), False if stuck.
        """
        changed = self._mark_blocked_pending_tasks_failed()
        if not changed:
            return False
        self._refresh_workstream_terminal_states()
        self._process_merge_ready_workstreams()
        return True

    async def _process_completed_tasks(
        self, done: set[asyncio.Task[TaskRunResult]]
    ) -> None:
        """Process all tasks that completed in the last await."""
        for done_task in done:
            task_id = self._task_id_for_future(done_task)
            del self._running[task_id]
            attempt_num = self._running_attempts.pop(task_id)
            self._attempts_used[task_id] = attempt_num + 1

            runtime = self._task_runtimes[task_id]
            ws_runtime = self._workstream_runtimes[runtime.task.workstream_id]

            try:
                result = done_task.result()
            except Exception:
                if await self._process_task_exception(task_id, attempt_num, ws_runtime):
                    break
                continue

            if result.status in SUCCESS_STATUSES:
                self._process_task_success(task_id, attempt_num)
                continue

            if result.status == TaskStatus.FAILED:
                if await self._process_task_failure(
                    task_id, attempt_num, result, ws_runtime
                ):
                    break
                continue

            if await self._process_unexpected_status(
                task_id, attempt_num, result, ws_runtime
            ):
                break

    # -- Per-outcome processing ----------------------------------------------

    async def _process_task_exception(
        self,
        task_id: str,
        attempt_num: int,
        ws_runtime: WorkstreamRuntime,
    ) -> bool:
        """Handle a task_runner.run() that raised an exception.

        Returns:
            True if the inner done-task loop should break (fail-fast triggered).
        """
        runtime = self._task_runtimes[task_id]
        self._fatal_error = traceback.format_exc()
        error_line = self._fatal_error.strip().splitlines()[-1]
        runtime.mark_failed(error_line)
        ws_runtime.mark_failed(error_line)
        self._emit(
            OrchestratorEvent(
                kind="task_finished",
                task_id=task_id,
                workstream_id=runtime.task.workstream_id,
                attempt_num=attempt_num,
                outcome_class=TaskOutcomeClass.INTERNAL_ERROR,
                message="task_runner.run raised; fail-fast",
            ),
        )
        if self._orchestrator.config.fail_fast_on_internal_error:
            await self._fail_fast_cancel(
                "canceled due to fatal internal orchestrator error"
            )
            return True
        return False

    def _process_task_success(self, task_id: str, attempt_num: int) -> None:
        """Handle a task that reached a terminal success status."""
        runtime = self._task_runtimes[task_id]
        self._completed_ids.add(task_id)
        self._emit(
            OrchestratorEvent(
                kind="task_finished",
                task_id=task_id,
                workstream_id=runtime.task.workstream_id,
                attempt_num=attempt_num,
                outcome_class=TaskOutcomeClass.SUCCESS,
                message=runtime.artifacts.pr_url,
            ),
        )
        self._refresh_workstream_terminal_states()
        self._process_merge_ready_workstreams()

    async def _process_task_failure(
        self,
        task_id: str,
        attempt_num: int,
        result: TaskRunResult,
        ws_runtime: WorkstreamRuntime,
    ) -> bool:
        """Handle a task that returned FAILED.

        Returns:
            True if the inner done-task loop should break (fail-fast triggered).
        """
        runtime = self._task_runtimes[task_id]
        config = self._orchestrator.config

        is_internal = result.failure_class == IntegrationFailureClass.INTERNAL_ERROR
        outcome_class = (
            TaskOutcomeClass.INTERNAL_ERROR
            if is_internal
            else TaskOutcomeClass.EXPECTED_FAILURE
        )
        should_retry = (
            not is_internal and self._attempts_used[task_id] < config.max_task_attempts
        )
        self._emit(
            OrchestratorEvent(
                kind="task_finished",
                task_id=task_id,
                workstream_id=runtime.task.workstream_id,
                attempt_num=attempt_num,
                outcome_class=outcome_class,
                message=("retry_scheduled" if should_retry else "max_attempts_reached"),
            ),
        )
        if should_retry:
            runtime.reset_for_retry()
        else:
            ws_runtime.mark_failed(runtime.state.error or "task failed")
        if is_internal and config.fail_fast_on_internal_error:
            await self._fail_fast_cancel("canceled due to internal integration error")
            self._fatal_error = runtime.state.error or "internal integration error"
            return True
        self._refresh_workstream_terminal_states()
        self._process_merge_ready_workstreams()
        return False

    async def _process_unexpected_status(
        self,
        task_id: str,
        attempt_num: int,
        result: TaskRunResult,
        ws_runtime: WorkstreamRuntime,
    ) -> bool:
        """Handle a task result with an unexpected (non-terminal) status.

        Returns:
            True if the inner done-task loop should break (fail-fast triggered).
        """
        runtime = self._task_runtimes[task_id]
        self._fatal_error = (
            f"RuntimeError: unexpected TaskRunner result status {result.status!r}"
        )
        runtime.mark_failed(self._fatal_error)
        ws_runtime.mark_failed(self._fatal_error)
        self._emit(
            OrchestratorEvent(
                kind="task_finished",
                task_id=task_id,
                workstream_id=runtime.task.workstream_id,
                attempt_num=attempt_num,
                outcome_class=TaskOutcomeClass.INTERNAL_ERROR,
                message="unexpected non-terminal TaskRunner result",
            ),
        )
        if self._orchestrator.config.fail_fast_on_internal_error:
            await self._fail_fast_cancel(
                "canceled due to fatal internal orchestrator error"
            )
            return True
        return False

    # -- Shared helpers ------------------------------------------------------

    def _emit(self, event: OrchestratorEvent) -> None:
        """Append event to the log and notify the listener, if any."""
        self._events.append(event)
        listener = self._orchestrator.listener
        if listener is not None:
            listener.on_event(event)

    def _all_tasks_terminal(self) -> bool:
        return all(
            runtime.status in SUCCESS_STATUSES or runtime.status == TaskStatus.FAILED
            for runtime in self._task_runtimes.values()
        )

    def _workstream_can_run(self, task_id: str) -> bool:
        graph = self._orchestrator.graph
        runtime = self._task_runtimes[task_id]
        workstream_id = runtime.task.workstream_id
        ws_runtime = self._workstream_runtimes[workstream_id]

        if ws_runtime.status in (
            WorkstreamStatus.FAILED,
            WorkstreamStatus.MERGE_READY,
            WorkstreamStatus.PR_CREATED,
            WorkstreamStatus.MERGED,
        ):
            return False

        task_ids_in_ws = graph.tasks_in_workstream(workstream_id)
        if any(
            self._task_runtimes[tid].status
            in (TaskStatus.RUNNING, TaskStatus.PR_CREATED)
            or tid in self._running
            for tid in task_ids_in_ws
        ):
            return False

        current = graph.workstream(workstream_id).parent_workstream_id
        while current is not None:
            parent_runtime = self._workstream_runtimes[current]
            if parent_runtime.status == WorkstreamStatus.FAILED:
                return False
            if parent_runtime.status not in (
                WorkstreamStatus.PR_CREATED,
                WorkstreamStatus.MERGED,
            ):
                return False
            current = graph.workstream(current).parent_workstream_id

        # Cross-workstream dependency gate: upstream workstreams (containing
        # dependencies in different workstreams) must be MERGED before dispatch.
        for upstream_ws_id in graph.upstream_workstream_ids(task_id):
            if (
                self._workstream_runtimes[upstream_ws_id].status
                != WorkstreamStatus.MERGED
            ):
                return False

        return True

    def _mark_blocked_pending_tasks_failed(self) -> bool:
        graph = self._orchestrator.graph
        changed = False
        for task_id in graph.task_ids():
            runtime = self._task_runtimes[task_id]
            if runtime.status != TaskStatus.PENDING:
                continue
            reason = self._blocked_reason(task_id)
            if reason is None:
                continue
            error = f"Blocked by orchestration rules: {reason}"
            runtime.mark_failed(error)
            ws_runtime = self._workstream_runtimes[runtime.task.workstream_id]
            if ws_runtime.status != WorkstreamStatus.FAILED:
                ws_runtime.mark_failed(error)
            self._emit(
                OrchestratorEvent(
                    kind="task_blocked",
                    task_id=task_id,
                    workstream_id=runtime.task.workstream_id,
                    outcome_class=TaskOutcomeClass.EXPECTED_FAILURE,
                    message=reason,
                ),
            )
            changed = True
        return changed

    def _blocked_reason(self, task_id: str) -> Optional[str]:
        graph = self._orchestrator.graph
        for dep_id in graph.dependency_ids(task_id):
            if self._task_runtimes[dep_id].status == TaskStatus.FAILED:
                return f"dependency '{dep_id}' failed"

        runtime = self._task_runtimes[task_id]
        workstream_id = runtime.task.workstream_id
        ws_runtime = self._workstream_runtimes[workstream_id]
        if ws_runtime.status == WorkstreamStatus.FAILED:
            return f"workstream '{workstream_id}' failed"

        parent_id = graph.workstream(workstream_id).parent_workstream_id
        while parent_id is not None:
            parent_runtime = self._workstream_runtimes[parent_id]
            if parent_runtime.status == WorkstreamStatus.FAILED:
                return f"ancestor workstream '{parent_id}' failed"
            if parent_runtime.status not in (
                WorkstreamStatus.PR_CREATED,
                WorkstreamStatus.MERGED,
            ):
                return f"waiting for parent workstream '{parent_id}' to complete integration"
            parent_id = graph.workstream(parent_id).parent_workstream_id

        # Cross-workstream dependency gate.
        for upstream_ws_id in graph.upstream_workstream_ids(task_id):
            upstream_runtime = self._workstream_runtimes[upstream_ws_id]
            if upstream_runtime.status == WorkstreamStatus.FAILED:
                return f"upstream workstream '{upstream_ws_id}' failed"
            if upstream_runtime.status != WorkstreamStatus.MERGED:
                if self._orchestrator.integration_merge_checker is None:
                    return (
                        f"upstream workstream '{upstream_ws_id}' awaiting"
                        " integration merge (no merge checker configured)"
                    )
                # Checker configured — not permanently blocked, just waiting.
                return None

        return None

    def _refresh_workstream_terminal_states(self) -> None:
        graph = self._orchestrator.graph
        for workstream_id in graph.workstream_ids():
            ws_runtime = self._workstream_runtimes[workstream_id]
            if ws_runtime.status in (
                WorkstreamStatus.FAILED,
                WorkstreamStatus.MERGE_READY,
                WorkstreamStatus.PR_CREATED,
                WorkstreamStatus.MERGED,
            ):
                continue
            task_ids = graph.tasks_in_workstream(workstream_id)
            if not task_ids or all(
                self._task_runtimes[task_id].status in SUCCESS_STATUSES
                for task_id in task_ids
            ):
                ws_runtime.mark_merge_ready()

    def _process_merge_ready_workstreams(self) -> None:
        """Create integration PRs for workstreams that have reached MERGE_READY.

        When a workstream has ``auto_merge=True`` on its spec and none of its
        tasks recorded design concerns, the integration PR is merged
        immediately after creation (via the configured
        :class:`IntegrationAutoMerger`).  Otherwise the PR is left for human
        review.
        """
        graph = self._orchestrator.graph
        for workstream_id in graph.workstream_ids():
            ws_runtime = self._workstream_runtimes[workstream_id]
            if ws_runtime.status == WorkstreamStatus.MERGE_READY:
                # Populate task summaries for the integration PR body.
                from agentrelay.workstream.core.runtime import TaskSummary

                def _read_summary(signal_dir: Path | None) -> str | None:
                    if signal_dir is None:
                        return None
                    path = signal_dir / "summary.md"
                    try:
                        text = path.read_text()
                    except OSError:
                        return None
                    return text.strip() or None

                task_ids = graph.tasks_in_workstream(workstream_id)
                ws_runtime.artifacts.task_summaries = [
                    TaskSummary(
                        task_id=tid,
                        description=self._task_runtimes[tid].task.description,
                        role=self._task_runtimes[tid].task.role.value,
                        pr_url=self._task_runtimes[tid].artifacts.pr_url,
                        concerns=tuple(self._task_runtimes[tid].artifacts.concerns),
                        ops_concerns=tuple(
                            self._task_runtimes[tid].artifacts.ops_concerns
                        ),
                        summary_text=_read_summary(
                            self._task_runtimes[tid].state.signal_dir
                        ),
                    )
                    for tid in task_ids
                ]
                result = self._orchestrator.workstream_runner.integrate(ws_runtime)

                if result.status == WorkstreamStatus.MERGED:
                    self._emit(
                        OrchestratorEvent(
                            kind="workstream_integration_skipped",
                            workstream_id=workstream_id,
                            message="no commits ahead of base — skipped integration PR",
                        ),
                    )
                elif result.status == WorkstreamStatus.PR_CREATED:
                    self._emit(
                        OrchestratorEvent(
                            kind="workstream_pr_created",
                            workstream_id=workstream_id,
                            message=ws_runtime.artifacts.merge_pr_url,
                        ),
                    )
                    self._try_auto_merge(workstream_id, ws_runtime)
                else:
                    self._emit(
                        OrchestratorEvent(
                            kind="workstream_integration_failed",
                            workstream_id=workstream_id,
                            message=result.error,
                        ),
                    )

    def _try_auto_merge(
        self, workstream_id: str, ws_runtime: WorkstreamRuntime
    ) -> None:
        """Attempt to auto-merge a workstream's integration PR.

        Auto-merge is attempted only when all of:
        - The workstream spec has ``auto_merge=True``.
        - An :class:`IntegrationAutoMerger` is configured on the orchestrator.
        - No task in the workstream recorded a design concern.

        On success the workstream transitions to ``MERGED`` and a
        ``workstream_auto_merged`` event is emitted.  On failure (merge call
        raises) a ``workstream_auto_merge_failed`` event is emitted and the
        workstream remains ``PR_CREATED`` for human review.  When auto-merge
        is skipped due to concerns, a ``workstream_auto_merge_skipped`` event
        is emitted.
        """
        spec = ws_runtime.spec
        if not spec.auto_merge:
            return

        merger = self._orchestrator.integration_auto_merger
        if merger is None:
            return

        has_concerns = any(s.concerns for s in ws_runtime.artifacts.task_summaries)
        if has_concerns:
            self._emit(
                OrchestratorEvent(
                    kind="workstream_auto_merge_skipped",
                    workstream_id=workstream_id,
                    message="design concerns found — leaving for human review",
                ),
            )
            return

        try:
            merger.merge(ws_runtime)
        except Exception as exc:  # noqa: BLE001
            self._emit(
                OrchestratorEvent(
                    kind="workstream_auto_merge_failed",
                    workstream_id=workstream_id,
                    message=str(exc),
                ),
            )
            return

        ws_runtime.mark_merged()
        self._emit(
            OrchestratorEvent(
                kind="workstream_auto_merged",
                workstream_id=workstream_id,
                message=ws_runtime.artifacts.merge_pr_url,
            ),
        )

    def _poll_integration_merges(self) -> None:
        """Check PR_CREATED workstreams for merge on the remote platform.

        For each workstream in ``PR_CREATED`` status, asks the configured
        :class:`IntegrationMergeChecker` whether the integration PR has been
        merged.  When a merge is detected, writes the ``merged`` signal file
        and emits a ``workstream_merged`` event.

        No-op when no :attr:`Orchestrator.integration_merge_checker` is set.
        """
        checker = self._orchestrator.integration_merge_checker
        if checker is None:
            return
        graph = self._orchestrator.graph
        for workstream_id in graph.workstream_ids():
            ws_runtime = self._workstream_runtimes[workstream_id]
            if ws_runtime.status != WorkstreamStatus.PR_CREATED:
                continue
            if checker.is_merged(ws_runtime):
                ws_runtime.mark_merged()
                self._emit(
                    OrchestratorEvent(
                        kind="workstream_merged",
                        workstream_id=workstream_id,
                        message=ws_runtime.artifacts.merge_pr_url,
                    ),
                )

    def _has_pending_integration_merges(self) -> bool:
        """True if any pending task is waiting for an upstream integration merge."""
        if self._orchestrator.integration_merge_checker is None:
            return False
        graph = self._orchestrator.graph
        for task_id in graph.task_ids():
            runtime = self._task_runtimes[task_id]
            if runtime.status != TaskStatus.PENDING:
                continue
            for ws_id in graph.upstream_workstream_ids(task_id):
                if (
                    self._workstream_runtimes[ws_id].status
                    == WorkstreamStatus.PR_CREATED
                ):
                    return True
        return False

    def _should_block_new_workstreams(self) -> bool:
        """Check whether new workstream preparation should be blocked."""
        if not self._orchestrator.config.fail_fast_on_workstream_error:
            return False
        return any(
            ws.status == WorkstreamStatus.FAILED
            for ws in self._workstream_runtimes.values()
        )

    async def _fail_fast_cancel(self, reason: str) -> None:
        """Mark in-flight tasks failed, cancel futures, and clear running."""
        self._mark_inflight_tasks_failed(reason)
        await self._cancel_running_tasks()
        self._running.clear()

    async def _cancel_running_tasks(self) -> None:
        if not self._running:
            return
        for task in self._running.values():
            task.cancel()
        await asyncio.gather(*self._running.values(), return_exceptions=True)

    def _task_id_for_future(self, done_task: asyncio.Task[TaskRunResult]) -> str:
        for task_id, task in self._running.items():
            if task is done_task:
                return task_id
        raise RuntimeError("Orchestrator internal error: completed task not tracked.")

    def _mark_inflight_tasks_failed(self, reason: str) -> None:
        """Mark in-flight tasks as failed when orchestration aborts."""
        for task_id in self._running:
            runtime = self._task_runtimes[task_id]
            if (
                runtime.status not in SUCCESS_STATUSES
                and runtime.status != TaskStatus.FAILED
            ):
                runtime.mark_failed(reason)
            else:
                runtime.state.error = reason
            ws_runtime = self._workstream_runtimes[runtime.task.workstream_id]
            if ws_runtime.status != WorkstreamStatus.FAILED:
                ws_runtime.mark_failed(reason)

    def _teardown_prepared_workstreams(self) -> None:
        """Teardown all workstreams that were prepared."""
        graph = self._orchestrator.graph
        for workstream_id in graph.workstream_ids():
            ws_runtime = self._workstream_runtimes[workstream_id]
            if ws_runtime.status != WorkstreamStatus.PENDING:
                self._orchestrator.workstream_runner.teardown(ws_runtime)

    def _build_result(self) -> OrchestratorResult:
        """Teardown workstreams and build the terminal result."""
        self._teardown_prepared_workstreams()

        if self._fatal_error is not None:
            outcome = OrchestratorOutcome.FATAL_INTERNAL_ERROR
        elif any(
            runtime.status == TaskStatus.FAILED
            for runtime in self._task_runtimes.values()
        ) or any(
            runtime.status == WorkstreamStatus.FAILED
            for runtime in self._workstream_runtimes.values()
        ):
            outcome = OrchestratorOutcome.COMPLETED_WITH_FAILURES
        else:
            outcome = OrchestratorOutcome.SUCCEEDED

        return OrchestratorResult(
            outcome=outcome,
            task_runtimes=MappingProxyType(self._task_runtimes),
            workstream_runtimes=MappingProxyType(self._workstream_runtimes),
            events=tuple(self._events),
            fatal_error=self._fatal_error,
        )
