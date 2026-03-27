"""Tests for AgentFrameworkAdapter protocol and ClaudeCodeAdapter implementation."""

from pathlib import Path

from agentrelay.sandbox import AgentFrameworkAdapter, ClaudeCodeAdapter
from agentrelay.task import AgentConfig


class TestAgentFrameworkAdapterProtocol:
    """Tests for the AgentFrameworkAdapter protocol."""

    def test_is_runtime_checkable(self) -> None:
        """ClaudeCodeAdapter satisfies the AgentFrameworkAdapter protocol."""
        assert isinstance(ClaudeCodeAdapter(), AgentFrameworkAdapter)


class TestClaudeCodeAdapter:
    """Tests for ClaudeCodeAdapter.build_command."""

    def test_build_command_with_model(self) -> None:
        """Includes --model flag when config.model is set."""
        adapter = ClaudeCodeAdapter()
        config = AgentConfig(model="claude-opus-4-6")
        signal_dir = Path("/tmp/signals")

        cmd = adapter.build_command(config, signal_dir)

        assert cmd == (
            'AGENTRELAY_SIGNAL_DIR="/tmp/signals"'
            " claude --model claude-opus-4-6"
            " --dangerously-skip-permissions"
        )

    def test_build_command_without_model(self) -> None:
        """Omits --model flag when config.model is None."""
        adapter = ClaudeCodeAdapter()
        config = AgentConfig(model=None)
        signal_dir = Path("/tmp/signals")

        cmd = adapter.build_command(config, signal_dir)

        assert cmd == (
            'AGENTRELAY_SIGNAL_DIR="/tmp/signals"'
            " claude"
            " --dangerously-skip-permissions"
        )

    def test_build_command_includes_signal_dir(self) -> None:
        """Injects AGENTRELAY_SIGNAL_DIR with the provided path."""
        adapter = ClaudeCodeAdapter()
        config = AgentConfig()
        signal_dir = Path("/repo/.workflow/graph/signals/task_a")

        cmd = adapter.build_command(config, signal_dir)

        assert 'AGENTRELAY_SIGNAL_DIR="/repo/.workflow/graph/signals/task_a"' in cmd

    def test_build_command_includes_skip_permissions(self) -> None:
        """Always includes --dangerously-skip-permissions."""
        adapter = ClaudeCodeAdapter()
        config = AgentConfig()

        cmd = adapter.build_command(config, Path("/tmp/signals"))

        assert "--dangerously-skip-permissions" in cmd
