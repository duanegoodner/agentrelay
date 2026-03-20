"""Tests for graph-level orchestration behavior."""

import asyncio
from dataclasses import dataclass, field

import pytest

from agentrelay.errors import IntegrationFailureClass
from agentrelay.orchestrator import (
    Orchestrator,
    OrchestratorConfig,
    OrchestratorOutcome,
    TaskOutcomeClass,
)
from agentrelay.task import AgentRole, Task
from agentrelay.task_graph import TaskGraph
from agentrelay.task_runner import TaskRunResult, TearDownMode
from agentrelay.task_runtime import TaskRuntime, TaskStatus
from agentrelay.workstream import (
    WorkstreamRunResult,
    WorkstreamRuntime,
    WorkstreamSpec,
    WorkstreamStatus,
)


def _task(
    task_id: str,
    *,
    dependencies: tuple[str, ...] = (),
    workstream_id: str = "default",
) -> Task:
    return Task(
        id=task_id,
        role=AgentRole.GENERIC,
        dependencies=dependencies,
        workstream_id=workstream_id,
    )


@dataclass
class ScriptedTaskRunner:
    """TaskRunner double with per-task/attempt scripted outcomes."""

    script: dict[tuple[str, int], str] = field(default_factory=dict)
    calls: list[tuple[str, int, TearDownMode]] = field(default_factory=list)

    async def run(
        self,
        runtime: TaskRuntime,
        *,
        teardown_mode: TearDownMode = TearDownMode.ALWAYS,
    ) -> TaskRunResult:
        task_id = runtime.task.id
        attempt_num = runtime.state.attempt_num
        self.calls.append((task_id, attempt_num, teardown_mode))
        action = self.script.get((task_id, attempt_num), "success")

        if action == "raise":
            raise RuntimeError(f"{task_id} internal boom")
        if action == "block":
            await asyncio.sleep(10)
        if action == "fail":
            runtime.state.status = TaskStatus.FAILED
            runtime.state.error = f"{task_id} failed"
            return TaskRunResult.from_runtime(runtime)
        if action == "fail_internal":
            runtime.state.status = TaskStatus.FAILED
            runtime.state.error = f"{task_id} internal adapter error"
            return TaskRunResult.from_runtime(
                runtime,
                failure_class=IntegrationFailureClass.INTERNAL_ERROR,
            )
        if action == "fail_expected":
            runtime.state.status = TaskStatus.FAILED
            runtime.state.error = f"{task_id} expected adapter failure"
            return TaskRunResult.from_runtime(
                runtime,
                failure_class=IntegrationFailureClass.EXPECTED_TASK_FAILURE,
            )

        runtime.artifacts.pr_url = f"https://example.com/{task_id}/{attempt_num}"
        runtime.state.status = TaskStatus.PR_MERGED
        runtime.state.error = None
        return TaskRunResult.from_runtime(runtime)


@dataclass
class NoOpWorkstreamRunner:
    """WorkstreamRunner double that performs state transitions without I/O."""

    prepare_calls: list[str] = field(default_factory=list)
    merge_calls: list[str] = field(default_factory=list)
    teardown_calls: list[str] = field(default_factory=list)

    def prepare(self, workstream_runtime: WorkstreamRuntime) -> None:  # noqa: D102
        self.prepare_calls.append(workstream_runtime.spec.id)
        workstream_runtime.state.status = WorkstreamStatus.ACTIVE

    def merge(  # noqa: D102
        self, workstream_runtime: WorkstreamRuntime
    ) -> WorkstreamRunResult:
        self.merge_calls.append(workstream_runtime.spec.id)
        workstream_runtime.state.status = WorkstreamStatus.MERGED
        return WorkstreamRunResult.from_runtime(workstream_runtime)

    def teardown(self, workstream_runtime: WorkstreamRuntime) -> None:  # noqa: D102
        self.teardown_calls.append(workstream_runtime.spec.id)


def _noop_ws_runner() -> NoOpWorkstreamRunner:
    return NoOpWorkstreamRunner()


def test_one_active_task_per_workstream() -> None:
    """Two independent tasks on the same workstream must run serially.

    Uses a yielding runner so asyncio has a chance to schedule both tasks
    concurrently if the dispatch guard fails.
    """

    @dataclass
    class _ConcurrencyTracker:
        active: int = 0
        peak: int = 0
        order: list[str] = field(default_factory=list)

        async def run(
            self,
            runtime: TaskRuntime,
            *,
            teardown_mode: TearDownMode = TearDownMode.ALWAYS,
        ) -> TaskRunResult:
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.order.append(runtime.task.id)
            # Yield so the event loop can start a second task if dispatched.
            await asyncio.sleep(0)
            self.active -= 1
            runtime.artifacts.pr_url = f"https://example.com/{runtime.task.id}/0"
            runtime.state.status = TaskStatus.PR_MERGED
            return TaskRunResult.from_runtime(runtime)

    task_a = _task("a")
    task_b = _task("b")
    graph = TaskGraph.from_tasks((task_a, task_b))
    tracker = _ConcurrencyTracker()
    orchestrator = Orchestrator(
        graph=graph,
        task_runner=tracker,
        workstream_runner=_noop_ws_runner(),
        config=OrchestratorConfig(max_concurrency=2),
    )

    result = asyncio.run(orchestrator.run())

    assert result.outcome == OrchestratorOutcome.SUCCEEDED
    assert (
        tracker.peak == 1
    ), f"expected serial execution, but peak concurrency was {tracker.peak}"
    assert tracker.order == ["a", "b"]
    assert result.workstream_runtimes["default"].state.status == WorkstreamStatus.MERGED


def test_same_workstream_dispatch_race_regression() -> None:
    """Regression: two tasks must not be dispatched together in one loop pass.

    Before the fix, ``_workstream_can_run`` only checked ``TaskStatus.RUNNING``
    which had not yet been set for a task that was just added to
    ``self._running`` via ``asyncio.create_task``.  This allowed a second task
    in the same workstream to slip through in the same synchronous dispatch
    loop, causing both agents to land in the same git worktree.
    """

    overlap_detected = False

    @dataclass
    class _OverlapDetector:
        active: int = 0

        async def run(
            self,
            runtime: TaskRuntime,
            *,
            teardown_mode: TearDownMode = TearDownMode.ALWAYS,
        ) -> TaskRunResult:
            nonlocal overlap_detected
            self.active += 1
            if self.active > 1:
                overlap_detected = True
            # Multiple yields to give the scheduler every opportunity.
            for _ in range(3):
                await asyncio.sleep(0)
            self.active -= 1
            runtime.artifacts.pr_url = f"https://example.com/{runtime.task.id}/0"
            runtime.state.status = TaskStatus.PR_MERGED
            return TaskRunResult.from_runtime(runtime)

    graph = TaskGraph.from_tasks((_task("x"), _task("y")))
    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=_OverlapDetector(),
            workstream_runner=_noop_ws_runner(),
            config=OrchestratorConfig(max_concurrency=2),
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.SUCCEEDED
    assert not overlap_detected, "two tasks in the same workstream ran concurrently"


def test_parent_workstream_must_merge_before_child_tasks_run() -> None:
    parent_stream = WorkstreamSpec(id="a")
    child_stream = WorkstreamSpec(id="b", parent_workstream_id="a")
    task_parent = _task("parent_task", workstream_id="a")
    task_child = _task("child_task", workstream_id="b")
    graph = TaskGraph.from_tasks(
        (task_parent, task_child),
        workstreams=(parent_stream, child_stream),
    )
    runner = ScriptedTaskRunner()

    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=runner,
            workstream_runner=_noop_ws_runner(),
            config=OrchestratorConfig(max_concurrency=2),
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.SUCCEEDED
    assert [task_id for task_id, _, _ in runner.calls] == ["parent_task", "child_task"]
    assert result.workstream_runtimes["a"].state.status == WorkstreamStatus.MERGED
    assert result.workstream_runtimes["b"].state.status == WorkstreamStatus.MERGED


def test_expected_failure_is_retried_until_success() -> None:
    task = _task("retry_me")
    graph = TaskGraph.from_tasks((task,))
    runner = ScriptedTaskRunner(
        script={
            ("retry_me", 0): "fail",
            ("retry_me", 1): "success",
        }
    )

    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=runner,
            workstream_runner=_noop_ws_runner(),
            config=OrchestratorConfig(max_task_attempts=2),
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.SUCCEEDED
    assert [attempt for _, attempt, _ in runner.calls] == [0, 1]
    assert result.task_runtimes["retry_me"].state.status == TaskStatus.PR_MERGED
    assert result.task_runtimes["retry_me"].state.attempt_num == 1
    assert any(
        event.outcome_class == TaskOutcomeClass.EXPECTED_FAILURE
        and event.message == "retry_scheduled"
        for event in result.events
    )


def test_expected_failure_without_retries_is_terminal() -> None:
    task = _task("fails_once")
    graph = TaskGraph.from_tasks((task,))
    runner = ScriptedTaskRunner(script={("fails_once", 0): "fail"})

    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=runner,
            workstream_runner=_noop_ws_runner(),
            config=OrchestratorConfig(max_task_attempts=1),
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.COMPLETED_WITH_FAILURES
    assert len(runner.calls) == 1
    assert result.task_runtimes["fails_once"].state.status == TaskStatus.FAILED
    assert result.workstream_runtimes["default"].state.status == WorkstreamStatus.FAILED
    assert any(
        event.outcome_class == TaskOutcomeClass.EXPECTED_FAILURE
        and event.message == "max_attempts_reached"
        for event in result.events
    )


def test_raised_task_runner_error_is_internal_fail_fast() -> None:
    task = _task("explodes")
    graph = TaskGraph.from_tasks((task,))
    runner = ScriptedTaskRunner(script={("explodes", 0): "raise"})

    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=runner,
            workstream_runner=_noop_ws_runner(),
            config=OrchestratorConfig(max_task_attempts=3),
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.FATAL_INTERNAL_ERROR
    assert len(runner.calls) == 1
    assert result.task_runtimes["explodes"].state.status == TaskStatus.FAILED
    assert result.fatal_error is not None
    assert "RuntimeError: explodes internal boom" in result.fatal_error
    assert any(
        event.outcome_class == TaskOutcomeClass.INTERNAL_ERROR
        for event in result.events
    )


def test_fail_fast_internal_error_cancels_other_inflight_tasks() -> None:
    stream_a = WorkstreamSpec(id="a")
    stream_b = WorkstreamSpec(id="b")
    task_a = _task("explodes", workstream_id="a")
    task_b = _task("blocked", workstream_id="b")
    graph = TaskGraph.from_tasks(
        (task_a, task_b),
        workstreams=(stream_a, stream_b),
    )
    runner = ScriptedTaskRunner(
        script={
            ("explodes", 0): "raise",
            ("blocked", 0): "block",
        }
    )

    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=runner,
            workstream_runner=_noop_ws_runner(),
            config=OrchestratorConfig(max_concurrency=2),
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.FATAL_INTERNAL_ERROR
    assert result.task_runtimes["explodes"].state.status == TaskStatus.FAILED
    assert result.task_runtimes["blocked"].state.status == TaskStatus.FAILED
    assert (
        result.task_runtimes["blocked"].state.error
        == "canceled due to fatal internal orchestrator error"
    )
    assert result.workstream_runtimes["b"].state.status == WorkstreamStatus.FAILED


def test_teardown_mode_is_forwarded_to_task_runner() -> None:
    task = _task("one")
    graph = TaskGraph.from_tasks((task,))
    runner = ScriptedTaskRunner()

    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=runner,
            workstream_runner=_noop_ws_runner(),
            config=OrchestratorConfig(task_teardown_mode=TearDownMode.NEVER),
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.SUCCEEDED
    assert runner.calls == [("one", 0, TearDownMode.NEVER)]


def test_descendant_workstream_task_is_blocked_after_parent_failure() -> None:
    parent_stream = WorkstreamSpec(id="a")
    child_stream = WorkstreamSpec(id="b", parent_workstream_id="a")
    task_parent = _task("parent_task", workstream_id="a")
    task_child = _task("child_task", workstream_id="b")
    graph = TaskGraph.from_tasks(
        (task_parent, task_child),
        workstreams=(parent_stream, child_stream),
    )
    runner = ScriptedTaskRunner(script={("parent_task", 0): "fail"})

    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=runner,
            workstream_runner=_noop_ws_runner(),
            config=OrchestratorConfig(max_task_attempts=1),
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.COMPLETED_WITH_FAILURES
    assert [task_id for task_id, _, _ in runner.calls] == ["parent_task"]
    assert result.task_runtimes["parent_task"].state.status == TaskStatus.FAILED
    assert result.task_runtimes["child_task"].state.status == TaskStatus.FAILED
    assert "ancestor workstream 'a' failed" in (
        result.task_runtimes["child_task"].state.error or ""
    )
    assert any(
        event.kind == "task_blocked" and event.task_id == "child_task"
        for event in result.events
    )


@pytest.mark.parametrize(
    "config",
    [
        OrchestratorConfig(max_concurrency=0),
        OrchestratorConfig(max_task_attempts=0),
    ],
)
def test_invalid_config_raises(config: OrchestratorConfig) -> None:
    graph = TaskGraph.from_tasks((_task("a"),))
    runner = ScriptedTaskRunner()
    orchestrator = Orchestrator(
        graph=graph,
        task_runner=runner,
        workstream_runner=_noop_ws_runner(),
        config=config,
    )

    with pytest.raises(ValueError):
        asyncio.run(orchestrator.run())


def test_internal_failure_class_triggers_fail_fast() -> None:
    task = _task("adapter_fails")
    graph = TaskGraph.from_tasks((task,))
    runner = ScriptedTaskRunner(script={("adapter_fails", 0): "fail_internal"})

    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=runner,
            workstream_runner=_noop_ws_runner(),
            config=OrchestratorConfig(
                max_task_attempts=3, fail_fast_on_internal_error=True
            ),
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.FATAL_INTERNAL_ERROR
    assert len(runner.calls) == 1
    assert result.task_runtimes["adapter_fails"].state.status == TaskStatus.FAILED
    assert any(
        event.outcome_class == TaskOutcomeClass.INTERNAL_ERROR
        for event in result.events
    )


def test_internal_failure_class_is_not_retried() -> None:
    task = _task("no_retry")
    graph = TaskGraph.from_tasks((task,))
    runner = ScriptedTaskRunner(script={("no_retry", 0): "fail_internal"})

    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=runner,
            workstream_runner=_noop_ws_runner(),
            config=OrchestratorConfig(
                max_task_attempts=3, fail_fast_on_internal_error=False
            ),
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.COMPLETED_WITH_FAILURES
    assert len(runner.calls) == 1


def test_expected_failure_class_allows_retry() -> None:
    task = _task("retry_expected")
    graph = TaskGraph.from_tasks((task,))
    runner = ScriptedTaskRunner(
        script={
            ("retry_expected", 0): "fail_expected",
            ("retry_expected", 1): "success",
        }
    )

    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=runner,
            workstream_runner=_noop_ws_runner(),
            config=OrchestratorConfig(max_task_attempts=2),
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.SUCCEEDED
    assert len(runner.calls) == 2
    assert any(
        event.outcome_class == TaskOutcomeClass.EXPECTED_FAILURE
        and event.message == "retry_scheduled"
        for event in result.events
    )


# ── WorkstreamRunner lifecycle tests ──


def test_workstream_runner_prepare_called_before_first_task() -> None:
    task_a = _task("a")
    task_b = _task("b", dependencies=("a",))
    graph = TaskGraph.from_tasks((task_a, task_b))
    runner = ScriptedTaskRunner()
    ws_runner = NoOpWorkstreamRunner()

    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=runner,
            workstream_runner=ws_runner,
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.SUCCEEDED
    assert ws_runner.prepare_calls == ["default"]


def test_workstream_runner_merge_called_after_all_tasks_succeed() -> None:
    task_a = _task("a")
    task_b = _task("b", dependencies=("a",))
    graph = TaskGraph.from_tasks((task_a, task_b))
    runner = ScriptedTaskRunner()
    ws_runner = NoOpWorkstreamRunner()

    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=runner,
            workstream_runner=ws_runner,
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.SUCCEEDED
    assert ws_runner.merge_calls == ["default"]
    assert result.workstream_runtimes["default"].state.status == WorkstreamStatus.MERGED


def test_workstream_runner_teardown_called_after_loop() -> None:
    task = _task("a")
    graph = TaskGraph.from_tasks((task,))
    runner = ScriptedTaskRunner()
    ws_runner = NoOpWorkstreamRunner()

    asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=runner,
            workstream_runner=ws_runner,
        ).run()
    )

    assert ws_runner.teardown_calls == ["default"]


def test_workstream_prepare_failure_marks_workstream_failed() -> None:
    @dataclass
    class FailingPrepareRunner:
        def prepare(self, workstream_runtime: WorkstreamRuntime) -> None:
            workstream_runtime.state.status = WorkstreamStatus.FAILED
            workstream_runtime.state.error = "prepare boom"
            raise RuntimeError("prepare boom")

        def merge(self, workstream_runtime: WorkstreamRuntime) -> WorkstreamRunResult:
            workstream_runtime.state.status = WorkstreamStatus.MERGED
            return WorkstreamRunResult.from_runtime(workstream_runtime)

        def teardown(self, workstream_runtime: WorkstreamRuntime) -> None:
            pass

    task = _task("a")
    graph = TaskGraph.from_tasks((task,))
    runner = ScriptedTaskRunner()

    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=runner,
            workstream_runner=FailingPrepareRunner(),
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.COMPLETED_WITH_FAILURES
    assert len(runner.calls) == 0
    assert result.workstream_runtimes["default"].state.status == WorkstreamStatus.FAILED
    assert any(event.kind == "workstream_prepare_failed" for event in result.events)


def test_fail_fast_on_workstream_error_blocks_new_workstreams() -> None:
    stream_a = WorkstreamSpec(id="a")
    stream_b = WorkstreamSpec(id="b")
    task_a = _task("task_a", workstream_id="a")
    task_b = _task("task_b", workstream_id="b")
    graph = TaskGraph.from_tasks(
        (task_a, task_b),
        workstreams=(stream_a, stream_b),
    )

    prepare_count = 0

    @dataclass
    class FailFirstPrepareRunner:
        def prepare(self, workstream_runtime: WorkstreamRuntime) -> None:
            nonlocal prepare_count
            prepare_count += 1
            if workstream_runtime.spec.id == "a":
                workstream_runtime.state.status = WorkstreamStatus.FAILED
                workstream_runtime.state.error = "prepare failed"
                raise RuntimeError("prepare failed")
            workstream_runtime.state.status = WorkstreamStatus.ACTIVE

        def merge(self, workstream_runtime: WorkstreamRuntime) -> WorkstreamRunResult:
            workstream_runtime.state.status = WorkstreamStatus.MERGED
            return WorkstreamRunResult.from_runtime(workstream_runtime)

        def teardown(self, workstream_runtime: WorkstreamRuntime) -> None:
            pass

    runner = ScriptedTaskRunner()
    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=runner,
            workstream_runner=FailFirstPrepareRunner(),
            config=OrchestratorConfig(
                max_concurrency=2, fail_fast_on_workstream_error=True
            ),
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.COMPLETED_WITH_FAILURES
    assert prepare_count == 1
    assert result.workstream_runtimes["a"].state.status == WorkstreamStatus.FAILED
    assert result.workstream_runtimes["b"].state.status != WorkstreamStatus.ACTIVE


def test_fail_fast_on_workstream_error_false_allows_new_workstreams() -> None:
    stream_a = WorkstreamSpec(id="a")
    stream_b = WorkstreamSpec(id="b")
    task_a = _task("task_a", workstream_id="a")
    task_b = _task("task_b", workstream_id="b")
    graph = TaskGraph.from_tasks(
        (task_a, task_b),
        workstreams=(stream_a, stream_b),
    )

    prepare_calls: list[str] = []

    @dataclass
    class FailFirstPrepareRunner:
        def prepare(self, workstream_runtime: WorkstreamRuntime) -> None:
            prepare_calls.append(workstream_runtime.spec.id)
            if workstream_runtime.spec.id == "a":
                workstream_runtime.state.status = WorkstreamStatus.FAILED
                workstream_runtime.state.error = "prepare failed"
                raise RuntimeError("prepare failed")
            workstream_runtime.state.status = WorkstreamStatus.ACTIVE

        def merge(self, workstream_runtime: WorkstreamRuntime) -> WorkstreamRunResult:
            workstream_runtime.state.status = WorkstreamStatus.MERGED
            return WorkstreamRunResult.from_runtime(workstream_runtime)

        def teardown(self, workstream_runtime: WorkstreamRuntime) -> None:
            pass

    runner = ScriptedTaskRunner()
    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=runner,
            workstream_runner=FailFirstPrepareRunner(),
            config=OrchestratorConfig(
                max_concurrency=2, fail_fast_on_workstream_error=False
            ),
        ).run()
    )

    assert "a" in prepare_calls
    assert "b" in prepare_calls
    assert result.workstream_runtimes["a"].state.status == WorkstreamStatus.FAILED
    assert result.workstream_runtimes["b"].state.status == WorkstreamStatus.MERGED


def test_workstream_merge_failure_downgrades_outcome() -> None:
    """Outcome must not be SUCCEEDED when a workstream merge fails.

    Regression: _build_result() only checked task statuses, so a run where
    all tasks reached PR_MERGED but the workstream integration-to-main merge
    failed still reported SUCCEEDED.
    """

    @dataclass
    class FailingMergeRunner:
        def prepare(self, workstream_runtime: WorkstreamRuntime) -> None:
            workstream_runtime.state.status = WorkstreamStatus.ACTIVE

        def merge(self, workstream_runtime: WorkstreamRuntime) -> WorkstreamRunResult:
            workstream_runtime.state.status = WorkstreamStatus.FAILED
            workstream_runtime.state.error = "gh pr merge failed"
            return WorkstreamRunResult.from_runtime(workstream_runtime)

        def teardown(self, workstream_runtime: WorkstreamRuntime) -> None:
            pass

    task = _task("a")
    graph = TaskGraph.from_tasks((task,))
    runner = ScriptedTaskRunner()

    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=runner,
            workstream_runner=FailingMergeRunner(),
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.COMPLETED_WITH_FAILURES
    assert result.task_runtimes["a"].state.status == TaskStatus.PR_MERGED
    assert result.workstream_runtimes["default"].state.status == WorkstreamStatus.FAILED
    assert any(event.kind == "workstream_merge_failed" for event in result.events)
