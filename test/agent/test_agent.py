"""Tests for agentrelay.v2.agent: live agent instances."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentrelay.agent import Agent, TmuxAddress, TmuxAgent
from agentrelay.task import AgentConfig, AgentFramework, TmuxEnvironment

# ── Tests for Agent (ABC) ──


class TestAgent:
    """Tests for Agent abstract base class."""

    def test_agent_cannot_be_instantiated(self) -> None:
        """Agent is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            Agent()  # type: ignore

    def test_agent_is_abstract_base(self) -> None:
        """Agent abstract base cannot be instantiated with direct call."""
        with pytest.raises(TypeError):
            # Try to create instance directly
            Agent()  # type: ignore


# ── Tests for TmuxAgent ──


class TestTmuxAgent:
    """Tests for TmuxAgent concrete implementation."""

    def test_tmux_agent_with_address(self) -> None:
        """TmuxAgent can be created with a TmuxAddress."""
        address = TmuxAddress(session="agentrelay", pane_id="%1")
        agent = TmuxAgent(_address=address)

        assert agent.address == address
        assert agent.address.label == "agentrelay:%1"

    def test_tmux_agent_address_is_accessible(self) -> None:
        """TmuxAgent.address property is accessible."""
        address = TmuxAddress(session="work", pane_id="%42")
        agent = TmuxAgent(_address=address)

        assert agent.address.label == "work:%42"

    def test_multiple_tmux_agents_independent(self) -> None:
        """Multiple TmuxAgent instances are independent."""
        agent1 = TmuxAgent(_address=TmuxAddress(session="s1", pane_id="%1"))
        agent2 = TmuxAgent(_address=TmuxAddress(session="s2", pane_id="%2"))

        assert agent1.address.label == "s1:%1"
        assert agent2.address.label == "s2:%2"
        assert agent1.address != agent2.address

    def test_tmux_agent_equality(self) -> None:
        """TmuxAgents with same address are equal."""
        address1 = TmuxAddress(session="agentrelay", pane_id="%1")
        address2 = TmuxAddress(session="agentrelay", pane_id="%1")

        agent1 = TmuxAgent(_address=address1)
        agent2 = TmuxAgent(_address=address2)

        assert agent1 == agent2

    def test_tmux_agent_inequality(self) -> None:
        """TmuxAgents with different addresses are not equal."""
        agent1 = TmuxAgent(_address=TmuxAddress(session="s1", pane_id="%1"))
        agent2 = TmuxAgent(_address=TmuxAddress(session="s1", pane_id="%2"))

        assert agent1 != agent2

    def test_tmux_agent_is_agent(self) -> None:
        """TmuxAgent is an instance of Agent."""
        address = TmuxAddress(session="agentrelay", pane_id="%1")
        agent = TmuxAgent(_address=address)

        assert isinstance(agent, Agent)


# ── Tests for TmuxAgent.from_config ──


class TestTmuxAgentFromConfig:
    """Tests for TmuxAgent.from_config class method."""

    @patch("agentrelay.agent.implementations.tmux_agent.tmux.send_keys")
    @patch("agentrelay.agent.implementations.tmux_agent.tmux.new_window")
    def test_creates_window_with_correct_args(
        self, mock_new_window: MagicMock, _mock_send_keys: MagicMock
    ) -> None:
        """Creates a tmux window using session, task_id, and worktree_path."""
        mock_new_window.return_value = "%42"
        config = AgentConfig(
            framework=AgentFramework.CLAUDE_CODE,
            environment=TmuxEnvironment(session="mysession"),
        )

        TmuxAgent.from_config(
            config=config,
            task_id="task_1",
            worktree_path=Path("/tmp/worktree"),
            signal_dir=Path("/tmp/signals"),
        )

        mock_new_window.assert_called_once_with(
            "mysession", "task_1", Path("/tmp/worktree")
        )

    @patch("agentrelay.agent.implementations.tmux_agent.tmux.send_keys")
    @patch("agentrelay.agent.implementations.tmux_agent.tmux.new_window")
    def test_returns_agent_with_correct_address(
        self, mock_new_window: MagicMock, _mock_send_keys: MagicMock
    ) -> None:
        """Returns a TmuxAgent with the correct session and pane_id."""
        mock_new_window.return_value = "%42"
        config = AgentConfig(
            environment=TmuxEnvironment(session="mysession"),
        )

        agent = TmuxAgent.from_config(
            config=config,
            task_id="task_1",
            worktree_path=Path("/tmp/worktree"),
            signal_dir=Path("/tmp/signals"),
        )

        assert isinstance(agent, TmuxAgent)
        assert agent.address.session == "mysession"
        assert agent.address.pane_id == "%42"

    @patch("agentrelay.agent.implementations.tmux_agent.tmux.send_keys")
    @patch("agentrelay.agent.implementations.tmux_agent.tmux.new_window")
    def test_sends_claude_command_with_model(
        self, mock_new_window: MagicMock, mock_send_keys: MagicMock
    ) -> None:
        """Sends claude command with --model flag when model is set."""
        mock_new_window.return_value = "%42"
        config = AgentConfig(model="claude-opus-4-6")

        TmuxAgent.from_config(
            config=config,
            task_id="task_1",
            worktree_path=Path("/tmp/worktree"),
            signal_dir=Path("/tmp/signals"),
        )

        cmd = mock_send_keys.call_args[0][1]
        assert "AGENTRELAY_SIGNAL_DIR=" in cmd
        assert "/tmp/signals" in cmd
        assert "--model claude-opus-4-6" in cmd
        assert "--dangerously-skip-permissions" in cmd

    @patch("agentrelay.agent.implementations.tmux_agent.tmux.send_keys")
    @patch("agentrelay.agent.implementations.tmux_agent.tmux.new_window")
    def test_sends_claude_command_without_model(
        self, mock_new_window: MagicMock, mock_send_keys: MagicMock
    ) -> None:
        """Sends claude command without --model flag when model is None."""
        mock_new_window.return_value = "%42"
        config = AgentConfig(model=None)

        TmuxAgent.from_config(
            config=config,
            task_id="task_1",
            worktree_path=Path("/tmp/worktree"),
            signal_dir=Path("/tmp/signals"),
        )

        cmd = mock_send_keys.call_args[0][1]
        assert "--model" not in cmd
        assert "claude" in cmd
        assert "--dangerously-skip-permissions" in cmd


# ── Tests for TmuxAgent.send_kickoff ──


class TestTmuxAgentSendKickoff:
    """Tests for TmuxAgent.send_kickoff method."""

    @patch("agentrelay.agent.implementations.tmux_agent.tmux.send_keys")
    @patch("agentrelay.agent.implementations.tmux_agent.tmux.wait_for_tui_ready")
    def test_waits_for_tui_then_sends_prompt(
        self, mock_wait: MagicMock, mock_send_keys: MagicMock
    ) -> None:
        """Waits for TUI ready, then sends the kickoff prompt."""
        mock_wait.return_value = True
        agent = TmuxAgent(_address=TmuxAddress(session="s", pane_id="%42"))

        agent.send_kickoff("/tmp/signals/instructions.md")

        mock_wait.assert_called_once_with("%42")
        mock_send_keys.assert_called_once_with(
            "%42",
            "Read /tmp/signals/instructions.md and follow the steps exactly.",
        )

    @patch("agentrelay.agent.implementations.tmux_agent.tmux.send_keys")
    @patch("agentrelay.agent.implementations.tmux_agent.tmux.wait_for_tui_ready")
    def test_uses_correct_pane_id(
        self, mock_wait: MagicMock, mock_send_keys: MagicMock
    ) -> None:
        """Uses the agent's pane_id for both wait and send."""
        mock_wait.return_value = True
        agent = TmuxAgent(_address=TmuxAddress(session="s", pane_id="%99"))

        agent.send_kickoff("/path/to/instructions.md")

        assert mock_wait.call_args[0][0] == "%99"
        assert mock_send_keys.call_args[0][0] == "%99"
