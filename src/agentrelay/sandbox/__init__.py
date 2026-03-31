"""Sandbox configuration, protocols, and implementations for agent isolation.

This package defines tunable agent isolation infrastructure — sandbox types,
token permission tiers, isolation configuration, and the protocols that
sandbox and framework adapter implementations must satisfy.

Subpackages:
    core: Enums, config dataclasses, context, AgentSandbox,
        AgentFrameworkAdapter, and CredentialProvider protocols.
    implementations: Concrete implementations (NullSandbox, ClaudeCodeAdapter,
        NullCredentialProvider, FileCredentialProvider, etc.).
"""

from agentrelay.sandbox.core.adapters import AgentFrameworkAdapter
from agentrelay.sandbox.core.config import (
    AnthropicCredential,
    ContainerRuntime,
    CredentialType,
    IsolationConfig,
    SandboxContext,
    SandboxType,
    TokenTier,
)
from agentrelay.sandbox.core.credentials import CredentialProvider
from agentrelay.sandbox.core.sandbox import AgentSandbox
from agentrelay.sandbox.implementations.claude_code_adapter import ClaudeCodeAdapter
from agentrelay.sandbox.implementations.file_credentials import FileCredentialProvider
from agentrelay.sandbox.implementations.null_credentials import NullCredentialProvider
from agentrelay.sandbox.implementations.null_sandbox import NullSandbox
from agentrelay.sandbox.implementations.oci_sandbox import OciSandbox

__all__ = [
    "AgentFrameworkAdapter",
    "AgentSandbox",
    "AnthropicCredential",
    "ClaudeCodeAdapter",
    "ContainerRuntime",
    "CredentialProvider",
    "CredentialType",
    "FileCredentialProvider",
    "IsolationConfig",
    "NullCredentialProvider",
    "NullSandbox",
    "OciSandbox",
    "SandboxContext",
    "SandboxType",
    "TokenTier",
]
