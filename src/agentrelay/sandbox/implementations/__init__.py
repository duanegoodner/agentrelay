"""Concrete sandbox and adapter implementations.

This subpackage provides sandbox implementations that satisfy the
:class:`AgentSandbox` protocol and framework adapters that satisfy the
:class:`AgentFrameworkAdapter` protocol.
"""

from agentrelay.sandbox.implementations.claude_code_adapter import ClaudeCodeAdapter
from agentrelay.sandbox.implementations.null_sandbox import NullSandbox

__all__ = ["ClaudeCodeAdapter", "NullSandbox"]
