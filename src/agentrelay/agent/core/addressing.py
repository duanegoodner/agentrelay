"""Abstract agent addressing type.

This module defines the abstract base for referring to a live running agent
instance, independent of any concrete execution environment.

Classes:
    AgentAddress: Abstract base for addressing a running agent instance.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


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

    def capture_log(self, signal_dir: Optional[Path] = None) -> None:
        """Capture agent execution log to the signal directory.

        Called unconditionally when a task reaches a terminal status, regardless
        of teardown mode. The default implementation is a no-op; subclasses
        override for environment-specific log capture (e.g. tmux scrollback).

        Args:
            signal_dir: Directory for writing the captured log. None if no
                signal directory is available.
        """

    def teardown(
        self,
        signal_dir: Optional[Path] = None,
        keep_panes: bool = False,
    ) -> None:
        """Release environment-specific resources for this agent address.

        Called during task teardown to clean up execution resources. The default
        implementation is a no-op; subclasses override for environment-specific
        cleanup (e.g. killing tmux windows, deleting branches).

        If ``capture_log()`` has already written ``agent.log``, implementations
        should skip redundant capture (idempotent).

        Args:
            signal_dir: Directory for writing teardown artifacts (e.g. agent logs).
                None if no signal directory is available.
            keep_panes: If True, preserve the agent's execution environment
                (e.g. tmux window) for debugging rather than destroying it.
        """
