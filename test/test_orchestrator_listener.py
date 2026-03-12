"""Tests for OrchestratorListener real-time event callback."""

import asyncio
from dataclasses import dataclass, field

from agentrelay.orchestrator import (
    Orchestrator,
    OrchestratorConfig,
    OrchestratorEvent,
    OrchestratorListener,
    OrchestratorOutcome,
)
from agentrelay.task import AgentRole, Task
from agentrelay.task_graph import TaskGraph
from agentrelay.task_runner import TaskRunResult, TearDownMode
from agentrelay.task_runtime import TaskRuntime, TaskStatus


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
        runtime.state.status = TaskStatus.PR_MERGED
        return TaskRunResult.from_runtime(runtime)


@dataclass
class FailRunner:
    """Task runner that always fails."""

    async def run(
        self,
        runtime: TaskRuntime,
        *,
        teardown_mode: TearDownMode = TearDownMode.ALWAYS,
    ) -> TaskRunResult:
        runtime.state.status = TaskStatus.FAILED
        runtime.state.error = f"{runtime.task.id} failed"
        return TaskRunResult.from_runtime(runtime)


def test_listener_receives_events_in_order() -> None:
    graph = TaskGraph.from_tasks((_task("a"),))
    listener = RecordingListener()

    result = asyncio.run(
        Orchestrator(
            graph=graph,
            task_runner=SuccessRunner(),
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
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.SUCCEEDED
    assert len(result.events) == 2  # task_started + task_finished
    assert result.events[0].kind == "task_started"
    assert result.events[1].kind == "task_finished"


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
            config=OrchestratorConfig(max_task_attempts=1),
            listener=listener,
        ).run()
    )

    assert result.outcome == OrchestratorOutcome.COMPLETED_WITH_FAILURES
    blocked_events = [e for e in listener.events if e.kind == "task_blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0].task_id == "b"
