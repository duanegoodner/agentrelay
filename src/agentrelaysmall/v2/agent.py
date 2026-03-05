"""Agent class: live running instance of a task executor.

This module defines the Agent class, which represents a running coding assistant
(e.g., Claude Code in a tmux pane). An Agent is instantiated from an AgentConfig
and holds the address where it is running.

Classes:
    Agent: A live running agent instance.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentrelaysmall.v2.task import AgentConfig

from agentrelaysmall.v2.task_runtime import AgentAddress


@dataclass
class Agent:
    """A live running agent instance.

    An Agent represents a coding assistant that has been spawned in a specific
    execution environment (e.g., a tmux pane running Claude Code). It holds the
    address where it is running and can be instructed to begin work via
    send_kickoff().

    The Agent does not store configuration or role information — these are
    accessible via runtime.task.primary_agent and runtime.task.role, ensuring
    a single source of truth.

    Attributes:
        address: Where the agent is running (e.g., TmuxAddress for tmux pane).
    """

    address: AgentAddress

    @classmethod
    def spawn(
        cls,
        config: AgentConfig,
        tmux_session: str,
        task_id: str,
        worktree_path: Path,
        signal_dir: Path,
    ) -> Agent:
        """Create a tmux pane, launch Claude Code, and return the Agent handle.

        Creates a new tmux window in the specified session, launches Claude Code
        with the specified model configuration, and returns an Agent object that
        can be used to communicate with the running process.

        Args:
            config: AgentConfig specifying framework and model.
                config.model is passed as --model flag (None = framework default).
                config.framework must be CLAUDE_CODE (only supported for now).
            tmux_session: Name of the tmux session where the pane will be created.
            task_id: Identifier for this task (used as tmux window name).
            worktree_path: Path to the git worktree where the agent will work.
            signal_dir: Path to the signal directory where task files are written.

        Returns:
            An Agent instance with its address set to the created tmux pane.

        Raises:
            NotImplementedError: This is a stub awaiting real subprocess implementation.
        """
        raise NotImplementedError(
            "Agent.spawn() requires subprocess/tmux integration. "
            "Implement in a later PR focused on launcher infrastructure."
        )

    def send_kickoff(self, instructions_path: str) -> None:
        """Wait for the agent's TUI to be ready, then send the kickoff message.

        Sends an initial prompt to the agent pointing it to its task instructions.
        This activates the agent to begin autonomous work.

        The message sent is: "Read {instructions_path} and follow the steps exactly."

        Args:
            instructions_path: Path to the instructions file the agent should read.
                Typically the signal_dir/instructions.md file written by the orchestrator.

        Raises:
            NotImplementedError: This is a stub awaiting real TUI interaction code.
        """
        raise NotImplementedError(
            "Agent.send_kickoff() requires tmux interaction. "
            "Implement in a later PR focused on launcher infrastructure."
        )
