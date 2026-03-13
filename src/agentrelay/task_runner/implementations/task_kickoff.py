"""Implementations of :class:`~agentrelay.task_runner.core.io.TaskKickoff`.

Classes:
    TmuxTaskKickoff: Sends kickoff instructions to a launched agent.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentrelay.agent import Agent
from agentrelay.task_runtime import TaskRuntime


@dataclass
class TmuxTaskKickoff:
    """Send kickoff instructions to a launched agent.

    Delegates to :meth:`Agent.send_kickoff` with the path to the
    ``instructions.md`` file in the task's signal directory.
    """

    def kickoff(self, runtime: TaskRuntime, agent: Agent) -> None:
        """Send kickoff instructions to the launched task agent.

        Args:
            runtime: Runtime envelope for the task being kicked off.
            agent: Live agent handle to send instructions to.

        Raises:
            ValueError: If ``signal_dir`` is not set on the runtime state.
        """
        if runtime.state.signal_dir is None:
            raise ValueError("runtime.state.signal_dir must be set before kickoff")

        instructions_path = str(runtime.state.signal_dir / "instructions.md")
        agent.send_kickoff(instructions_path)
