"""Tmux agent implementation.

Classes:
    TmuxAgent: Concrete agent running in a tmux pane.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from agentrelay.agent.core.agent import Agent
from agentrelay.agent.implementations.tmux_address import TmuxAddress
from agentrelay.ops import tmux

if TYPE_CHECKING:
    from agentrelay.task import AgentConfig


@dataclass
class TmuxAgent(Agent):
    """A live agent running in a tmux pane.

    Represents a Claude Code instance launched in a tmux pane. The agent holds
    the TmuxAddress (session + pane_id) of its running process.

    Attributes:
        _address: The tmux address (session and pane_id) of the running agent.
    """

    _address: TmuxAddress

    @property
    def address(self) -> TmuxAddress:
        """Return the tmux address of this agent."""
        return self._address

    @classmethod
    def from_config(
        cls,
        config: AgentConfig,
        task_id: str,
        worktree_path: Path,
        cmd: str,
    ) -> TmuxAgent:
        """Create a tmux pane, send a pre-built command, and return the TmuxAgent handle.

        Creates a new tmux window in the session specified by config.environment,
        sends the provided command string, and returns a TmuxAgent object that
        can be used to communicate with the running process.

        Args:
            config: AgentConfig specifying environment.
                config.environment must be TmuxEnvironment.
            task_id: Window name for the tmux window (typically ``{graph_name}-{task_id}``).
            worktree_path: Path to the git worktree where the agent will work.
            cmd: Pre-built command string to send to the tmux pane. Typically
                constructed by an :class:`AgentFrameworkAdapter` and wrapped
                by an :class:`AgentSandbox`.

        Returns:
            A TmuxAgent instance with its address set to the created tmux pane.
        """
        session = config.environment.session
        pane_id = tmux.new_window(session, task_id, worktree_path)
        tmux.send_keys(pane_id, cmd)

        return cls(_address=TmuxAddress(session=session, pane_id=pane_id))

    def send_kickoff(self, instructions_path: str) -> None:
        """Wait for the agent's TUI to be ready, then send the kickoff message.

        Sends an initial prompt to the agent pointing it to its task instructions.
        This activates the agent to begin autonomous work.

        The message sent is: "Read {instructions_path} and follow the steps exactly."

        Args:
            instructions_path: Path to the instructions file the agent should read.
                Typically the signal_dir/instructions.md file written by the orchestrator.
        """
        pane_id = self._address.pane_id
        tmux.wait_for_tui_ready(pane_id)
        tmux.send_keys(
            pane_id,
            f"Read {instructions_path} and follow the steps exactly.",
        )
