"""Concrete sandbox implementations.

This subpackage provides sandbox implementations that satisfy the
:class:`AgentSandbox` protocol.
"""

from agentrelay.sandbox.implementations.null_sandbox import NullSandbox

__all__ = ["NullSandbox"]
