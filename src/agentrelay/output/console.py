"""Console output for orchestrator events and results.

Provides :class:`ConsoleListener` for real-time event output during a run,
and :func:`print_summary` for a post-run summary table.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, TextIO

from agentrelay.orchestrator import (
    OrchestratorEvent,
    OrchestratorResult,
    TaskOutcomeClass,
)
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

    def _on_workstream_merged(self, event: OrchestratorEvent) -> None:
        self._print(event.timestamp, event.workstream_id or "?", "merged to main")

    def _on_workstream_merge_failed(self, event: OrchestratorEvent) -> None:
        msg = event.message or "unknown error"
        self._print(
            event.timestamp,
            event.workstream_id or "?",
            f"merge FAILED: {msg}",
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
        TaskStatus.FAILED: "failed",
        TaskStatus.RUNNING: "running",
        TaskStatus.PR_CREATED: "pr_created",
        TaskStatus.PENDING: "pending",
    }
    rows: list[tuple[str, ...]] = []
    for task_id, runtime in result.task_runtimes.items():
        status = status_labels.get(runtime.state.status, runtime.state.status.value)
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
        if rt.state.status is TaskStatus.FAILED and rt.state.error
    ]
    if failed_errors:
        stream.write("\nErrors:\n")
        for task_id, error in failed_errors:
            stream.write(f"  {task_id}: {error}\n")

    stream.flush()
