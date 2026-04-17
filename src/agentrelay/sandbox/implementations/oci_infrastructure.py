"""OCI sandbox infrastructure manager — Docker network lifecycle.

This module provides ``OciSandboxInfrastructureManager``, which manages
Docker network creation and teardown for graphs using OCI sandbox
isolation.

Classes:
    OciSandboxInfrastructureManager: Docker network setup and teardown.
"""

from agentrelay.ops import docker as docker_ops


class OciSandboxInfrastructureManager:
    """Docker network lifecycle manager for OCI-sandboxed graphs.

    Creates a Docker network named ``agentrelay-<graph_name>`` on
    ``setup()`` and removes it on ``teardown()``.

    Args:
        graph_name: Name of the graph (used for network naming).
    """

    def __init__(self, graph_name: str) -> None:
        self._network_name = f"agentrelay-{graph_name}"

    def setup(self) -> None:
        """Create the Docker network if it does not already exist.

        Raises:
            RuntimeError: If Docker is not available.
        """
        if not docker_ops.is_available():
            raise RuntimeError(
                "Docker is required for OCI sandbox but is not available"
            )
        if not docker_ops.network_exists(self._network_name):
            docker_ops.network_create(self._network_name)

    def teardown(self) -> None:
        """Remove the Docker network (best-effort)."""
        try:
            docker_ops.network_remove(self._network_name)
        except Exception:
            pass  # Best-effort cleanup
