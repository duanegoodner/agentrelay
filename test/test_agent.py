"""Tests for agentrelay.v2.agent: live agent instances."""

from pathlib import Path

import pytest

from agentrelay.addressing import TmuxAddress
from agentrelay.agent import Agent, TmuxAgent
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

    def test_from_config_not_implemented(self) -> None:
        """TmuxAgent.from_config() raises NotImplementedError (stub)."""
        config = AgentConfig(
            framework=AgentFramework.CLAUDE_CODE,
            model="claude-opus-4-6",
            environment=TmuxEnvironment(session="agentrelay"),
        )
        task_id = "my_task"
        worktree_path = Path("/tmp/worktree-123")
        signal_dir = Path("/tmp/signals")

        with pytest.raises(NotImplementedError):
            TmuxAgent.from_config(
                config=config,
                task_id=task_id,
                worktree_path=worktree_path,
                signal_dir=signal_dir,
            )

    def test_send_kickoff_not_implemented(self) -> None:
        """TmuxAgent.send_kickoff() raises NotImplementedError (stub)."""
        address = TmuxAddress(session="agentrelay", pane_id="%1")
        agent = TmuxAgent(_address=address)

        with pytest.raises(NotImplementedError):
            agent.send_kickoff(instructions_path="/tmp/instructions.md")

    def test_multiple_tmux_agents_independent(self) -> None:
        """Multiple TmuxAgent instances are independent."""
        agent1 = TmuxAgent(_address=TmuxAddress(session="s1", pane_id="%1"))
        agent2 = TmuxAgent(_address=TmuxAddress(session="s2", pane_id="%2"))

        assert agent1.address.label == "s1:%1"
        assert agent2.address.label == "s2:%2"
        assert agent1.address != agent2.address

    def test_from_config_accepts_all_parameters(self) -> None:
        """TmuxAgent.from_config() accepts all required parameters."""
        config = AgentConfig(model="claude-opus-4-6")
        task_id = "task"
        worktree_path = Path("/tmp/work")
        signal_dir = Path("/tmp/signals")

        # Should raise NotImplementedError, not TypeError from bad signature
        with pytest.raises(NotImplementedError):
            TmuxAgent.from_config(
                config=config,
                task_id=task_id,
                worktree_path=worktree_path,
                signal_dir=signal_dir,
            )

    def test_send_kickoff_accepts_instructions_path(self) -> None:
        """TmuxAgent.send_kickoff() accepts instructions_path parameter."""
        address = TmuxAddress(session="agentrelay", pane_id="%1")
        agent = TmuxAgent(_address=address)

        # Should raise NotImplementedError, not TypeError from bad signature
        with pytest.raises(NotImplementedError):
            agent.send_kickoff(instructions_path="/signal/instructions.md")

    def test_tmux_agent_equality(self) -> None:
        """TmuxAgents with same address are equal."""
        address1 = TmuxAddress(session="agentrelay", pane_id="%1")
        address2 = TmuxAddress(session="agentrelay", pane_id="%1")

        agent1 = TmuxAgent(_address=address1)
        agent2 = TmuxAgent(_address=address2)

        # Frozen dataclass: equality is based on field values
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
