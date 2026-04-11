"""Implementation of :class:`~agentrelay.task_runner.core.io.TaskLogCapture`.

Classes:
    WorktreeTaskLogCapture: Delegates agent log capture to the agent address.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentrelay.task_runtime import TaskRuntime


@dataclass
class WorktreeTaskLogCapture:
    """Delegate agent log capture to the agent address.

    Calls ``agent_address.capture_log()`` to write the agent's execution
    log (e.g. tmux scrollback) to the signal directory. This step runs
    unconditionally at task termination, before the teardown decision.
    """

    def capture_log(self, runtime: TaskRuntime) -> None:
        """Capture the agent's execution log to the signal directory.

        Args:
            runtime: Runtime envelope whose agent log should be captured.
        """
        agent_address = runtime.artifacts.agent_address

        if agent_address is not None:
            agent_address.capture_log(signal_dir=runtime.attempt_dir)
