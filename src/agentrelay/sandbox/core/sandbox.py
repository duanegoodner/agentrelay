"""Agent sandbox protocol for wrapping agent commands with isolation.

This module defines the :class:`AgentSandbox` protocol that all sandbox
implementations must satisfy. The protocol is runtime-checkable, so
``isinstance(obj, AgentSandbox)`` works at runtime.

Protocols:
    AgentSandbox: Wraps agent commands with sandbox isolation.
"""

from typing import Protocol, runtime_checkable

from agentrelay.sandbox.core.config import SandboxContext


@runtime_checkable
class AgentSandbox(Protocol):
    """Protocol for wrapping agent commands with sandbox isolation.

    Implementations control how an agent command is executed — directly
    on the host (NullSandbox), inside a container (OciSandbox), etc.

    Methods:
        wrap_command: Transform a raw agent command into a sandboxed command.
        setup: Perform any pre-launch setup (e.g., create Docker network).
        teardown: Clean up sandbox resources after agent completion.
    """

    def wrap_command(self, cmd: str, context: SandboxContext) -> str:
        """Wrap an agent command string with sandbox isolation.

        Args:
            cmd: The raw agent command to execute.
            context: Execution context with paths and environment.

        Returns:
            The wrapped command string ready for execution.
        """
        ...

    def setup(self, context: SandboxContext) -> None:
        """Perform pre-launch sandbox setup.

        Args:
            context: Execution context with paths and environment.
        """
        ...

    def teardown(self, context: SandboxContext) -> None:
        """Clean up sandbox resources after agent completion.

        Args:
            context: Execution context with paths and environment.
        """
        ...
