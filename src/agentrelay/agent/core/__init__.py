"""Core agent abstractions — ABCs and protocols.

This subpackage defines the abstract interfaces for agents and their
addressing, independent of any concrete execution environment.
"""

from agentrelay.agent.core.addressing import AgentAddress
from agentrelay.agent.core.agent import Agent

__all__ = [
    "Agent",
    "AgentAddress",
]
