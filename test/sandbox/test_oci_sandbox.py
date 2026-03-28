"""Tests for OciSandbox implementation."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentrelay.sandbox import (
    AgentSandbox,
    ContainerRuntime,
    SandboxContext,
)
from agentrelay.sandbox.implementations.oci_sandbox import OciSandbox


def _make_context(**overrides: object) -> SandboxContext:
    defaults = dict(
        worktree_path=Path("/repo/.workflow/g/worktrees/task_a"),
        signal_dir=Path("/repo/.workflow/g/signals/task_a"),
        repo_path=Path("/repo"),
        task_id="task_a",
        graph_name="test-graph",
        env_vars={"GH_TOKEN": "ghp_xxx"},
    )
    defaults.update(overrides)
    return SandboxContext(**defaults)  # type: ignore[arg-type]


class TestOciSandboxProtocol:
    """Tests for OciSandbox protocol satisfaction."""

    def test_satisfies_agent_sandbox_protocol(self) -> None:
        assert isinstance(OciSandbox(), AgentSandbox)


class TestOciSandboxDefaults:
    """Tests for default image and runtime."""

    def test_default_image(self) -> None:
        sandbox = OciSandbox()
        assert sandbox._image == "agentrelay-agent:latest"

    def test_default_runtime(self) -> None:
        sandbox = OciSandbox()
        assert sandbox._runtime == "docker"

    def test_custom_image(self) -> None:
        sandbox = OciSandbox(image="custom:v1")
        assert sandbox._image == "custom:v1"

    def test_custom_runtime(self) -> None:
        sandbox = OciSandbox(runtime=ContainerRuntime.PODMAN)
        assert sandbox._runtime == "podman"


class TestOciSandboxSetup:
    """Tests for OciSandbox.setup."""

    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_creates_network_when_not_exists(self, mock_docker: MagicMock) -> None:
        mock_docker.is_available.return_value = True
        mock_docker.network_exists.return_value = False

        sandbox = OciSandbox()
        sandbox.setup(_make_context())

        mock_docker.is_available.assert_called_once_with("docker")
        mock_docker.network_exists.assert_called_once_with(
            "agentrelay-test-graph", "docker"
        )
        mock_docker.network_create.assert_called_once_with(
            "agentrelay-test-graph", "docker"
        )

    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_skips_network_create_when_exists(self, mock_docker: MagicMock) -> None:
        mock_docker.is_available.return_value = True
        mock_docker.network_exists.return_value = True

        sandbox = OciSandbox()
        sandbox.setup(_make_context())

        mock_docker.network_create.assert_not_called()

    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_raises_when_runtime_unavailable(self, mock_docker: MagicMock) -> None:
        mock_docker.is_available.return_value = False

        sandbox = OciSandbox()
        with pytest.raises(RuntimeError, match="not available"):
            sandbox.setup(_make_context())

    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_uses_custom_runtime(self, mock_docker: MagicMock) -> None:
        mock_docker.is_available.return_value = True
        mock_docker.network_exists.return_value = False

        sandbox = OciSandbox(runtime=ContainerRuntime.PODMAN)
        sandbox.setup(_make_context())

        mock_docker.is_available.assert_called_once_with("podman")
        mock_docker.network_create.assert_called_once_with(
            "agentrelay-test-graph", "podman"
        )


class TestOciSandboxWrapCommand:
    """Tests for OciSandbox.wrap_command."""

    @patch("agentrelay.sandbox.implementations.oci_sandbox.git_ops")
    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_builds_correct_docker_run(
        self, mock_docker: MagicMock, mock_git: MagicMock
    ) -> None:
        mock_git.worktree_git_dir.return_value = Path("/repo/.git")
        mock_docker.build_run_command.return_value = "docker run ..."

        sandbox = OciSandbox(image="myimage:v1")
        ctx = _make_context()
        result = sandbox.wrap_command("claude --model opus", ctx)

        assert result == "docker run ..."
        mock_git.worktree_git_dir.assert_called_once_with(ctx.worktree_path)
        mock_docker.build_run_command.assert_called_once_with(
            container_name="agentrelay-task_a",
            image="myimage:v1",
            cmd="claude --model opus",
            volumes=[
                (
                    str(ctx.worktree_path),
                    str(ctx.worktree_path),
                ),
                (
                    str(ctx.signal_dir),
                    str(ctx.signal_dir),
                ),
                ("/repo/.git", "/repo/.git", "ro"),
            ],
            env_vars={"GH_TOKEN": "ghp_xxx"},
            network="agentrelay-test-graph",
            workdir=str(ctx.worktree_path),
            runtime="docker",
        )

    @patch("agentrelay.sandbox.implementations.oci_sandbox.git_ops")
    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_uses_custom_runtime(
        self, mock_docker: MagicMock, mock_git: MagicMock
    ) -> None:
        mock_git.worktree_git_dir.return_value = Path("/repo/.git")
        mock_docker.build_run_command.return_value = "podman run ..."

        sandbox = OciSandbox(runtime=ContainerRuntime.PODMAN)
        sandbox.wrap_command("cmd", _make_context())

        assert mock_docker.build_run_command.call_args.kwargs["runtime"] == "podman"


class TestOciSandboxTeardown:
    """Tests for OciSandbox.teardown."""

    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_stops_and_removes_container(self, mock_docker: MagicMock) -> None:
        sandbox = OciSandbox()
        sandbox.teardown(_make_context())

        mock_docker.stop.assert_called_once_with("agentrelay-task_a", "docker")
        mock_docker.rm.assert_called_once_with("agentrelay-task_a", "docker")

    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_swallows_stop_error(self, mock_docker: MagicMock) -> None:
        """Still calls rm even if stop raises."""
        mock_docker.stop.side_effect = subprocess.CalledProcessError(1, "stop")

        sandbox = OciSandbox()
        sandbox.teardown(_make_context())

        mock_docker.rm.assert_called_once_with("agentrelay-task_a", "docker")

    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_swallows_rm_error(self, mock_docker: MagicMock) -> None:
        """Does not raise even if both stop and rm fail."""
        mock_docker.stop.side_effect = subprocess.CalledProcessError(1, "stop")
        mock_docker.rm.side_effect = subprocess.CalledProcessError(1, "rm")

        sandbox = OciSandbox()
        sandbox.teardown(_make_context())  # should not raise

    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_uses_custom_runtime(self, mock_docker: MagicMock) -> None:
        sandbox = OciSandbox(runtime=ContainerRuntime.PODMAN)
        sandbox.teardown(_make_context())

        mock_docker.stop.assert_called_once_with("agentrelay-task_a", "podman")
        mock_docker.rm.assert_called_once_with("agentrelay-task_a", "podman")
