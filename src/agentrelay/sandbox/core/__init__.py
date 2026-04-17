"""Core sandbox configuration types and protocols.

This subpackage defines the sandbox data model (enums, config, context)
and the :class:`AgentSandbox`, :class:`AgentFrameworkAdapter`, and
:class:`CredentialProvider` protocols that implementations must satisfy.
"""

from agentrelay.sandbox.core.adapters import AgentFrameworkAdapter
from agentrelay.sandbox.core.config import (
    IsolationConfig,
    SandboxContext,
    SandboxType,
    TokenTier,
)
from agentrelay.sandbox.core.credentials import CredentialProvider
from agentrelay.sandbox.core.infrastructure import SandboxInfrastructureManager
from agentrelay.sandbox.core.sandbox import AgentSandbox

__all__ = [
    "AgentFrameworkAdapter",
    "AgentSandbox",
    "CredentialProvider",
    "IsolationConfig",
    "SandboxContext",
    "SandboxInfrastructureManager",
    "SandboxType",
    "TokenTier",
]
