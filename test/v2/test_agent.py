"""Tests for agentrelaysmall.v2.agent: live agent instances."""

from pathlib import Path

import pytest

from agentrelaysmall.v2.agent import Agent
from agentrelaysmall.v2.task import AgentConfig, AgentFramework, AgentRole
from agentrelaysmall.v2.task_runtime import TmuxAddress

# ── Tests for Agent ──


class TestAgent:
    """Tests for Agent (live running instance)."""

    def test_agent_with_tmux_address(self) -> None:
        """Agent can be created with a TmuxAddress."""
        address = TmuxAddress(session="agentrelay", pane_id="%1")
        agent = Agent(address=address)

        assert agent.address == address
        assert agent.address.label == "agentrelay:%1"

    def test_agent_address_is_accessible(self) -> None:
        """Agent.address property is accessible."""
        address = TmuxAddress(session="work", pane_id="%42")
        agent = Agent(address=address)

        assert agent.address.label == "work:%42"

    def test_spawn_not_implemented(self) -> None:
        """Agent.spawn() raises NotImplementedError."""
        config = AgentConfig(
            framework=AgentFramework.CLAUDE_CODE,
            model="claude-opus-4-6",
        )
        tmux_session = "agentrelay"
        task_id = "my_task"
        worktree_path = Path("/tmp/worktree-123")
        signal_dir = Path("/tmp/signals")

        with pytest.raises(NotImplementedError):
            Agent.spawn(
                config=config,
                tmux_session=tmux_session,
                task_id=task_id,
                worktree_path=worktree_path,
                signal_dir=signal_dir,
            )

    def test_send_kickoff_not_implemented(self) -> None:
        """Agent.send_kickoff() raises NotImplementedError."""
        address = TmuxAddress(session="agentrelay", pane_id="%1")
        agent = Agent(address=address)

        with pytest.raises(NotImplementedError):
            agent.send_kickoff(instructions_path="/tmp/instructions.md")

    def test_multiple_agents_independent(self) -> None:
        """Multiple Agent instances are independent."""
        agent1 = Agent(address=TmuxAddress(session="s1", pane_id="%1"))
        agent2 = Agent(address=TmuxAddress(session="s2", pane_id="%2"))

        assert agent1.address.label == "s1:%1"
        assert agent2.address.label == "s2:%2"
        assert agent1.address != agent2.address

    def test_spawn_signature_accepts_agentconfig(self) -> None:
        """Agent.spawn() classmethod accepts AgentConfig as first parameter."""
        # This test verifies the signature matches the design
        # (actual spawn logic is NotImplementedError)
        config = AgentConfig(model="claude-opus-4-6")
        tmux_session = "agentrelay"
        task_id = "task"
        worktree_path = Path("/tmp/work")
        signal_dir = Path("/tmp/signals")

        # Should raise NotImplementedError, not TypeError from bad signature
        with pytest.raises(NotImplementedError):
            Agent.spawn(
                config=config,
                tmux_session=tmux_session,
                task_id=task_id,
                worktree_path=worktree_path,
                signal_dir=signal_dir,
            )

    def test_send_kickoff_accepts_instructions_path(self) -> None:
        """Agent.send_kickoff() accepts instructions_path parameter."""
        address = TmuxAddress(session="agentrelay", pane_id="%1")
        agent = Agent(address=address)

        # Should raise NotImplementedError, not TypeError from bad signature
        with pytest.raises(NotImplementedError):
            agent.send_kickoff(instructions_path="/signal/instructions.md")

    def test_agent_equality(self) -> None:
        """Agents with same address are equal."""
        address1 = TmuxAddress(session="agentrelay", pane_id="%1")
        address2 = TmuxAddress(session="agentrelay", pane_id="%1")

        agent1 = Agent(address=address1)
        agent2 = Agent(address=address2)

        # Frozen dataclass: equality is based on field values
        assert agent1 == agent2

    def test_agent_inequality(self) -> None:
        """Agents with different addresses are not equal."""
        agent1 = Agent(address=TmuxAddress(session="s1", pane_id="%1"))
        agent2 = Agent(address=TmuxAddress(session="s1", pane_id="%2"))

        assert agent1 != agent2
