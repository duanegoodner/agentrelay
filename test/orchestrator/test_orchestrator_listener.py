"""Tests for OrchestratorListener real-time event callback."""

import asyncio
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from agentrelay.orchestrator import (
    Orchestrator,
    OrchestratorConfig,
    OrchestratorEvent,
    OrchestratorListener,
    OrchestratorOutcome,
    TaskOutcomeClass,
)
from agentrelay.task import AgentRole, Task
from agentrelay.task_graph import TaskGraph
from agentrelay.task_runner import TaskRunResult, TearDownMode
from agentrelay.task_runtime import TaskRuntime
from agentrelay.workstream import (
    WorkstreamRunResult,
    WorkstreamRuntime,
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
class RecordingListener:
    """Listener that records all received events."""

    events: list[OrchestratorEvent] = field(default_factory=list)

    def on_event(self, event: OrchestratorEvent) -> None:
        self.events.append(event)


@dataclass
class SuccessRunner:
    """Task runner that always succeeds."""

    async def run(
        self,
        runtime: TaskRuntime,
        *,
        teardown_mode: TearDownMode = TearDownMode.ALWAYS,
    ) -> TaskRunResult:
        runtime.artifacts.pr_url = f"https://example.com/{runtime.task.id}"
        if runtime.state.signal_dir is None:
            runtime.state.signal_dir = Path(tempfile.mkdtemp())
        runtime.mark_pr_merged()
        return TaskRunResult.from_runtime(runtime)


@dataclass
class NoOpWorkstreamRunner:
    """WorkstreamRunner double that performs state transitions without I/O."""

    def prepare(self, workstream_runtime: WorkstreamRuntime) -> None:
        workstream_runtime.state.signal_dir = Path(tempfile.mkdtemp())
        workstream_runtime.mark_pending()
        workstream_runtime.mark_active()

    def integrate(self, workstream_runtime: WorkstreamRuntime) -> WorkstreamRunResult:
        workstream_runtime.mark_pr_created(
            f"https://example.com/{workstream_runtime.spec.id}/integration-pr"
        )
        return WorkstreamRunResult.from_runtime(workstream_runtime)

    def teardown(self, workstream_runtime: WorkstreamRuntime) -> None:
        pass


@dataclass
class FailRunner:
    """Task runner that always fails."""

    async def run(
        self,
        runtime: TaskRuntime,
        *,
        teardown_mode: TearDownMode = TearDownMode.ALWAYS,
    ) -> TaskRunResult:
        runtime.mark_failed(f"{runtime.task.id} failed")
        return TaskRunResult.from_runtime(runtime)


def test_listener_receives_events_in_order() -> None:
    graph = TaskGraph.from_tasks((_task("a"),))
    listener = RecordingListener()

    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=SuccessRunner(),
            workstream_runner=NoOpWorkstreamRunner(),
            listener=listener,
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.SUCCEEDED
    assert len(listener.events) == len(result.events)
    for received, recorded in zip(listener.events, result.events):
        assert received is recorded


def test_no_listener_default_behavior_unchanged() -> None:
    graph = TaskGraph.from_tasks((_task("a"),))

    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=SuccessRunner(),
            workstream_runner=NoOpWorkstreamRunner(),
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.SUCCEEDED
    kinds = [e.kind for e in result.events]
    assert kinds == [
        "workstream_prepared",
        "task_started",
        "task_finished",
        "workstream_pr_created",
    ]


def test_listener_protocol_runtime_checkable() -> None:
    listener = RecordingListener()
    assert isinstance(listener, OrchestratorListener)


def test_listener_called_for_blocked_events() -> None:
    task_a = _task("a")
    task_b = _task("b", dependencies=("a",))
    graph = TaskGraph.from_tasks((task_a, task_b))
    listener = RecordingListener()

    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=FailRunner(),
            workstream_runner=NoOpWorkstreamRunner(),
            config=OrchestratorConfig(max_task_attempts=1),
            listener=listener,
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.COMPLETED_WITH_FAILURES
    blocked_events = [e for e in listener.events if e.kind == "task_blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0].task_id == "b"


def test_all_events_have_timestamps() -> None:
    graph = TaskGraph.from_tasks((_task("a"),))
    listener = RecordingListener()

    asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=SuccessRunner(),
            workstream_runner=NoOpWorkstreamRunner(),
            listener=listener,
        ).run()
    )

    assert len(listener.events) > 0
    for event in listener.events:
        assert event.timestamp > 0


def test_workstream_prepared_event_emitted() -> None:
    graph = TaskGraph.from_tasks((_task("a"),))
    listener = RecordingListener()

    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=SuccessRunner(),
            workstream_runner=NoOpWorkstreamRunner(),
            listener=listener,
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.SUCCEEDED
    prepared = [e for e in listener.events if e.kind == "workstream_prepared"]
    assert len(prepared) == 1
    assert prepared[0].workstream_id == "default"


def test_task_finished_success_carries_pr_url() -> None:
    graph = TaskGraph.from_tasks((_task("a"),))
    listener = RecordingListener()

    asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=SuccessRunner(),
            workstream_runner=NoOpWorkstreamRunner(),
            listener=listener,
        ).run()
    )

    finished = [e for e in listener.events if e.kind == "task_finished"]
    assert len(finished) == 1
    assert finished[0].outcome_class == TaskOutcomeClass.SUCCESS
    assert finished[0].message == "https://example.com/a"
