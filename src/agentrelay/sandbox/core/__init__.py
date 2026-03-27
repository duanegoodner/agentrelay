"""Core sandbox configuration types and protocols.

This subpackage defines the sandbox data model (enums, config, context)
and the :class:`AgentSandbox` protocol that implementations must satisfy.
"""

from agentrelay.sandbox.core.config import (
    IsolationConfig,
    SandboxContext,
    SandboxType,
    TokenTier,
)
from agentrelay.sandbox.core.sandbox import AgentSandbox

__all__ = [
    "AgentSandbox",
    "IsolationConfig",
    "SandboxContext",
    "SandboxType",
    "TokenTier",
]
