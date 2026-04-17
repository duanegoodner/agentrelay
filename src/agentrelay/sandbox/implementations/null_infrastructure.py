"""Null sandbox infrastructure manager — no-op for non-OCI graphs.

This module provides :class:`NullSandboxInfrastructureManager`, a no-op
implementation for graphs that do not use OCI sandbox isolation.

Classes:
    NullSandboxInfrastructureManager: No-op infrastructure manager.
"""


class NullSandboxInfrastructureManager:
    """No-op infrastructure manager for graphs without OCI tasks.

    Both :meth:`setup` and :meth:`teardown` are no-ops.
    """

    def setup(self) -> None:
        """No-op setup."""

    def teardown(self) -> None:
        """No-op teardown."""
