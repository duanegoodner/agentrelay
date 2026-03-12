"""Agent abstractions for live coding-agent execution.

This package defines how orchestrator/runtime code interacts with running agents:
addressing types for locating an agent process and agent interfaces for sending
kickoff instructions in a concrete execution environment.

Subpackages:
    core: Abstract interfaces (Agent ABC, AgentAddress ABC).
    implementations: Concrete implementations (TmuxAgent, TmuxAddress).
"""

from agentrelay.agent.core.addressing import AgentAddress
from agentrelay.agent.core.agent import Agent
from agentrelay.agent.implementations.tmux_address import TmuxAddress
from agentrelay.agent.implementations.tmux_agent import TmuxAgent

__all__ = [
    "Agent",
    "AgentAddress",
    "TmuxAddress",
    "TmuxAgent",
]
