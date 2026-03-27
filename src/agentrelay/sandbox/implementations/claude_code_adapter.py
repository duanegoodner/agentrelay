"""Claude Code framework adapter.

This module provides :class:`ClaudeCodeAdapter`, which builds the CLI command
string for launching a Claude Code agent. The command construction logic is
extracted from :meth:`TmuxAgent.from_config` to enable independent testing
and sandbox wrapping.

Classes:
    ClaudeCodeAdapter: Builds Claude Code CLI commands.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentrelay.task import AgentConfig


class ClaudeCodeAdapter:
    """Build the CLI command string for launching a Claude Code agent.

    Constructs the ``claude`` CLI invocation with the signal directory
    environment variable, optional model flag, and permission skip flag.
    """

    def build_command(self, config: AgentConfig, signal_dir: Path) -> str:
        """Build the Claude Code CLI command string.

        Args:
            config: Agent configuration. Uses ``config.model`` for the
                ``--model`` flag (omitted when ``None``).
            signal_dir: Path to the signal directory, injected as the
                ``AGENTRELAY_SIGNAL_DIR`` environment variable prefix.

        Returns:
            The raw CLI command string, e.g.::

                AGENTRELAY_SIGNAL_DIR="/path" claude --model X --dangerously-skip-permissions
        """
        model_flag = f" --model {config.model}" if config.model else ""
        return (
            f'AGENTRELAY_SIGNAL_DIR="{signal_dir}"'
            f" claude{model_flag}"
            f" --dangerously-skip-permissions"
        )
