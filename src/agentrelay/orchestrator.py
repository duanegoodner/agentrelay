"""Graph-level orchestration loop for task and workstream runtimes.

This module schedules tasks from a :class:`agentrelay.task_graph.TaskGraph`
using dependency readiness and workstream constraints, then delegates one-task
execution to :class:`agentrelay.task_runner.TaskRunner`.
"""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Optional, Protocol, runtime_checkable

from agentrelay.errors import IntegrationFailureClass
from agentrelay.task_graph import TaskGraph
from agentrelay.task_runner import TaskRunResult, TearDownMode
from agentrelay.task_runtime import TaskRuntime, TaskRuntimeBuilder, TaskStatus
from agentrelay.workstream import (
    WorkstreamRuntime,
    WorkstreamRuntimeBuilder,
    WorkstreamStatus,
)


class TaskOutcomeClass(str, Enum):
    """Classification of one task attempt outcome from the orchestrator boundary.

    Attributes:
        SUCCESS: Task reached ``PR_MERGED``.
        EXPECTED_FAILURE: Task run returned ``FAILED``.
        INTERNAL_ERROR: Task run raised an exception.
    """

    SUCCESS = "success"
    EXPECTED_FAILURE = "expected_failure"
    INTERNAL_ERROR = "internal_error"


class OrchestratorOutcome(str, Enum):
    """Terminal outcome for one orchestrator run.

    Attributes:
        SUCCEEDED: All tasks reached ``PR_MERGED``.
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
    """

    max_concurrency: int = 1
    max_task_attempts: int = 1
    task_teardown_mode: TearDownMode = TearDownMode.ON_SUCCESS
    fail_fast_on_internal_error: bool = True


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
    task_id: Optional[str] = None
    workstream_id: Optional[str] = None
    attempt_num: Optional[int] = None
    outcome_class: Optional[TaskOutcomeClass] = None
    message: Optional[str] = None


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


@runtime_checkable
class TaskRunnerLike(Protocol):
    """Protocol for the task runner boundary used by :class:`Orchestrator`."""

    async def run(
        self,
        runtime: TaskRuntime,
        *,
        teardown_mode: TearDownMode = TearDownMode.ALWAYS,
    ) -> TaskRunResult:
        """Execute one task attempt and return terminal task fields."""
        ...


@dataclass
class Orchestrator:
    """Async graph scheduler using dependency + workstream constraints."""

    graph: TaskGraph
    task_runner: TaskRunnerLike
    config: OrchestratorConfig = field(default_factory=OrchestratorConfig)

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
        self._validate_config()

        mutable_task_runtimes = self._init_task_runtimes(task_runtimes)
        mutable_workstream_runtimes = self._init_workstream_runtimes(
            workstream_runtimes
        )

        events: list[OrchestratorEvent] = []
        completed_ids = {
            task_id
            for task_id, runtime in mutable_task_runtimes.items()
            if runtime.state.status == TaskStatus.PR_MERGED
        }
        attempts_used = self._initialize_attempts_used(mutable_task_runtimes)
        self._normalize_failed_for_retry(mutable_task_runtimes, attempts_used)
        self._refresh_workstream_terminal_states(
            mutable_task_runtimes, mutable_workstream_runtimes
        )

        running: dict[str, asyncio.Task[TaskRunResult]] = {}
        running_attempts: dict[str, int] = {}
        fatal_error: Optional[str] = None

        while True:
            if self._all_tasks_terminal(mutable_task_runtimes):
                break

            if fatal_error is not None:
                break

            ready_ids = self.graph.ready_ids(
                completed_ids=completed_ids,
                running_ids=running.keys(),
            )
            for task_id in ready_ids:
                if len(running) >= self.config.max_concurrency:
                    break
                runtime = mutable_task_runtimes[task_id]
                if runtime.state.status != TaskStatus.PENDING:
                    continue
                if not self._workstream_can_run(
                    task_id, mutable_task_runtimes, mutable_workstream_runtimes
                ):
                    continue

                attempt_num = attempts_used[task_id]
                runtime.prepare_for_attempt(attempt_num)
                ws_runtime = mutable_workstream_runtimes[runtime.task.workstream_id]
                ws_runtime.activate(task_id)
                events.append(
                    OrchestratorEvent(
                        kind="task_started",
                        task_id=task_id,
                        workstream_id=runtime.task.workstream_id,
                        attempt_num=attempt_num,
                    )
                )
                running[task_id] = asyncio.create_task(
                    self.task_runner.run(
                        runtime, teardown_mode=self.config.task_teardown_mode
                    )
                )
                running_attempts[task_id] = attempt_num

            if not running:
                changed = self._mark_blocked_pending_tasks_failed(
                    mutable_task_runtimes,
                    mutable_workstream_runtimes,
                    events,
                )
                if not changed:
                    break
                self._refresh_workstream_terminal_states(
                    mutable_task_runtimes, mutable_workstream_runtimes
                )
                continue

            done, _ = await asyncio.wait(
                running.values(), return_when=asyncio.FIRST_COMPLETED
            )
            for done_task in done:
                task_id = self._task_id_for_future(running, done_task)
                del running[task_id]
                attempt_num = running_attempts.pop(task_id)
                attempts_used[task_id] = attempt_num + 1

                runtime = mutable_task_runtimes[task_id]
                ws_runtime = mutable_workstream_runtimes[runtime.task.workstream_id]
                ws_runtime.deactivate()

                try:
                    result = done_task.result()
                except Exception:
                    fatal_error = traceback.format_exc()
                    error_line = fatal_error.strip().splitlines()[-1]
                    runtime.mark_failed(error_line)
                    ws_runtime.mark_failed(error_line)
                    events.append(
                        OrchestratorEvent(
                            kind="task_finished",
                            task_id=task_id,
                            workstream_id=runtime.task.workstream_id,
                            attempt_num=attempt_num,
                            outcome_class=TaskOutcomeClass.INTERNAL_ERROR,
                            message="task_runner.run raised; fail-fast",
                        )
                    )
                    if self.config.fail_fast_on_internal_error:
                        self._mark_inflight_tasks_failed(
                            running_task_ids=running.keys(),
                            task_runtimes=mutable_task_runtimes,
                            workstream_runtimes=mutable_workstream_runtimes,
                            reason="canceled due to fatal internal orchestrator error",
                        )
                        await self._cancel_running_tasks(running)
                        running.clear()
                        break
                    continue

                if result.status == TaskStatus.PR_MERGED:
                    completed_ids.add(task_id)
                    events.append(
                        OrchestratorEvent(
                            kind="task_finished",
                            task_id=task_id,
                            workstream_id=runtime.task.workstream_id,
                            attempt_num=attempt_num,
                            outcome_class=TaskOutcomeClass.SUCCESS,
                        )
                    )
                    self._refresh_workstream_terminal_states(
                        mutable_task_runtimes, mutable_workstream_runtimes
                    )
                    continue

                if result.status == TaskStatus.FAILED:
                    is_internal = (
                        result.failure_class == IntegrationFailureClass.INTERNAL_ERROR
                    )
                    outcome_class = (
                        TaskOutcomeClass.INTERNAL_ERROR
                        if is_internal
                        else TaskOutcomeClass.EXPECTED_FAILURE
                    )
                    should_retry = (
                        not is_internal
                        and attempts_used[task_id] < self.config.max_task_attempts
                    )
                    events.append(
                        OrchestratorEvent(
                            kind="task_finished",
                            task_id=task_id,
                            workstream_id=runtime.task.workstream_id,
                            attempt_num=attempt_num,
                            outcome_class=outcome_class,
                            message=(
                                "retry_scheduled"
                                if should_retry
                                else "max_attempts_reached"
                            ),
                        )
                    )
                    if should_retry:
                        runtime.reset_for_retry()
                    else:
                        ws_runtime.mark_failed(runtime.state.error or "task failed")
                    if is_internal and self.config.fail_fast_on_internal_error:
                        self._mark_inflight_tasks_failed(
                            running_task_ids=running.keys(),
                            task_runtimes=mutable_task_runtimes,
                            workstream_runtimes=mutable_workstream_runtimes,
                            reason="canceled due to internal integration error",
                        )
                        await self._cancel_running_tasks(running)
                        running.clear()
                        fatal_error = (
                            runtime.state.error or "internal integration error"
                        )
                        break
                    self._refresh_workstream_terminal_states(
                        mutable_task_runtimes, mutable_workstream_runtimes
                    )
                    continue

                fatal_error = f"RuntimeError: unexpected TaskRunner result status {result.status!r}"
                runtime.mark_failed(fatal_error)
                ws_runtime.mark_failed(fatal_error)
                events.append(
                    OrchestratorEvent(
                        kind="task_finished",
                        task_id=task_id,
                        workstream_id=runtime.task.workstream_id,
                        attempt_num=attempt_num,
                        outcome_class=TaskOutcomeClass.INTERNAL_ERROR,
                        message="unexpected non-terminal TaskRunner result",
                    )
                )
                if self.config.fail_fast_on_internal_error:
                    self._mark_inflight_tasks_failed(
                        running_task_ids=running.keys(),
                        task_runtimes=mutable_task_runtimes,
                        workstream_runtimes=mutable_workstream_runtimes,
                        reason="canceled due to fatal internal orchestrator error",
                    )
                    await self._cancel_running_tasks(running)
                    running.clear()
                    break

        if fatal_error is not None:
            outcome = OrchestratorOutcome.FATAL_INTERNAL_ERROR
        elif any(
            runtime.state.status == TaskStatus.FAILED
            for runtime in mutable_task_runtimes.values()
        ):
            outcome = OrchestratorOutcome.COMPLETED_WITH_FAILURES
        else:
            outcome = OrchestratorOutcome.SUCCEEDED

        return OrchestratorResult(
            outcome=outcome,
            task_runtimes=MappingProxyType(mutable_task_runtimes),
            workstream_runtimes=MappingProxyType(mutable_workstream_runtimes),
            events=tuple(events),
            fatal_error=fatal_error,
        )

    def _validate_config(self) -> None:
        if self.config.max_concurrency < 1:
            raise ValueError("OrchestratorConfig.max_concurrency must be >= 1.")
        if self.config.max_task_attempts < 1:
            raise ValueError("OrchestratorConfig.max_task_attempts must be >= 1.")

    def _init_task_runtimes(
        self, task_runtimes: Optional[Mapping[str, TaskRuntime]]
    ) -> dict[str, TaskRuntime]:
        if task_runtimes is None:
            return TaskRuntimeBuilder.from_graph(self.graph)
        runtimes = dict(task_runtimes)
        expected = set(self.graph.task_ids())
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
        if workstream_runtimes is None:
            return WorkstreamRuntimeBuilder.from_graph(self.graph)
        runtimes = dict(workstream_runtimes)
        expected = set(self.graph.workstream_ids())
        actual = set(runtimes.keys())
        if actual != expected:
            raise ValueError(
                "workstream_runtimes keys must match graph.workstream_ids(). "
                f"Missing={sorted(expected - actual)}, extra={sorted(actual - expected)}."
            )
        return runtimes

    def _initialize_attempts_used(
        self, task_runtimes: Mapping[str, TaskRuntime]
    ) -> dict[str, int]:
        attempts_used: dict[str, int] = {}
        for task_id, runtime in task_runtimes.items():
            status = runtime.state.status
            if status in (TaskStatus.RUNNING, TaskStatus.PR_CREATED):
                raise ValueError(
                    "Resume from RUNNING/PR_CREATED is not yet supported. "
                    f"Task '{task_id}' is in state {status.value!r}."
                )
            if status in (TaskStatus.PR_MERGED, TaskStatus.FAILED):
                attempts_used[task_id] = runtime.state.attempt_num + 1
            else:
                attempts_used[task_id] = runtime.state.attempt_num
        return attempts_used

    def _normalize_failed_for_retry(
        self,
        task_runtimes: Mapping[str, TaskRuntime],
        attempts_used: Mapping[str, int],
    ) -> None:
        for task_id, runtime in task_runtimes.items():
            if runtime.state.status != TaskStatus.FAILED:
                continue
            if attempts_used[task_id] < self.config.max_task_attempts:
                runtime.mark_pending()

    def _all_tasks_terminal(self, task_runtimes: Mapping[str, TaskRuntime]) -> bool:
        return all(
            runtime.state.status in (TaskStatus.PR_MERGED, TaskStatus.FAILED)
            for runtime in task_runtimes.values()
        )

    def _workstream_can_run(
        self,
        task_id: str,
        task_runtimes: Mapping[str, TaskRuntime],
        workstream_runtimes: Mapping[str, WorkstreamRuntime],
    ) -> bool:
        runtime = task_runtimes[task_id]
        workstream_id = runtime.task.workstream_id
        ws_runtime = workstream_runtimes[workstream_id]

        if ws_runtime.state.status == WorkstreamStatus.FAILED:
            return False
        if ws_runtime.state.active_task_id is not None:
            return False

        current = self.graph.workstream(workstream_id).parent_workstream_id
        while current is not None:
            parent_runtime = workstream_runtimes[current]
            if parent_runtime.state.status == WorkstreamStatus.FAILED:
                return False
            if parent_runtime.state.status != WorkstreamStatus.MERGED:
                return False
            current = self.graph.workstream(current).parent_workstream_id

        return True

    def _mark_blocked_pending_tasks_failed(
        self,
        task_runtimes: Mapping[str, TaskRuntime],
        workstream_runtimes: Mapping[str, WorkstreamRuntime],
        events: list[OrchestratorEvent],
    ) -> bool:
        changed = False
        for task_id in self.graph.task_ids():
            runtime = task_runtimes[task_id]
            if runtime.state.status != TaskStatus.PENDING:
                continue
            reason = self._blocked_reason(task_id, task_runtimes, workstream_runtimes)
            if reason is None:
                continue
            error = f"Blocked by orchestration rules: {reason}"
            runtime.mark_failed(error)
            ws_runtime = workstream_runtimes[runtime.task.workstream_id]
            if ws_runtime.state.status != WorkstreamStatus.FAILED:
                ws_runtime.mark_failed(error)
            events.append(
                OrchestratorEvent(
                    kind="task_blocked",
                    task_id=task_id,
                    workstream_id=runtime.task.workstream_id,
                    outcome_class=TaskOutcomeClass.EXPECTED_FAILURE,
                    message=reason,
                )
            )
            changed = True
        return changed

    def _blocked_reason(
        self,
        task_id: str,
        task_runtimes: Mapping[str, TaskRuntime],
        workstream_runtimes: Mapping[str, WorkstreamRuntime],
    ) -> Optional[str]:
        for dep_id in self.graph.dependency_ids(task_id):
            if task_runtimes[dep_id].state.status == TaskStatus.FAILED:
                return f"dependency '{dep_id}' failed"

        runtime = task_runtimes[task_id]
        workstream_id = runtime.task.workstream_id
        ws_runtime = workstream_runtimes[workstream_id]
        if ws_runtime.state.status == WorkstreamStatus.FAILED:
            return f"workstream '{workstream_id}' failed"

        parent_id = self.graph.workstream(workstream_id).parent_workstream_id
        while parent_id is not None:
            parent_runtime = workstream_runtimes[parent_id]
            if parent_runtime.state.status == WorkstreamStatus.FAILED:
                return f"ancestor workstream '{parent_id}' failed"
            if parent_runtime.state.status != WorkstreamStatus.MERGED:
                return f"waiting for parent workstream '{parent_id}' to reach MERGED"
            parent_id = self.graph.workstream(parent_id).parent_workstream_id
        return None

    def _refresh_workstream_terminal_states(
        self,
        task_runtimes: Mapping[str, TaskRuntime],
        workstream_runtimes: Mapping[str, WorkstreamRuntime],
    ) -> None:
        for workstream_id in self.graph.workstream_ids():
            ws_runtime = workstream_runtimes[workstream_id]
            if ws_runtime.state.status == WorkstreamStatus.FAILED:
                continue
            task_ids = self.graph.tasks_in_workstream(workstream_id)
            if not task_ids or all(
                task_runtimes[task_id].state.status == TaskStatus.PR_MERGED
                for task_id in task_ids
            ):
                ws_runtime.mark_merged()

    async def _cancel_running_tasks(
        self, running: Mapping[str, asyncio.Task[TaskRunResult]]
    ) -> None:
        if not running:
            return
        for task in running.values():
            task.cancel()
        await asyncio.gather(*running.values(), return_exceptions=True)

    def _task_id_for_future(
        self,
        running: Mapping[str, asyncio.Task[TaskRunResult]],
        done_task: asyncio.Task[TaskRunResult],
    ) -> str:
        for task_id, task in running.items():
            if task is done_task:
                return task_id
        raise RuntimeError("Orchestrator internal error: completed task not tracked.")

    def _mark_inflight_tasks_failed(
        self,
        running_task_ids: Iterable[str],
        task_runtimes: Mapping[str, TaskRuntime],
        workstream_runtimes: Mapping[str, WorkstreamRuntime],
        reason: str,
    ) -> None:
        """Mark in-flight tasks as failed when orchestration aborts."""
        for task_id in running_task_ids:
            runtime = task_runtimes[task_id]
            if runtime.state.status not in (TaskStatus.PR_MERGED, TaskStatus.FAILED):
                runtime.mark_failed(reason)
            else:
                runtime.state.error = reason
            ws_runtime = workstream_runtimes[runtime.task.workstream_id]
            ws_runtime.deactivate()
            if ws_runtime.state.status != WorkstreamStatus.FAILED:
                ws_runtime.mark_failed(reason)
