"""Abstract agent interface.

This module defines the Agent abstract base class — the contract that all
concrete agent implementations must satisfy.

See also:
    addressing: AgentAddress abstract base for agent location types.

Classes:
    Agent: Abstract base for a live running agent instance.
"""

from abc import ABC, abstractmethod

from agentrelay.agent.core.addressing import AgentAddress


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
