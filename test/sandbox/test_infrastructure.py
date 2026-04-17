"""Tests for SandboxInfrastructureManager protocol and implementations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentrelay.sandbox import (
    NullSandboxInfrastructureManager,
    OciSandboxInfrastructureManager,
    SandboxInfrastructureManager,
)

# --- NullSandboxInfrastructureManager ---


class TestNullSandboxInfrastructureManager:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(
            NullSandboxInfrastructureManager(), SandboxInfrastructureManager
        )

    def test_setup_is_noop(self) -> None:
        NullSandboxInfrastructureManager().setup()

    def test_teardown_is_noop(self) -> None:
        NullSandboxInfrastructureManager().teardown()


# --- OciSandboxInfrastructureManager ---


class TestOciSandboxInfrastructureManager:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(
            OciSandboxInfrastructureManager("g"), SandboxInfrastructureManager
        )

    def test_network_name(self) -> None:
        mgr = OciSandboxInfrastructureManager("my-graph")
        assert mgr._network_name == "agentrelay-my-graph"

    @patch("agentrelay.sandbox.implementations.oci_infrastructure.docker_ops")
    def test_setup_creates_network(self, mock_docker: MagicMock) -> None:
        mock_docker.is_available.return_value = True
        mock_docker.network_exists.return_value = False
        mgr = OciSandboxInfrastructureManager("g")
        mgr.setup()
        mock_docker.network_create.assert_called_once_with("agentrelay-g")

    @patch("agentrelay.sandbox.implementations.oci_infrastructure.docker_ops")
    def test_setup_skips_existing_network(self, mock_docker: MagicMock) -> None:
        mock_docker.is_available.return_value = True
        mock_docker.network_exists.return_value = True
        mgr = OciSandboxInfrastructureManager("g")
        mgr.setup()
        mock_docker.network_create.assert_not_called()

    @patch("agentrelay.sandbox.implementations.oci_infrastructure.docker_ops")
    def test_setup_raises_when_docker_unavailable(self, mock_docker: MagicMock) -> None:
        mock_docker.is_available.return_value = False
        mgr = OciSandboxInfrastructureManager("g")
        with pytest.raises(RuntimeError, match="not available"):
            mgr.setup()

    @patch("agentrelay.sandbox.implementations.oci_infrastructure.docker_ops")
    def test_teardown_removes_network(self, mock_docker: MagicMock) -> None:
        mgr = OciSandboxInfrastructureManager("g")
        mgr.teardown()
        mock_docker.network_remove.assert_called_once_with("agentrelay-g")

    @patch("agentrelay.sandbox.implementations.oci_infrastructure.docker_ops")
    def test_teardown_swallows_error(self, mock_docker: MagicMock) -> None:
        mock_docker.network_remove.side_effect = Exception("gone")
        mgr = OciSandboxInfrastructureManager("g")
        mgr.teardown()  # Should not raise
