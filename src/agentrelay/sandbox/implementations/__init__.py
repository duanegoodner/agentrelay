"""Concrete sandbox, adapter, and credential provider implementations.

This subpackage provides sandbox implementations that satisfy the
:class:`AgentSandbox` protocol, framework adapters that satisfy the
:class:`AgentFrameworkAdapter` protocol, and credential providers that
satisfy the :class:`CredentialProvider` protocol.
"""

from agentrelay.sandbox.implementations.claude_code_adapter import ClaudeCodeAdapter
from agentrelay.sandbox.implementations.file_credentials import FileCredentialProvider
from agentrelay.sandbox.implementations.null_credentials import NullCredentialProvider
from agentrelay.sandbox.implementations.null_sandbox import NullSandbox

__all__ = [
    "ClaudeCodeAdapter",
    "FileCredentialProvider",
    "NullCredentialProvider",
    "NullSandbox",
]
