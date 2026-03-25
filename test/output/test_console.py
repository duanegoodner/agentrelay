"""Tests for ConsoleListener real-time output and summary table."""

from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import Any

from agentrelay.orchestrator import (
    OrchestratorEvent,
    OrchestratorOutcome,
    OrchestratorResult,
    TaskOutcomeClass,
)
from agentrelay.output.console import ConsoleListener, print_summary
from agentrelay.task import AgentRole, Task
from agentrelay.task_runtime import TaskRuntime, TaskStatus
from agentrelay.workstream import WorkstreamRuntime, WorkstreamSpec


def _event(kind: str, **kwargs: Any) -> OrchestratorEvent:
    """Build an event with a fixed timestamp for deterministic output."""
    return OrchestratorEvent(kind=kind, timestamp=1742400000.0, **kwargs)


def _listener() -> tuple[ConsoleListener, io.StringIO]:
    buf = io.StringIO()
    return ConsoleListener(stream=buf), buf


# ---------------------------------------------------------------------------
# ConsoleListener real-time output
# ---------------------------------------------------------------------------


class TestConsoleListenerEvents:
    def test_workstream_prepared(self) -> None:
        listener, buf = _listener()
        listener.on_event(_event("workstream_prepared", workstream_id="ws_add"))
        assert "ws_add" in buf.getvalue()
        assert "prepared" in buf.getvalue()

    def test_workstream_prepare_failed(self) -> None:
        listener, buf = _listener()
        listener.on_event(
            _event(
                "workstream_prepare_failed",
                workstream_id="ws_add",
                message="git error",
            )
        )
        output = buf.getvalue()
        assert "ws_add" in output
        assert "prepare FAILED" in output
        assert "git error" in output

    def test_task_started(self) -> None:
        listener, buf = _listener()
        listener.on_event(
            _event(
                "task_started",
                task_id="add_fn",
                workstream_id="ws_add",
                attempt_num=0,
            )
        )
        output = buf.getvalue()
        assert "add_fn" in output
        assert "started" in output
        assert "ws_add" in output

    def test_task_started_retry(self) -> None:
        listener, buf = _listener()
        listener.on_event(
            _event(
                "task_started",
                task_id="add_fn",
                workstream_id="ws_add",
                attempt_num=1,
            )
        )
        assert "retry 1" in buf.getvalue()

    def test_task_finished_success(self) -> None:
        listener, buf = _listener()
        # Seed start time.
        listener.on_event(
            OrchestratorEvent(
                kind="task_started",
                timestamp=1742400000.0,
                task_id="add_fn",
                workstream_id="ws_add",
                attempt_num=0,
            )
        )
        buf.truncate(0)
        buf.seek(0)
        listener.on_event(
            OrchestratorEvent(
                kind="task_finished",
                timestamp=1742400065.0,
                task_id="add_fn",
                workstream_id="ws_add",
                attempt_num=0,
                outcome_class=TaskOutcomeClass.SUCCESS,
                message="https://github.com/org/repo/pull/1",
            )
        )
        output = buf.getvalue()
        assert "succeeded" in output
        assert "1m05s" in output
        assert "https://github.com/org/repo/pull/1" in output

    def test_task_finished_failure_retry(self) -> None:
        listener, buf = _listener()
        listener.on_event(
            _event(
                "task_finished",
                task_id="add_fn",
                workstream_id="ws_add",
                attempt_num=0,
                outcome_class=TaskOutcomeClass.EXPECTED_FAILURE,
                message="retry_scheduled",
            )
        )
        assert "retrying" in buf.getvalue()

    def test_task_finished_failure_terminal(self) -> None:
        listener, buf = _listener()
        listener.on_event(
            _event(
                "task_finished",
                task_id="add_fn",
                workstream_id="ws_add",
                attempt_num=0,
                outcome_class=TaskOutcomeClass.EXPECTED_FAILURE,
                message="max_attempts_reached",
            )
        )
        assert "no retries left" in buf.getvalue()

    def test_task_finished_internal_error(self) -> None:
        listener, buf = _listener()
        listener.on_event(
            _event(
                "task_finished",
                task_id="add_fn",
                workstream_id="ws_add",
                attempt_num=0,
                outcome_class=TaskOutcomeClass.INTERNAL_ERROR,
                message="RuntimeError: boom",
            )
        )
        output = buf.getvalue()
        assert "INTERNAL ERROR" in output
        assert "RuntimeError: boom" in output

    def test_task_blocked(self) -> None:
        listener, buf = _listener()
        listener.on_event(_event("task_blocked", task_id="add_fn"))
        assert "blocked" in buf.getvalue()

    def test_workstream_pr_created(self) -> None:
        listener, buf = _listener()
        listener.on_event(
            _event(
                "workstream_pr_created",
                workstream_id="ws_add",
                message="https://example.com/pr/1",
            )
        )
        output = buf.getvalue()
        assert "integration PR created" in output
        assert "https://example.com/pr/1" in output

    def test_workstream_integration_failed(self) -> None:
        listener, buf = _listener()
        listener.on_event(
            _event(
                "workstream_integration_failed",
                workstream_id="ws_add",
                message="conflict",
            )
        )
        output = buf.getvalue()
        assert "integration FAILED" in output
        assert "conflict" in output

    def test_unknown_event_is_silently_ignored(self) -> None:
        listener, buf = _listener()
        listener.on_event(_event("some_future_event"))
        assert buf.getvalue() == ""


# ---------------------------------------------------------------------------
# Verbose step events
# ---------------------------------------------------------------------------


def _verbose_listener() -> tuple[ConsoleListener, io.StringIO]:
    buf = io.StringIO()
    return ConsoleListener(stream=buf, verbose=True), buf


class TestVerboseStepEvents:
    def test_step_events_suppressed_in_default_mode(self) -> None:
        listener, buf = _listener()  # verbose=False
        for kind in (
            "task_prepared",
            "task_launched",
            "task_waiting",
            "task_gate_running",
            "task_gate_passed",
            "task_pr_merging",
        ):
            listener.on_event(_event(kind, task_id="t"))
        assert buf.getvalue() == ""

    def test_task_prepared(self) -> None:
        listener, buf = _verbose_listener()
        listener.on_event(
            _event(
                "task_prepared", task_id="add_fn", message="branch=agentrelay/g/add_fn"
            )
        )
        output = buf.getvalue()
        assert "add_fn" in output
        assert "prepared" in output
        assert "branch=" in output

    def test_task_launched(self) -> None:
        listener, buf = _verbose_listener()
        listener.on_event(
            _event("task_launched", task_id="add_fn", message="agentrelay:%3")
        )
        output = buf.getvalue()
        assert "agent launched" in output
        assert "agentrelay:%3" in output

    def test_task_waiting(self) -> None:
        listener, buf = _verbose_listener()
        listener.on_event(_event("task_waiting", task_id="add_fn"))
        assert "waiting for completion signal" in buf.getvalue()

    def test_task_gate_running(self) -> None:
        listener, buf = _verbose_listener()
        listener.on_event(
            _event(
                "task_gate_running",
                task_id="add_fn",
                message="attempt 1/3: pixi run test",
            )
        )
        output = buf.getvalue()
        assert "gate running" in output
        assert "attempt 1/3" in output

    def test_task_gate_passed(self) -> None:
        listener, buf = _verbose_listener()
        listener.on_event(_event("task_gate_passed", task_id="add_fn"))
        assert "gate passed" in buf.getvalue()

    def test_task_gate_failed_always_visible(self) -> None:
        """gate_failed is printed even with verbose=False."""
        listener, buf = _listener()  # non-verbose
        listener.on_event(
            _event(
                "task_gate_failed",
                task_id="add_fn",
                message="pixi run test",
            )
        )
        output = buf.getvalue()
        assert "gate FAILED" in output
        assert "pixi run test" in output

    def test_task_pr_merging(self) -> None:
        listener, buf = _verbose_listener()
        listener.on_event(
            _event(
                "task_pr_merging", task_id="add_fn", message="https://example.com/pr/1"
            )
        )
        assert "merging PR" in buf.getvalue()


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------


def _make_result(
    *,
    outcome: OrchestratorOutcome = OrchestratorOutcome.SUCCEEDED,
    tasks: tuple[tuple[str, TaskStatus, str], ...] = (),
    fatal_error: str | None = None,
) -> OrchestratorResult:
    """Build a minimal OrchestratorResult for table tests."""
    task_runtimes: dict[str, TaskRuntime] = {}
    events: list[OrchestratorEvent] = []
    for task_id, status, ws_id in tasks:
        task = Task(id=task_id, role=AgentRole.GENERIC, workstream_id=ws_id)
        runtime = TaskRuntime(task=task)
        if status == TaskStatus.FAILED:
            runtime.mark_failed(f"{task_id} failed")
        elif status != TaskStatus.PENDING:
            runtime.state.signal_dir = Path(tempfile.mkdtemp())
            _mark = {
                TaskStatus.RUNNING: runtime.mark_running,
                TaskStatus.PR_CREATED: runtime.mark_pr_created,
                TaskStatus.PR_MERGED: runtime.mark_pr_merged,
            }
            _mark[status]()
        if status == TaskStatus.PR_MERGED:
            runtime.artifacts.pr_url = f"https://example.com/{task_id}"
        task_runtimes[task_id] = runtime
        events.append(
            OrchestratorEvent(
                kind="task_started",
                timestamp=1742400000.0,
                task_id=task_id,
                workstream_id=ws_id,
            )
        )
        events.append(
            OrchestratorEvent(
                kind="task_finished",
                timestamp=1742400030.0,
                task_id=task_id,
                workstream_id=ws_id,
                outcome_class=(
                    TaskOutcomeClass.SUCCESS
                    if status == TaskStatus.PR_MERGED
                    else TaskOutcomeClass.EXPECTED_FAILURE
                ),
            )
        )

    ws_runtimes: dict[str, WorkstreamRuntime] = {}
    ws_ids = {ws_id for _, _, ws_id in tasks} or {"default"}
    for ws_id in ws_ids:
        ws_runtimes[ws_id] = WorkstreamRuntime(spec=WorkstreamSpec(id=ws_id))

    return OrchestratorResult(
        outcome=outcome,
        task_runtimes=task_runtimes,
        workstream_runtimes=ws_runtimes,
        events=tuple(events),
        fatal_error=fatal_error,
    )


class TestPrintSummary:
    def test_succeeded_table_has_headers_and_rows(self) -> None:
        result = _make_result(
            tasks=(
                ("add_fn", TaskStatus.PR_MERGED, "ws_add"),
                ("mul_fn", TaskStatus.PR_MERGED, "ws_mul"),
            ),
        )
        buf = io.StringIO()
        print_summary(result, stream=buf)
        output = buf.getvalue()
        assert "Outcome: succeeded" in output
        assert "Task" in output
        assert "Status" in output
        assert "add_fn" in output
        assert "mul_fn" in output
        assert "ws_add" in output
        assert "30s" in output

    def test_failed_table_shows_errors(self) -> None:
        result = _make_result(
            outcome=OrchestratorOutcome.COMPLETED_WITH_FAILURES,
            tasks=(("bad_fn", TaskStatus.FAILED, "default"),),
        )
        buf = io.StringIO()
        print_summary(result, stream=buf)
        output = buf.getvalue()
        assert "Errors:" in output
        assert "bad_fn" in output
        assert "bad_fn failed" in output

    def test_fatal_error_displayed(self) -> None:
        result = _make_result(
            outcome=OrchestratorOutcome.FATAL_INTERNAL_ERROR,
            fatal_error="RuntimeError: boom",
        )
        buf = io.StringIO()
        print_summary(result, stream=buf)
        output = buf.getvalue()
        assert "Fatal error:" in output
        assert "RuntimeError: boom" in output

    def test_ops_concerns_displayed_in_summary(self) -> None:
        result = _make_result(
            tasks=(("task_a", TaskStatus.PR_MERGED, "default"),),
        )
        result.task_runtimes["task_a"].artifacts.ops_concerns = [
            "slow build",
            "missing dep",
        ]
        buf = io.StringIO()
        print_summary(result, stream=buf)
        output = buf.getvalue()
        assert "Ops Concerns:" in output
        assert "task_a:" in output
        assert "slow build" in output
        assert "missing dep" in output

    def test_both_concern_types_displayed(self) -> None:
        result = _make_result(
            tasks=(("task_a", TaskStatus.PR_MERGED, "default"),),
        )
        result.task_runtimes["task_a"].artifacts.concerns = ["spec issue"]
        result.task_runtimes["task_a"].artifacts.ops_concerns = ["build flaky"]
        buf = io.StringIO()
        print_summary(result, stream=buf)
        output = buf.getvalue()
        assert "Concerns:" in output
        assert "spec issue" in output
        assert "Ops Concerns:" in output
        assert "build flaky" in output

    def test_empty_graph_no_table(self) -> None:
        result = _make_result()
        buf = io.StringIO()
        print_summary(result, stream=buf)
        output = buf.getvalue()
        assert "Outcome: succeeded" in output
        # No table rows.
        assert "Task" not in output
