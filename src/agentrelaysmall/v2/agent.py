"""Agent class: live running instance of a task executor.

This module defines the Agent abstract base class and concrete implementations
for different execution environments. An Agent represents a running coding assistant
(e.g., Claude Code in a tmux pane) and can be told to begin work.

Classes:
    Agent: Abstract base for a live running agent instance.
    TmuxAgent: Concrete agent running in a tmux pane.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentrelaysmall.v2.task import AgentConfig, TmuxEnvironment

from agentrelaysmall.v2.task_runtime import AgentAddress, TmuxAddress


class Agent(ABC):
    """Abstract base for a live running agent instance.

    An Agent represents a coding assistant that has been spawned in a specific
    execution environment and can be instructed to begin work. Different execution
    environments (tmux, cloud, etc.) are represented by concrete subclasses.

    The Agent does not store configuration or role information — these are
    accessible via runtime.task.primary_agent and runtime.task.role, ensuring
    a single source of truth.
    """

    @abstractmethod
    def send_kickoff(self, instructions_path: str) -> None:
        """Send kickoff instructions to the running agent.

        Activates the agent to begin autonomous work.

        Args:
            instructions_path: Path to the instructions file the agent should read.
                Typically the signal_dir/instructions.md file written by the orchestrator.
        """
        ...

    @property
    @abstractmethod
    def address(self) -> AgentAddress:
        """Return the address of this running agent.

        Returns:
            An AgentAddress indicating where the agent is running (type depends
            on the concrete Agent subclass).
        """
        ...


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
        signal_dir: Path,
    ) -> TmuxAgent:
        """Create a tmux pane, launch Claude Code, and return the TmuxAgent handle.

        Creates a new tmux window in the session specified by config.environment,
        launches Claude Code with the specified model configuration, and returns
        a TmuxAgent object that can be used to communicate with the running process.

        Args:
            config: AgentConfig specifying framework, model, adr_verbosity, and
                environment. config.environment must be TmuxEnvironment.
                config.model is passed as --model flag (None = framework default).
            task_id: Identifier for this task (used as tmux window name).
            worktree_path: Path to the git worktree where the agent will work.
            signal_dir: Path to the signal directory where task files are written.

        Returns:
            A TmuxAgent instance with its address set to the created tmux pane.

        Raises:
            NotImplementedError: This is a stub awaiting real subprocess implementation.
        """
        raise NotImplementedError(
            "TmuxAgent.from_config() requires subprocess/tmux integration. "
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
            "TmuxAgent.send_kickoff() requires tmux interaction. "
            "Implement in a later PR focused on launcher infrastructure."
        )
