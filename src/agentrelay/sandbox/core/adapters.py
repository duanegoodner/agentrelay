"""Agent framework adapter protocol for building framework-specific commands.

This module defines the :class:`AgentFrameworkAdapter` protocol that framework
adapters must satisfy. The protocol is runtime-checkable, so
``isinstance(obj, AgentFrameworkAdapter)`` works at runtime.

Protocols:
    AgentFrameworkAdapter: Builds framework-specific agent CLI commands.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from agentrelay.task import AgentConfig


@runtime_checkable
class AgentFrameworkAdapter(Protocol):
    """Protocol for building framework-specific agent CLI commands.

    Implementations construct the raw CLI invocation string for a specific
    AI framework (Claude Code, Codex, etc.). The resulting command is then
    wrapped by an :class:`AgentSandbox` before execution.

    Methods:
        build_command: Build the CLI command string for launching an agent.
    """

    def build_command(self, config: AgentConfig, signal_dir: Path) -> str:
        """Build the framework-specific CLI command string.

        Args:
            config: Agent configuration with framework, model, and settings.
            signal_dir: Path to the signal directory for this task.

        Returns:
            The raw CLI command string ready for sandbox wrapping.
        """
        ...
