"""Agent abstractions for live coding-agent execution.

This package defines how orchestrator/runtime code interacts with running agents:
addressing types for locating an agent process and agent interfaces for sending
kickoff instructions in a concrete execution environment.
"""

from agentrelay.agent.addressing import AgentAddress, TmuxAddress
from agentrelay.agent.agent import Agent, TmuxAgent

__all__ = [
    "Agent",
    "TmuxAgent",
    "AgentAddress",
    "TmuxAddress",
]
