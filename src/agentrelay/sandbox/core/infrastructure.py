"""Sandbox infrastructure lifecycle protocol.

This module defines the ``SandboxInfrastructureManager`` protocol for
managing graph-level sandbox infrastructure (e.g., OCI network creation
and teardown).

Protocols:
    SandboxInfrastructureManager: Setup and teardown for sandbox
        infrastructure.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class SandboxInfrastructureManager(Protocol):
    """Protocol for managing graph-level sandbox infrastructure.

    Implementations handle the setup and teardown of infrastructure
    required by sandboxed agents — for example, creating and removing
    Docker networks for OCI-isolated tasks.

    The graph name (needed for network naming) is captured at
    construction time by the factory, keeping the protocol methods
    argument-free.

    Methods:
        setup: Provision infrastructure before orchestrator execution.
        teardown: Clean up infrastructure after orchestrator execution.
    """

    def setup(self) -> None:
        """Provision sandbox infrastructure.

        Raises:
            RuntimeError: If required infrastructure cannot be created.
        """
        ...

    def teardown(self) -> None:
        """Clean up sandbox infrastructure.

        Best-effort: implementations should swallow errors when
        resources are already removed.
        """
        ...
