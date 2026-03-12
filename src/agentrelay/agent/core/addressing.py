"""Abstract agent addressing type.

This module defines the abstract base for referring to a live running agent
instance, independent of any concrete execution environment.

Classes:
    AgentAddress: Abstract base for addressing a running agent instance.
"""

from abc import ABC, abstractmethod


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
