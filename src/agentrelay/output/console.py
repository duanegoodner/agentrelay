"""Console output for orchestrator events and results.

Provides :class:`ConsoleListener` for real-time event output during a run,
:func:`print_summary` for a post-run summary table, and resume-specific
formatting functions (:func:`print_resume_summary`,
:func:`print_override_report`, :func:`print_config_warnings`).
"""

from __future__ import annotations

import sys
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Sequence, TextIO

from agentrelay.orchestrator import (
    OrchestratorEvent,
    OrchestratorResult,
    TaskOutcomeClass,
)
from agentrelay.resolved_validation import FrozenValidationResult
from agentrelay.task_runtime import TaskStatus


def _format_time(timestamp: float) -> str:
    """Format a Unix timestamp as HH:MM:SS local time."""
    return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")


def _format_duration(seconds: float) -> str:
    """Format a duration in seconds as a human-readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m{secs:02d}s"


@dataclass
class ConsoleListener:
    """Real-time console output for orchestrator events.

    Satisfies the :class:`~agentrelay.orchestrator.OrchestratorListener`
    protocol. Prints timestamped event lines to *stream* as events arrive.
    """

    stream: TextIO = field(default_factory=lambda: sys.stderr)
    verbose: bool = False
    _start_times: dict[str, float] = field(default_factory=dict, repr=False)

    def on_event(self, event: OrchestratorEvent) -> None:
        """Print a formatted line for each orchestrator event."""
        handler = getattr(self, f"_on_{event.kind}", None)
        if handler is not None:
            handler(event)

    def _print(self, timestamp: float, label: str, detail: str) -> None:
        ts = _format_time(timestamp)
        self.stream.write(f"[{ts}] {label:<14} {detail}\n")
        self.stream.flush()

    def _on_workstream_prepared(self, event: OrchestratorEvent) -> None:
        self._print(event.timestamp, event.workstream_id or "?", "prepared")

    def _on_workstream_prepare_failed(self, event: OrchestratorEvent) -> None:
        msg = event.message or "unknown error"
        self._print(
            event.timestamp,
            event.workstream_id or "?",
            f"prepare FAILED: {msg}",
        )

    def _on_task_started(self, event: OrchestratorEvent) -> None:
        task_id = event.task_id or "?"
        self._start_times[task_id] = event.timestamp
        attempt = event.attempt_num or 0
        parts = [f"started ({event.workstream_id}"]
        if attempt > 0:
            parts.append(f", retry {attempt}")
        parts.append(")")
        self._print(event.timestamp, task_id, "".join(parts))

    def _on_task_finished(self, event: OrchestratorEvent) -> None:
        task_id = event.task_id or "?"
        start = self._start_times.pop(task_id, None)
        duration = _format_duration(event.timestamp - start) if start else ""

        if event.outcome_class == TaskOutcomeClass.SUCCESS:
            detail = f"succeeded ({duration})"
            if event.message:
                detail += f" \u2192 {event.message}"
        elif event.outcome_class == TaskOutcomeClass.INTERNAL_ERROR:
            detail = f"INTERNAL ERROR: {event.message or ''}"
        else:
            msg = event.message or ""
            if msg == "retry_scheduled":
                detail = f"failed, retrying ({duration})"
            elif msg == "max_attempts_reached":
                detail = f"failed, no retries left ({duration})"
            else:
                detail = f"failed: {msg}"

        self._print(event.timestamp, task_id, detail)

    def _on_task_blocked(self, event: OrchestratorEvent) -> None:
        self._print(event.timestamp, event.task_id or "?", "blocked")

    def _on_workstream_pr_created(self, event: OrchestratorEvent) -> None:
        detail = "integration PR created"
        if event.message:
            detail += f" \u2192 {event.message}"
        self._print(event.timestamp, event.workstream_id or "?", detail)

    def _on_workstream_integration_failed(self, event: OrchestratorEvent) -> None:
        msg = event.message or "unknown error"
        self._print(
            event.timestamp,
            event.workstream_id or "?",
            f"integration FAILED: {msg}",
        )

    def _on_workstream_merged(self, event: OrchestratorEvent) -> None:
        detail = "integration PR merged"
        if event.message:
            detail += f" \u2192 {event.message}"
        self._print(event.timestamp, event.workstream_id or "?", detail)

    def _on_workstream_auto_merged(self, event: OrchestratorEvent) -> None:
        detail = "integration PR auto-merged"
        if event.message:
            detail += f" \u2192 {event.message}"
        self._print(event.timestamp, event.workstream_id or "?", detail)

    def _on_workstream_integration_skipped(self, event: OrchestratorEvent) -> None:
        detail = "integration skipped (no changes)"
        if event.message:
            detail += f": {event.message}"
        self._print(event.timestamp, event.workstream_id or "?", detail)

    def _on_workstream_auto_merge_skipped(self, event: OrchestratorEvent) -> None:
        detail = "auto-merge skipped"
        if event.message:
            detail += f": {event.message}"
        self._print(event.timestamp, event.workstream_id or "?", detail)

    def _on_workstream_auto_merge_failed(self, event: OrchestratorEvent) -> None:
        msg = event.message or "unknown error"
        self._print(
            event.timestamp,
            event.workstream_id or "?",
            f"auto-merge FAILED: {msg}",
        )

    def _on_waiting_for_integration_merge(self, event: OrchestratorEvent) -> None:
        self._print(
            event.timestamp,
            "orchestrator",
            "waiting for integration PR merge...",
        )

    # -- Verbose-only step events (from StandardTaskRunner) --

    def _on_task_prepared(self, event: OrchestratorEvent) -> None:
        if self.verbose:
            self._print(
                event.timestamp,
                event.task_id or "?",
                f"prepared ({event.message or ''})",
            )

    def _on_task_launched(self, event: OrchestratorEvent) -> None:
        if self.verbose:
            self._print(
                event.timestamp,
                event.task_id or "?",
                f"agent launched ({event.message or ''})",
            )

    def _on_task_waiting(self, event: OrchestratorEvent) -> None:
        if self.verbose:
            self._print(
                event.timestamp,
                event.task_id or "?",
                "waiting for completion signal",
            )

    def _on_task_gate_running(self, event: OrchestratorEvent) -> None:
        if self.verbose:
            self._print(
                event.timestamp,
                event.task_id or "?",
                f"gate running ({event.message or ''})",
            )

    def _on_task_gate_passed(self, event: OrchestratorEvent) -> None:
        if self.verbose:
            self._print(
                event.timestamp,
                event.task_id or "?",
                "gate passed",
            )

    def _on_task_gate_failed(self, event: OrchestratorEvent) -> None:
        msg = event.message or "unknown command"
        self._print(
            event.timestamp,
            event.task_id or "?",
            f"gate FAILED: {msg}",
        )

    def _on_task_pr_merging(self, event: OrchestratorEvent) -> None:
        if self.verbose:
            self._print(
                event.timestamp,
                event.task_id or "?",
                f"merging PR to integration branch",
            )


# ---------------------------------------------------------------------------
# Post-run summary table
# ---------------------------------------------------------------------------


def _task_durations(
    events: tuple[OrchestratorEvent, ...],
) -> dict[str, Optional[float]]:
    """Compute per-task durations from event timestamps."""
    starts: dict[str, float] = {}
    durations: dict[str, Optional[float]] = {}
    for event in events:
        if event.kind == "task_started" and event.task_id:
            starts[event.task_id] = event.timestamp
        elif event.kind == "task_finished" and event.task_id:
            start = starts.get(event.task_id)
            if start is not None:
                durations[event.task_id] = event.timestamp - start
            else:
                durations[event.task_id] = None
    return durations


def print_summary(
    result: OrchestratorResult,
    *,
    stream: TextIO = sys.stderr,
) -> None:
    """Print a post-run summary table.

    Args:
        result: Terminal orchestration result.
        stream: Output stream (default stderr).
    """
    durations = _task_durations(result.events)

    stream.write(f"\nOutcome: {result.outcome.value}\n")
    if result.fatal_error:
        stream.write(f"Fatal error:\n{result.fatal_error}\n")

    if not result.task_runtimes:
        return

    # Column headers and rows.
    headers = ("Task", "Status", "Workstream", "Attempts", "Duration", "PR")
    status_labels = {
        TaskStatus.PR_MERGED: "succeeded",
        TaskStatus.COMPLETED: "succeeded",
        TaskStatus.FAILED: "failed",
        TaskStatus.RUNNING: "running",
        TaskStatus.PR_CREATED: "pr_created",
        TaskStatus.PENDING: "pending",
    }
    rows: list[tuple[str, ...]] = []
    for task_id, runtime in result.task_runtimes.items():
        status = status_labels.get(runtime.status, runtime.status.value)
        workstream = runtime.task.workstream_id
        attempts = str(runtime.state.attempt_num + 1)
        dur = durations.get(task_id)
        duration = _format_duration(dur) if dur is not None else "-"
        pr_url = runtime.artifacts.pr_url or ""
        rows.append((task_id, status, workstream, attempts, duration, pr_url))

    # Compute column widths.
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def _fmt_row(cells: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    stream.write("\n")
    stream.write(_fmt_row(headers) + "\n")
    stream.write("  ".join("\u2500" * w for w in widths) + "\n")
    for row in rows:
        stream.write(_fmt_row(row) + "\n")

    # Total duration from first event to last event.
    if result.events:
        total = result.events[-1].timestamp - result.events[0].timestamp
        stream.write(f"\nTotal: {_format_duration(total)}\n")

    # Per-task errors for failed tasks.
    failed_errors = [
        (tid, rt.state.error)
        for tid, rt in result.task_runtimes.items()
        if rt.status is TaskStatus.FAILED and rt.state.error
    ]
    if failed_errors:
        stream.write("\nErrors:\n")
        for task_id, error in failed_errors:
            stream.write(f"  {task_id}: {error}\n")

    # Per-task concerns.
    task_concerns = [
        (tid, rt.artifacts.concerns)
        for tid, rt in result.task_runtimes.items()
        if rt.artifacts.concerns
    ]
    if task_concerns:
        stream.write("\nConcerns:\n")
        _write_concerns(stream, task_concerns)

    # Per-task ops concerns.
    task_ops_concerns = [
        (tid, rt.artifacts.ops_concerns)
        for tid, rt in result.task_runtimes.items()
        if rt.artifacts.ops_concerns
    ]
    if task_ops_concerns:
        stream.write("\nOps Concerns:\n")
        _write_concerns(stream, task_ops_concerns)

    stream.flush()


def _write_concerns(
    stream: TextIO,
    task_concerns: Sequence[tuple[str, Sequence[str]]],
) -> None:
    """Write formatted concern entries with wrapped text."""
    for task_id, concerns in task_concerns:
        for concern in concerns:
            stream.write(f"\n  {task_id}:\n")
            wrapped = textwrap.fill(
                concern, width=76, initial_indent="    ", subsequent_indent="    "
            )
            stream.write(wrapped + "\n")


# ---------------------------------------------------------------------------
# Resume-specific output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResumeTaskInfo:
    """Per-task information for the resume summary table.

    Attributes:
        task_id: Task identifier.
        status: Task status from the prior run probe.
        frozen: Whether the task has a frozen ``resolved.json`` record.
    """

    task_id: str
    status: TaskStatus
    frozen: bool


def _resume_action(info: ResumeTaskInfo) -> str:
    """Compute the human-readable action for a task in the resume table."""
    if info.frozen:
        return "skip (frozen)"
    if info.status == TaskStatus.FAILED:
        return "restart"
    if info.status == TaskStatus.PENDING:
        return "start"
    # Stale states (RUNNING, PR_CREATED) should already be normalized by the
    # probe, but handle gracefully.
    return "restart"


def print_resume_summary(
    graph_name: str,
    run_number: int,
    prior_run_number: int,
    task_infos: Sequence[ResumeTaskInfo],
    *,
    stream: TextIO = sys.stderr,
) -> None:
    """Print a pre-orchestrator resume summary table.

    Shows the status and planned action for each task in graph topological
    order.

    Args:
        graph_name: Name of the graph being resumed.
        run_number: New run number being created.
        prior_run_number: Run number of the prior run being resumed from.
        task_infos: Per-task resume info in graph topological order.
        stream: Output stream (default stderr).
    """
    stream.write(
        f"\nResuming graph '{graph_name}' (run {run_number}, prior: run {prior_run_number})\n"
    )

    if not task_infos:
        stream.write("\n  (no tasks)\n")
        stream.flush()
        return

    headers = ("Task", "Status", "Action")
    rows: list[tuple[str, str, str]] = []
    status_labels = {
        TaskStatus.PR_MERGED: "completed",
        TaskStatus.COMPLETED: "completed",
        TaskStatus.FAILED: "failed",
        TaskStatus.RUNNING: "running",
        TaskStatus.PR_CREATED: "pr_created",
        TaskStatus.PENDING: "pending",
    }
    for info in task_infos:
        label = status_labels.get(info.status, info.status.value)
        action = _resume_action(info)
        rows.append((info.task_id, label, action))

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def _fmt(cells: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    stream.write("\n")
    stream.write("  " + _fmt(headers) + "\n")
    stream.write("  " + "  ".join("\u2500" * w for w in widths) + "\n")
    for row in rows:
        stream.write("  " + _fmt(row) + "\n")

    stream.flush()


def print_override_report(
    validation: FrozenValidationResult,
    *,
    stream: TextIO = sys.stderr,
) -> None:
    """Print informational override report for frozen tasks.

    Called only when ``validation.has_overrides`` is ``True``.

    Args:
        validation: Frozen validation result from
            :func:`~agentrelay.resolved_validation.validate_frozen_tasks`.
        stream: Output stream (default stderr).
    """
    stream.write(
        "\nFrozen task overrides (current YAML differs from executed values):\n"
    )
    for task_result in validation.task_results:
        if not task_result.has_overrides:
            continue
        stream.write(f"\n  {task_result.task_id}:\n")
        for mismatch in task_result.mismatches:
            stream.write(
                f"    {mismatch.field}: {mismatch.resolved_value}"
                f" (current: {mismatch.current_value})\n"
            )
    stream.flush()


def print_config_warnings(
    warnings: Sequence[str],
    *,
    stream: TextIO = sys.stderr,
) -> None:
    """Print config mismatch warnings from a prior run.

    Args:
        warnings: Warning strings from config comparison.
        stream: Output stream (default stderr).
    """
    stream.write("\nConfig changed from prior run:\n")
    for warning in warnings:
        stream.write(f"  {warning}\n")
    stream.flush()
