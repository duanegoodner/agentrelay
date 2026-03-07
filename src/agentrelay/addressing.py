"""Agent addressing types.

This module defines how to refer to a live running agent instance — the
abstract base and concrete implementations for different execution environments
(tmux panes, cloud endpoints, subprocesses, etc.).

As new execution environments are added, each brings a corresponding concrete
address type here alongside its environment config in environments.py.

Classes:
    AgentAddress: Abstract base for addressing a running agent instance.
    TmuxAddress: Concrete address for agents running in tmux panes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class AgentAddress(ABC):
    """Abstract base for addressing a running agent instance.

    Defines the interface for locating a live agent regardless of execution
    environment. Concrete subclasses carry the environment-specific connection
    details needed to communicate with the agent (pane IDs, endpoints, etc.).

    Attributes:
        label: A human-readable string identifier for the agent's location.
    """

    @property
    @abstractmethod
    def label(self) -> str:
        """Return a human-readable identifier for this agent's location.

        Returns:
            String representation of the agent's address/location.
        """
        ...


@dataclass(frozen=True)
class TmuxAddress(AgentAddress):
    """Address of an agent running in a tmux pane.

    Attributes:
        session: The name of the tmux session.
        pane_id: The identifier of the tmux pane (e.g., "%1", "%2").
    """

    session: str
    pane_id: str

    @property
    def label(self) -> str:
        """Return a human-readable identifier combining session and pane.

        Returns:
            String in format "session:pane_id" (e.g., "agentrelay:%1").
        """
        return f"{self.session}:{self.pane_id}"
