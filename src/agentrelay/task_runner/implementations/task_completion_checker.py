"""Implementations of :class:`~agentrelay.task_runner.core.io.TaskCompletionChecker`.

Classes:
    SignalCompletionChecker: Polls signal files and parses completion signals.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentrelay.ops import signals
from agentrelay.task_runner.core.io import TaskCompletionSignal
from agentrelay.task_runtime import TaskRuntime


def _parse_concerns(concerns_text: str | None) -> tuple[str, ...]:
    """Parse concerns.log content into a tuple of concern strings.

    Each non-empty line in concerns.log is treated as one concern entry.
    Lines are stripped of leading/trailing whitespace.
    """
    if not concerns_text:
        return ()
    return tuple(line.strip() for line in concerns_text.splitlines() if line.strip())


@dataclass
class SignalCompletionChecker:
    """Poll signal files and parse the result into a completion signal.

    Watches the task's signal directory for ``.done`` or ``.failed`` files,
    then parses the signal file content and any ``concerns.log`` entries
    into a :class:`TaskCompletionSignal`.
    """

    poll_interval: float = 2.0

    async def wait_for_completion(self, runtime: TaskRuntime) -> TaskCompletionSignal:
        """Wait for terminal task signal from the execution boundary.

        Args:
            runtime: Runtime envelope being observed.

        Returns:
            TaskCompletionSignal: Terminal signal payload with outcome data.

        Raises:
            ValueError: If ``signal_dir`` is not set on the runtime state.
        """
        if runtime.state.signal_dir is None:
            raise ValueError("runtime.state.signal_dir must be set before polling")

        signal_dir = runtime.state.signal_dir
        found = await signals.poll_signal_files(
            signal_dir, (".done", ".failed"), self.poll_interval
        )

        content = signals.read_signal_file(signal_dir, found) or ""
        lines = content.splitlines()

        # Line 1 = ISO timestamp (informational), Line 2 = payload
        payload = lines[1].strip() if len(lines) > 1 else None

        concerns_text = signals.read_signal_file(signal_dir, "concerns.log")
        concerns = _parse_concerns(concerns_text)

        if found == ".done":
            return TaskCompletionSignal(
                outcome="done",
                pr_url=payload,
                concerns=concerns,
            )

        return TaskCompletionSignal(
            outcome="failed",
            error=payload,
            concerns=concerns,
        )
