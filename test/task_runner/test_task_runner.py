"""Tests for StandardTaskRunner lifecycle behavior."""

import asyncio
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from agentrelay.agent import Agent, TmuxAddress, TmuxAgent
from agentrelay.errors import (
    ExpectedTaskFailureError,
    IntegrationBoundary,
    IntegrationFailureClass,
)
from agentrelay.task import AgentRole, Task
from agentrelay.task_runner import (
    GateCheckResult,
    StandardTaskRunner,
    StepDispatch,
    TaskCompletionChecker,
    TaskCompletionSignal,
    TaskGateChecker,
    TaskKickoff,
    TaskLauncher,
    TaskLogCapture,
    TaskMerger,
    TaskPreparer,
    TaskTeardown,
    TearDownMode,
)
from agentrelay.task_runtime import TaskRuntime, TaskStatus


def _make_runtime(
    task_id: str = "task_1", status: TaskStatus = TaskStatus.PENDING
) -> TaskRuntime:
    runtime = TaskRuntime(task=Task(id=task_id, role=AgentRole.GENERIC))
    runtime.state.signal_dir = Path(tempfile.mkdtemp())
    if status == TaskStatus.PENDING:
        runtime.mark_pending()
    elif status == TaskStatus.RUNNING:
        runtime.mark_running()
    elif status == TaskStatus.PR_CREATED:
        runtime.mark_pr_created()
    elif status == TaskStatus.PR_MERGED:
        runtime.mark_pr_merged()
    elif status == TaskStatus.COMPLETED:
        runtime.mark_completed()
    elif status == TaskStatus.FAILED:
        runtime.mark_failed("test failure")
    return runtime


@dataclass
class FakeIO:
    """Simple I/O double implementing all per-step protocols (including gate)."""

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
    gate_results: list[GateCheckResult] = field(default_factory=list)
    _gate_call_count: int = field(default=0, repr=False)

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

    def check_gate(self, runtime: TaskRuntime) -> GateCheckResult:
        self.calls.append("check_gate")
        self._maybe_fail("check_gate")
        if self.gate_results:
            idx = min(self._gate_call_count, len(self.gate_results) - 1)
            self._gate_call_count += 1
            return self.gate_results[idx]
        return GateCheckResult(passed=True, output="")

    def merge_pr(self, runtime: TaskRuntime, pr_url: str) -> None:
        self.calls.append("merge_pr")
        self._maybe_fail("merge_pr")

    def capture_log(self, runtime: TaskRuntime) -> None:
        self.calls.append("capture_log")
        self._maybe_fail("capture_log")

    def teardown(self, runtime: TaskRuntime) -> None:
        self.calls.append("teardown")
        self._maybe_fail("teardown")


def _make_runner(fake: FakeIO | None = None) -> StandardTaskRunner:
    """Build a StandardTaskRunner wired to a single FakeIO via StepDispatch."""
    if fake is None:
        fake = FakeIO()
    d: StepDispatch[Any] = StepDispatch(default=lambda rt: fake)
    return StandardTaskRunner(
        _preparer=d,
        _launcher=d,
        _kickoff=d,
        _completion_checker=d,
        _gate_checker=fake,
        _merger=d,
        _log_capture=d,
        _teardown=d,
    )


def test_run_success_path() -> None:
    fake = FakeIO()
    runner = _make_runner(fake)
    runtime = _make_runtime()

    result = asyncio.run(runner.run(runtime))

    assert fake.calls == [
        "prepare",
        "launch",
        "kickoff",
        "wait_for_completion",
        "merge_pr",
        "capture_log",
        "teardown",
    ]
    assert runtime.status == TaskStatus.PR_MERGED
    assert runtime.state.error is None
    assert runtime.artifacts.pr_url == "https://github.com/org/repo/pull/1"
    assert runtime.artifacts.agent_address == fake.agent.address

    assert result.task_id == runtime.task.id
    assert result.status == TaskStatus.PR_MERGED
    assert result.pr_url == runtime.artifacts.pr_url
    assert result.error is None


def test_run_failed_signal_marks_runtime_failed() -> None:
    fake = FakeIO(signal=TaskCompletionSignal(outcome="failed", error="agent failed"))
    runner = _make_runner(fake)
    runtime = _make_runtime()

    result = asyncio.run(runner.run(runtime))

    assert fake.calls == [
        "prepare",
        "launch",
        "kickoff",
        "wait_for_completion",
        "capture_log",
        "teardown",
    ]
    assert runtime.status == TaskStatus.FAILED
    assert runtime.state.error == "agent failed"
    assert runtime.artifacts.pr_url is None
    assert result.status == TaskStatus.FAILED
    assert result.error == "agent failed"


def test_run_failed_signal_without_error_sets_default_message() -> None:
    fake = FakeIO(signal=TaskCompletionSignal(outcome="failed"))
    runtime = _make_runtime()

    asyncio.run(_make_runner(fake).run(runtime))

    assert runtime.status == TaskStatus.FAILED
    assert runtime.state.error == "Task failed without an error message."


def test_run_done_signal_without_pr_url_succeeds_without_merge() -> None:
    fake = FakeIO(signal=TaskCompletionSignal(outcome="done", pr_url=None))
    runner = _make_runner(fake)
    runtime = _make_runtime()

    result = asyncio.run(runner.run(runtime))

    assert fake.calls == [
        "prepare",
        "launch",
        "kickoff",
        "wait_for_completion",
        "capture_log",
        "teardown",
    ]
    assert "merge_pr" not in fake.calls
    assert runtime.status == TaskStatus.COMPLETED
    assert runtime.artifacts.pr_url is None
    assert result.status == TaskStatus.COMPLETED


@pytest.mark.parametrize(
    "fail_stage",
    ["prepare", "launch", "kickoff", "wait_for_completion", "merge_pr"],
)
def test_run_io_exception_marks_failed_and_still_tears_down(fail_stage: str) -> None:
    fake = FakeIO(fail_stage=fail_stage)
    runner = _make_runner(fake)
    runtime = _make_runtime()

    result = asyncio.run(runner.run(runtime))

    assert "capture_log" in fake.calls
    assert fake.calls[-1] == "teardown"
    assert runtime.status == TaskStatus.FAILED
    assert f"{fail_stage} boom" in (runtime.state.error or "")
    assert result.status == TaskStatus.FAILED
    assert result.failure_class == IntegrationFailureClass.INTERNAL_ERROR


def test_run_requires_pending_entry_status() -> None:
    fake = FakeIO()
    runner = _make_runner(fake)
    runtime = _make_runtime(status=TaskStatus.RUNNING)

    with pytest.raises(ValueError, match="requires runtime.status == PENDING"):
        asyncio.run(runner.run(runtime))

    assert fake.calls == []


def test_teardown_failure_is_recorded_without_overwriting_success() -> None:
    fake = FakeIO(fail_stage="teardown")
    runner = _make_runner(fake)
    runtime = _make_runtime()

    result = asyncio.run(runner.run(runtime))

    assert runtime.status == TaskStatus.PR_MERGED
    assert result.status == TaskStatus.PR_MERGED
    assert runtime.artifacts.concerns
    assert runtime.artifacts.concerns[-1].startswith("teardown_failed:")


def test_internal_logic_error_propagates() -> None:
    fake = FakeIO()
    runner = _make_runner(fake)
    runtime = _make_runtime()

    def _transition_with_bug(runtime_obj: TaskRuntime, target: TaskStatus) -> None:
        if target == TaskStatus.PR_CREATED:
            raise RuntimeError("internal transition bug")
        StandardTaskRunner._transition(runner, runtime_obj, target)

    runner._transition = _transition_with_bug  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="internal transition bug"):
        asyncio.run(runner.run(runtime))

    # Log capture and teardown still run from finally even when internal logic errors propagate.
    assert "capture_log" in fake.calls
    assert fake.calls[-1] == "teardown"


def test_teardown_mode_never_skips_teardown_on_success() -> None:
    fake = FakeIO()
    runner = _make_runner(fake)
    runtime = _make_runtime()

    result = asyncio.run(runner.run(runtime, teardown_mode=TearDownMode.NEVER))

    assert result.status == TaskStatus.PR_MERGED
    assert "capture_log" in fake.calls
    assert "teardown" not in fake.calls


def test_teardown_mode_on_success_tears_down_after_success() -> None:
    fake = FakeIO()
    runner = _make_runner(fake)
    runtime = _make_runtime()

    result = asyncio.run(runner.run(runtime, teardown_mode=TearDownMode.ON_SUCCESS))

    assert result.status == TaskStatus.PR_MERGED
    assert fake.calls[-1] == "teardown"


def test_teardown_mode_on_success_skips_teardown_after_failure() -> None:
    fake = FakeIO(signal=TaskCompletionSignal(outcome="failed", error="agent failed"))
    runtime = _make_runtime()

    result = asyncio.run(
        _make_runner(fake).run(runtime, teardown_mode=TearDownMode.ON_SUCCESS)
    )

    assert result.status == TaskStatus.FAILED
    assert "capture_log" in fake.calls
    assert "teardown" not in fake.calls


def test_teardown_mode_on_success_tears_down_after_completed() -> None:
    """ON_SUCCESS teardown fires for COMPLETED (PR-less success) too."""
    fake = FakeIO(signal=TaskCompletionSignal(outcome="done", pr_url=None))
    runtime = _make_runtime()

    result = asyncio.run(
        _make_runner(fake).run(runtime, teardown_mode=TearDownMode.ON_SUCCESS)
    )

    assert result.status == TaskStatus.COMPLETED
    assert "teardown" in fake.calls


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
    assert isinstance(fake, TaskGateChecker)
    assert isinstance(fake, TaskLogCapture)
    assert isinstance(fake, TaskMerger)
    assert isinstance(fake, TaskTeardown)


def test_success_result_has_no_failure_class() -> None:
    result = asyncio.run(_make_runner().run(_make_runtime()))

    assert result.status == TaskStatus.PR_MERGED
    assert result.failure_class is None


def test_agent_signaled_failure_has_no_failure_class() -> None:
    fake = FakeIO(signal=TaskCompletionSignal(outcome="failed", error="agent failed"))
    result = asyncio.run(_make_runner(fake).run(_make_runtime()))

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
    failing_preparer = FailingPreparer()
    d_fake: StepDispatch[Any] = StepDispatch(default=lambda rt: fake)
    runner = StandardTaskRunner(
        _preparer=StepDispatch(default=lambda rt: failing_preparer),
        _launcher=d_fake,
        _kickoff=d_fake,
        _completion_checker=d_fake,
        _gate_checker=fake,
        _merger=d_fake,
        _log_capture=d_fake,
        _teardown=d_fake,
    )
    result = asyncio.run(runner.run(_make_runtime()))

    assert result.status == TaskStatus.FAILED
    assert result.failure_class == IntegrationFailureClass.EXPECTED_TASK_FAILURE


def test_concerns_transferred_to_runtime_on_success() -> None:
    fake = FakeIO(
        signal=TaskCompletionSignal(
            outcome="done",
            pr_url="https://github.com/org/repo/pull/1",
            concerns=("naming could be clearer", "consider edge case X"),
        )
    )
    runner = _make_runner(fake)
    runtime = _make_runtime()

    asyncio.run(runner.run(runtime))

    assert runtime.status == TaskStatus.PR_MERGED
    assert runtime.artifacts.concerns == [
        "naming could be clearer",
        "consider edge case X",
    ]


def test_concerns_transferred_to_runtime_on_failure() -> None:
    fake = FakeIO(
        signal=TaskCompletionSignal(
            outcome="failed",
            error="could not complete task",
            concerns=("partial progress made",),
        )
    )
    runner = _make_runner(fake)
    runtime = _make_runtime()

    asyncio.run(runner.run(runtime))

    assert runtime.status == TaskStatus.FAILED
    assert runtime.artifacts.concerns == ["partial progress made"]


def test_ops_concerns_transferred_to_runtime_on_success() -> None:
    fake = FakeIO(
        signal=TaskCompletionSignal(
            outcome="done",
            pr_url="https://github.com/org/repo/pull/1",
            ops_concerns=("slow build", "missing dep"),
        )
    )
    runner = _make_runner(fake)
    runtime = _make_runtime()

    asyncio.run(runner.run(runtime))

    assert runtime.status == TaskStatus.PR_MERGED
    assert runtime.artifacts.ops_concerns == ["slow build", "missing dep"]


def test_ops_concerns_transferred_to_runtime_on_failure() -> None:
    fake = FakeIO(
        signal=TaskCompletionSignal(
            outcome="failed",
            error="could not complete task",
            ops_concerns=("pixi not found",),
        )
    )
    runner = _make_runner(fake)
    runtime = _make_runtime()

    asyncio.run(runner.run(runtime))

    assert runtime.status == TaskStatus.FAILED
    assert runtime.artifacts.ops_concerns == ["pixi not found"]


@patch("agentrelay.task_runner.core.runner.gh")
def test_run_saves_pr_summary_before_merge(mock_gh: Any) -> None:
    mock_gh.pr_body.return_value = "## Summary\n\n- implemented feature"
    fake = FakeIO()
    runner = _make_runner(fake)
    runtime = _make_runtime()

    result = asyncio.run(runner.run(runtime))

    assert result.status == TaskStatus.PR_MERGED
    mock_gh.pr_body.assert_called_once_with("https://github.com/org/repo/pull/1")
    assert runtime.state.signal_dir is not None
    summary_path = runtime.state.signal_dir / "summary.md"
    assert summary_path.is_file()
    assert summary_path.read_text() == "## Summary\n\n- implemented feature"
    # Verify summary saved before merge (merge_pr comes after summary in calls).
    merge_idx = fake.calls.index("merge_pr")
    assert merge_idx > 0  # merge_pr happened, not first


@patch("agentrelay.task_runner.core.runner.gh")
def test_run_pr_summary_fetch_failure_does_not_block_merge(mock_gh: Any) -> None:
    mock_gh.pr_body.side_effect = RuntimeError("gh failed")
    fake = FakeIO()
    runner = _make_runner(fake)
    runtime = _make_runtime()

    result = asyncio.run(runner.run(runtime))

    assert result.status == TaskStatus.PR_MERGED
    assert "merge_pr" in fake.calls
    assert runtime.state.signal_dir is not None
    summary_path = runtime.state.signal_dir / "summary.md"
    assert not summary_path.exists()


@patch("agentrelay.task_runner.core.runner.gh")
def test_run_pr_less_completion_skips_summary(mock_gh: Any) -> None:
    fake = FakeIO(signal=TaskCompletionSignal(outcome="done", pr_url=None))
    runner = _make_runner(fake)
    runtime = _make_runtime()

    result = asyncio.run(runner.run(runtime))

    assert result.status == TaskStatus.COMPLETED
    mock_gh.pr_body.assert_not_called()


# ---------------------------------------------------------------------------
# Completion gate tests
# ---------------------------------------------------------------------------


def _make_gated_runtime(
    completion_gate: str = "test cmd",
    max_gate_attempts: int | None = None,
) -> TaskRuntime:
    """Build a PENDING runtime whose task declares a completion gate."""
    runtime = TaskRuntime(
        task=Task(
            id="gated_task",
            role=AgentRole.GENERIC,
            completion_gate=completion_gate,
            max_gate_attempts=max_gate_attempts,
        )
    )
    runtime.state.signal_dir = Path(tempfile.mkdtemp())
    runtime.mark_pending()
    return runtime


def test_gate_passes_proceeds_to_merge() -> None:
    fake = FakeIO(gate_results=[GateCheckResult(passed=True, output="ok")])
    runner = _make_runner(fake)
    runtime = _make_gated_runtime()

    result = asyncio.run(runner.run(runtime))

    assert result.status == TaskStatus.PR_MERGED
    assert "check_gate" in fake.calls
    assert "merge_pr" in fake.calls
    # Gate runs after wait, before merge.
    gate_idx = fake.calls.index("check_gate")
    merge_idx = fake.calls.index("merge_pr")
    assert gate_idx < merge_idx


def test_gate_fails_all_attempts_marks_failed() -> None:
    fake = FakeIO(
        gate_results=[GateCheckResult(passed=False, output="FAIL")],
    )
    runner = _make_runner(fake)
    runtime = _make_gated_runtime(max_gate_attempts=3)

    result = asyncio.run(runner.run(runtime))

    assert result.status == TaskStatus.FAILED
    assert result.failure_class is None  # Expected failure, not internal.
    assert "Completion gate failed after 3 attempt(s)" in (runtime.state.error or "")
    assert fake.calls.count("check_gate") == 3
    assert "merge_pr" not in fake.calls


def test_gate_retries_then_passes() -> None:
    fake = FakeIO(
        gate_results=[
            GateCheckResult(passed=False, output="fail 1"),
            GateCheckResult(passed=False, output="fail 2"),
            GateCheckResult(passed=True, output="pass"),
        ],
    )
    runner = _make_runner(fake)
    runtime = _make_gated_runtime(max_gate_attempts=5)

    result = asyncio.run(runner.run(runtime))

    assert result.status == TaskStatus.PR_MERGED
    assert fake.calls.count("check_gate") == 3
    assert "merge_pr" in fake.calls


def test_no_gate_skips_check() -> None:
    """Task without completion_gate should not invoke check_gate."""
    fake = FakeIO()
    runner = _make_runner(fake)
    runtime = _make_runtime()  # No completion_gate on task.

    result = asyncio.run(runner.run(runtime))

    assert result.status == TaskStatus.PR_MERGED
    assert "check_gate" not in fake.calls


def test_gate_exception_records_io_failure() -> None:
    fake = FakeIO(fail_stage="check_gate")
    runner = _make_runner(fake)
    runtime = _make_gated_runtime()

    result = asyncio.run(runner.run(runtime))

    assert result.status == TaskStatus.FAILED
    assert result.failure_class == IntegrationFailureClass.INTERNAL_ERROR
    assert "check_gate boom" in (runtime.state.error or "")
    assert fake.calls[-1] == "teardown"


def test_gate_events_emitted() -> None:
    events: list[Any] = []
    fake = FakeIO(
        gate_results=[
            GateCheckResult(passed=False, output="fail"),
            GateCheckResult(passed=True, output="pass"),
        ],
    )
    runner = _make_runner(fake)
    runner.on_event = lambda e: events.append(e)
    runtime = _make_gated_runtime(max_gate_attempts=3)

    asyncio.run(runner.run(runtime))

    kinds = [e.kind for e in events]
    assert "task_gate_running" in kinds
    assert "task_gate_passed" in kinds
    # Two gate_running events (one per attempt).
    assert kinds.count("task_gate_running") == 2


def test_gate_failed_event_on_exhaustion() -> None:
    events: list[Any] = []
    fake = FakeIO(
        gate_results=[GateCheckResult(passed=False, output="nope")],
    )
    runner = _make_runner(fake)
    runner.on_event = lambda e: events.append(e)
    runtime = _make_gated_runtime(max_gate_attempts=1)

    asyncio.run(runner.run(runtime))

    kinds = [e.kind for e in events]
    assert "task_gate_failed" in kinds
    assert "task_gate_passed" not in kinds


def test_gate_skipped_for_pr_less_completion() -> None:
    """Even if task has a gate, PR-less completion skips the gate check."""
    fake = FakeIO(
        signal=TaskCompletionSignal(outcome="done", pr_url=None),
        gate_results=[GateCheckResult(passed=False, output="should not run")],
    )
    runner = _make_runner(fake)
    runtime = _make_gated_runtime()

    result = asyncio.run(runner.run(runtime))

    assert result.status == TaskStatus.COMPLETED
    assert "check_gate" not in fake.calls


def test_gate_default_max_attempts_used_when_task_omits() -> None:
    """When task.max_gate_attempts is None, runner uses default (5)."""
    fake = FakeIO(
        gate_results=[GateCheckResult(passed=False, output="fail")],
    )
    runner = _make_runner(fake)
    runtime = _make_gated_runtime(max_gate_attempts=None)

    asyncio.run(runner.run(runtime))

    # Default is 5 attempts.
    assert fake.calls.count("check_gate") == 5


# ---------------------------------------------------------------------------
# Log capture tests
# ---------------------------------------------------------------------------


def test_log_capture_runs_before_teardown() -> None:
    """capture_log always precedes teardown in call order."""
    fake = FakeIO()
    runner = _make_runner(fake)
    runtime = _make_runtime()

    asyncio.run(runner.run(runtime))

    capture_idx = fake.calls.index("capture_log")
    teardown_idx = fake.calls.index("teardown")
    assert capture_idx < teardown_idx


def test_log_capture_runs_when_teardown_skipped() -> None:
    """capture_log runs even when ON_SUCCESS teardown is skipped on failure."""
    fake = FakeIO(signal=TaskCompletionSignal(outcome="failed", error="boom"))
    runner = _make_runner(fake)
    runtime = _make_runtime()

    result = asyncio.run(runner.run(runtime, teardown_mode=TearDownMode.ON_SUCCESS))

    assert result.status == TaskStatus.FAILED
    assert "capture_log" in fake.calls
    assert "teardown" not in fake.calls


def test_log_capture_failure_does_not_block_teardown() -> None:
    """If capture_log raises, teardown still runs and concern is recorded."""
    fake = FakeIO(fail_stage="capture_log")
    runner = _make_runner(fake)
    runtime = _make_runtime()

    result = asyncio.run(runner.run(runtime))

    assert result.status == TaskStatus.PR_MERGED
    assert "teardown" in fake.calls
    assert any("log_capture_failed" in c for c in runtime.artifacts.concerns)
