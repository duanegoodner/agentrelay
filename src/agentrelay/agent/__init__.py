"""Agent package: addressing types and live agent implementations.

Public exports preserve the stable import surface:

- ``from agentrelay.agent import Agent, TmuxAgent``
- ``from agentrelay.agent import AgentAddress, TmuxAddress``
"""

from agentrelay.agent.addressing import AgentAddress, TmuxAddress
from agentrelay.agent.agent import Agent, TmuxAgent

__all__ = [
    "Agent",
    "TmuxAgent",
    "AgentAddress",
    "TmuxAddress",
]
