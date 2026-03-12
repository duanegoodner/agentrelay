"""Tests for TaskRunner lifecycle behavior."""

import asyncio
from dataclasses import dataclass, field

import pytest

from agentrelay.agent import Agent, TmuxAddress, TmuxAgent
from agentrelay.errors import (
    ExpectedTaskFailureError,
    IntegrationBoundary,
    IntegrationFailureClass,
)
from agentrelay.task import AgentRole, Task
from agentrelay.task_runner import (
    TaskCompletionChecker,
    TaskCompletionSignal,
    TaskKickoff,
    TaskLauncher,
    TaskMerger,
    TaskPreparer,
    TaskRunner,
    TaskRunnerIO,
    TaskTeardown,
    TearDownMode,
)
from agentrelay.task_runtime import TaskRuntime, TaskStatus


def _make_runtime(
    task_id: str = "task_1", status: TaskStatus = TaskStatus.PENDING
) -> TaskRuntime:
    runtime = TaskRuntime(task=Task(id=task_id, role=AgentRole.GENERIC))
    runtime.state.status = status
    return runtime


@dataclass
class FakeIO:
    """Simple I/O double implementing all six per-step protocols."""

    signal: TaskCompletionSignal = field(
        default_factory=lambda: TaskCompletionSignal(
            outcome="done",
            pr_url="https://github.com/org/repo/pull/1",
        )
    )
    fail_stage: str | None = None
    calls: list[str] = field(default_factory=list)
    agent: Agent = field(
        default_factory=lambda: TmuxAgent(
            _address=TmuxAddress(session="agentrelay", pane_id="%1")
        )
    )

    def _maybe_fail(self, stage: str) -> None:
        if self.fail_stage == stage:
            raise RuntimeError(f"{stage} boom")

    def prepare(self, runtime: TaskRuntime) -> None:
        self.calls.append("prepare")
        self._maybe_fail("prepare")

    def launch(self, runtime: TaskRuntime) -> Agent:
        self.calls.append("launch")
        self._maybe_fail("launch")
        return self.agent

    def kickoff(self, runtime: TaskRuntime, agent: Agent) -> None:
        self.calls.append("kickoff")
        self._maybe_fail("kickoff")

    async def wait_for_completion(self, runtime: TaskRuntime) -> TaskCompletionSignal:
        self.calls.append("wait_for_completion")
        self._maybe_fail("wait_for_completion")
        return self.signal

    def merge_pr(self, runtime: TaskRuntime, pr_url: str) -> None:
        self.calls.append("merge_pr")
        self._maybe_fail("merge_pr")

    def teardown(self, runtime: TaskRuntime) -> None:
        self.calls.append("teardown")
        self._maybe_fail("teardown")


def _make_io(fake: FakeIO | None = None) -> TaskRunnerIO:
    """Compose a FakeIO into a TaskRunnerIO dataclass."""
    if fake is None:
        fake = FakeIO()
    return TaskRunnerIO(
        preparer=fake,
        launcher=fake,
        kickoff_sender=fake,
        completion_checker=fake,
        merger=fake,
        teardown_handler=fake,
    )


def test_run_success_path() -> None:
    fake = FakeIO()
    io = _make_io(fake)
    runtime = _make_runtime()

    result = asyncio.run(TaskRunner(io=io).run(runtime))

    assert fake.calls == [
        "prepare",
        "launch",
        "kickoff",
        "wait_for_completion",
        "merge_pr",
        "teardown",
    ]
    assert runtime.state.status == TaskStatus.PR_MERGED
    assert runtime.state.error is None
    assert runtime.artifacts.pr_url == "https://github.com/org/repo/pull/1"
    assert runtime.artifacts.agent_address == fake.agent.address

    assert result.task_id == runtime.task.id
    assert result.status == TaskStatus.PR_MERGED
    assert result.pr_url == runtime.artifacts.pr_url
    assert result.error is None


def test_run_failed_signal_marks_runtime_failed() -> None:
    fake = FakeIO(signal=TaskCompletionSignal(outcome="failed", error="agent failed"))
    io = _make_io(fake)
    runtime = _make_runtime()

    result = asyncio.run(TaskRunner(io=io).run(runtime))

    assert fake.calls == [
        "prepare",
        "launch",
        "kickoff",
        "wait_for_completion",
        "teardown",
    ]
    assert runtime.state.status == TaskStatus.FAILED
    assert runtime.state.error == "agent failed"
    assert runtime.artifacts.pr_url is None
    assert result.status == TaskStatus.FAILED
    assert result.error == "agent failed"


def test_run_failed_signal_without_error_sets_default_message() -> None:
    fake = FakeIO(signal=TaskCompletionSignal(outcome="failed"))
    runtime = _make_runtime()

    asyncio.run(TaskRunner(io=_make_io(fake)).run(runtime))

    assert runtime.state.status == TaskStatus.FAILED
    assert runtime.state.error == "Task failed without an error message."


def test_run_done_signal_without_pr_url_fails() -> None:
    fake = FakeIO(signal=TaskCompletionSignal(outcome="done", pr_url=None))
    io = _make_io(fake)
    runtime = _make_runtime()

    result = asyncio.run(TaskRunner(io=io).run(runtime))

    assert fake.calls == [
        "prepare",
        "launch",
        "kickoff",
        "wait_for_completion",
        "teardown",
    ]
    assert runtime.state.status == TaskStatus.FAILED
    assert "did not include pr_url" in (runtime.state.error or "")
    assert result.status == TaskStatus.FAILED


@pytest.mark.parametrize(
    "fail_stage",
    ["prepare", "launch", "kickoff", "wait_for_completion", "merge_pr"],
)
def test_run_io_exception_marks_failed_and_still_tears_down(fail_stage: str) -> None:
    fake = FakeIO(fail_stage=fail_stage)
    io = _make_io(fake)
    runtime = _make_runtime()

    result = asyncio.run(TaskRunner(io=io).run(runtime))

    assert fake.calls[-1] == "teardown"
    assert runtime.state.status == TaskStatus.FAILED
    assert f"{fail_stage} boom" in (runtime.state.error or "")
    assert result.status == TaskStatus.FAILED
    assert result.failure_class == IntegrationFailureClass.INTERNAL_ERROR


def test_run_requires_pending_entry_status() -> None:
    fake = FakeIO()
    io = _make_io(fake)
    runtime = _make_runtime(status=TaskStatus.RUNNING)

    with pytest.raises(ValueError, match="requires runtime.state.status == PENDING"):
        asyncio.run(TaskRunner(io=io).run(runtime))

    assert fake.calls == []


def test_teardown_failure_is_recorded_without_overwriting_success() -> None:
    fake = FakeIO(fail_stage="teardown")
    io = _make_io(fake)
    runtime = _make_runtime()

    result = asyncio.run(TaskRunner(io=io).run(runtime))

    assert runtime.state.status == TaskStatus.PR_MERGED
    assert result.status == TaskStatus.PR_MERGED
    assert runtime.artifacts.concerns
    assert runtime.artifacts.concerns[-1].startswith("teardown_failed:")


def test_internal_logic_error_propagates() -> None:
    fake = FakeIO()
    io = _make_io(fake)
    runtime = _make_runtime()
    runner = TaskRunner(io=io)

    def _transition_with_bug(runtime_obj: TaskRuntime, target: TaskStatus) -> None:
        if target == TaskStatus.PR_CREATED:
            raise RuntimeError("internal transition bug")
        TaskRunner._transition(runner, runtime_obj, target)

    runner._transition = _transition_with_bug  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="internal transition bug"):
        asyncio.run(runner.run(runtime))

    # Teardown still runs from finally even when internal logic errors propagate.
    assert fake.calls[-1] == "teardown"


def test_teardown_mode_never_skips_teardown_on_success() -> None:
    fake = FakeIO()
    io = _make_io(fake)
    runtime = _make_runtime()

    result = asyncio.run(
        TaskRunner(io=io).run(runtime, teardown_mode=TearDownMode.NEVER)
    )

    assert result.status == TaskStatus.PR_MERGED
    assert "teardown" not in fake.calls


def test_teardown_mode_on_success_tears_down_after_success() -> None:
    fake = FakeIO()
    io = _make_io(fake)
    runtime = _make_runtime()

    result = asyncio.run(
        TaskRunner(io=io).run(runtime, teardown_mode=TearDownMode.ON_SUCCESS)
    )

    assert result.status == TaskStatus.PR_MERGED
    assert fake.calls[-1] == "teardown"


def test_teardown_mode_on_success_skips_teardown_after_failure() -> None:
    fake = FakeIO(signal=TaskCompletionSignal(outcome="failed", error="agent failed"))
    runtime = _make_runtime()

    result = asyncio.run(
        TaskRunner(io=_make_io(fake)).run(
            runtime, teardown_mode=TearDownMode.ON_SUCCESS
        )
    )

    assert result.status == TaskStatus.FAILED
    assert "teardown" not in fake.calls


def test_completion_signal_concerns_default_empty() -> None:
    signal = TaskCompletionSignal(outcome="done", pr_url="https://example/pr/1")
    assert signal.concerns == ()


def test_completion_signal_concerns_preserved() -> None:
    signal = TaskCompletionSignal(
        outcome="done",
        pr_url="https://example/pr/1",
        concerns=("style issue", "missing test"),
    )
    assert signal.concerns == ("style issue", "missing test")


def test_protocol_runtime_checkable_instances() -> None:
    fake = FakeIO()
    assert isinstance(fake, TaskPreparer)
    assert isinstance(fake, TaskLauncher)
    assert isinstance(fake, TaskKickoff)
    assert isinstance(fake, TaskCompletionChecker)
    assert isinstance(fake, TaskMerger)
    assert isinstance(fake, TaskTeardown)


def test_success_result_has_no_failure_class() -> None:
    result = asyncio.run(TaskRunner(io=_make_io()).run(_make_runtime()))

    assert result.status == TaskStatus.PR_MERGED
    assert result.failure_class is None


def test_agent_signaled_failure_has_no_failure_class() -> None:
    fake = FakeIO(signal=TaskCompletionSignal(outcome="failed", error="agent failed"))
    result = asyncio.run(TaskRunner(io=_make_io(fake)).run(_make_runtime()))

    assert result.status == TaskStatus.FAILED
    assert result.failure_class is None


def test_expected_task_failure_error_classified_as_expected() -> None:
    @dataclass
    class FailingPreparer:
        def prepare(self, runtime: TaskRuntime) -> None:
            raise ExpectedTaskFailureError(
                "gate check failed", boundary=IntegrationBoundary.SIGNAL
            )

    fake = FakeIO()
    io = TaskRunnerIO(
        preparer=FailingPreparer(),
        launcher=fake,
        kickoff_sender=fake,
        completion_checker=fake,
        merger=fake,
        teardown_handler=fake,
    )
    result = asyncio.run(TaskRunner(io=io).run(_make_runtime()))

    assert result.status == TaskStatus.FAILED
    assert result.failure_class == IntegrationFailureClass.EXPECTED_TASK_FAILURE
