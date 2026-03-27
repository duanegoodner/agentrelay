"""Null sandbox implementation — no isolation, pass-through.

This module provides :class:`NullSandbox`, the default sandbox that applies
no isolation. It satisfies the :class:`AgentSandbox` protocol with no-op
operations, preserving current host-execution behavior exactly.

Classes:
    NullSandbox: Pass-through sandbox with no isolation.
"""

from agentrelay.sandbox.core.config import SandboxContext


class NullSandbox:
    """Pass-through sandbox that applies no isolation.

    All methods are no-ops: ``wrap_command`` returns the command unchanged,
    and ``setup``/``teardown`` do nothing. This is the default sandbox for
    ``SandboxType.NONE``.
    """

    def wrap_command(self, cmd: str, _context: SandboxContext) -> str:
        """Return the command unchanged.

        Args:
            cmd: The raw agent command.
            _context: Execution context (unused).

        Returns:
            The original command string, unmodified.
        """
        return cmd

    def setup(self, _context: SandboxContext) -> None:
        """No-op setup.

        Args:
            _context: Execution context (unused).
        """

    def teardown(self, _context: SandboxContext) -> None:
        """No-op teardown.

        Args:
            _context: Execution context (unused).
        """
