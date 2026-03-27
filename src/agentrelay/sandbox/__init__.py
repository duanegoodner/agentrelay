"""Sandbox configuration, protocols, and implementations for agent isolation.

This package defines tunable agent isolation infrastructure — sandbox types,
token permission tiers, isolation configuration, and the protocols that
sandbox and framework adapter implementations must satisfy.

Subpackages:
    core: Enums, config dataclasses, context, AgentSandbox and
        AgentFrameworkAdapter protocols.
    implementations: Concrete implementations (NullSandbox, ClaudeCodeAdapter,
        etc.).
"""

from agentrelay.sandbox.core.adapters import AgentFrameworkAdapter
from agentrelay.sandbox.core.config import (
    IsolationConfig,
    SandboxContext,
    SandboxType,
    TokenTier,
)
from agentrelay.sandbox.core.sandbox import AgentSandbox
from agentrelay.sandbox.implementations.claude_code_adapter import ClaudeCodeAdapter
from agentrelay.sandbox.implementations.null_sandbox import NullSandbox

__all__ = [
    "AgentFrameworkAdapter",
    "AgentSandbox",
    "ClaudeCodeAdapter",
    "IsolationConfig",
    "NullSandbox",
    "SandboxContext",
    "SandboxType",
    "TokenTier",
]
