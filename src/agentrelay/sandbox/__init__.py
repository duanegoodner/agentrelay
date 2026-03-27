"""Sandbox configuration, protocols, and implementations for agent isolation.

This package defines tunable agent isolation infrastructure — sandbox types,
token permission tiers, isolation configuration, and the protocol that
sandbox implementations must satisfy.

Subpackages:
    core: Enums, config dataclasses, context, and the AgentSandbox protocol.
    implementations: Concrete sandbox implementations (NullSandbox, etc.).
"""

from agentrelay.sandbox.core.config import (
    IsolationConfig,
    SandboxContext,
    SandboxType,
    TokenTier,
)
from agentrelay.sandbox.core.sandbox import AgentSandbox
from agentrelay.sandbox.implementations.null_sandbox import NullSandbox

__all__ = [
    "AgentSandbox",
    "IsolationConfig",
    "NullSandbox",
    "SandboxContext",
    "SandboxType",
    "TokenTier",
]
