"""Tests for agentrelay.ops.docker — Docker subprocess wrappers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentrelay.ops.docker import (
    build_run_command,
    image_exists,
    is_available,
    network_create,
    network_exists,
    network_remove,
    rm,
    stop,
)

# ── is_available ──


class TestIsAvailable:
    """Tests for is_available."""

    @patch("agentrelay.ops.docker.subprocess.run")
    def test_returns_true_when_runtime_responds(self, mock_run: MagicMock) -> None:
        mock_run.return_value.returncode = 0
        assert is_available() is True
        mock_run.assert_called_once_with(["docker", "info"], capture_output=True)

    @patch("agentrelay.ops.docker.subprocess.run")
    def test_returns_false_when_runtime_unavailable(self, mock_run: MagicMock) -> None:
        mock_run.return_value.returncode = 1
        assert is_available() is False

    @patch("agentrelay.ops.docker.subprocess.run")
    def test_uses_custom_runtime(self, mock_run: MagicMock) -> None:
        mock_run.return_value.returncode = 0
        is_available(runtime="podman")
        mock_run.assert_called_once_with(["podman", "info"], capture_output=True)


# ── image_exists ──


class TestImageExists:
    """Tests for image_exists."""

    @patch("agentrelay.ops.docker.subprocess.run")
    def test_returns_true_when_image_exists(self, mock_run: MagicMock) -> None:
        mock_run.return_value.returncode = 0
        assert image_exists("myimage:latest") is True
        mock_run.assert_called_once_with(
            ["docker", "image", "inspect", "myimage:latest"], capture_output=True
        )

    @patch("agentrelay.ops.docker.subprocess.run")
    def test_returns_false_when_image_missing(self, mock_run: MagicMock) -> None:
        mock_run.return_value.returncode = 1
        assert image_exists("noimage") is False

    @patch("agentrelay.ops.docker.subprocess.run")
    def test_uses_custom_runtime(self, mock_run: MagicMock) -> None:
        mock_run.return_value.returncode = 0
        image_exists("img", runtime="podman")
        assert mock_run.call_args[0][0][0] == "podman"


# ── network_exists ──


class TestNetworkExists:
    """Tests for network_exists."""

    @patch("agentrelay.ops.docker.subprocess.run")
    def test_returns_true_when_exists(self, mock_run: MagicMock) -> None:
        mock_run.return_value.returncode = 0
        assert network_exists("mynet") is True
        mock_run.assert_called_once_with(
            ["docker", "network", "inspect", "mynet"], capture_output=True
        )

    @patch("agentrelay.ops.docker.subprocess.run")
    def test_returns_false_when_missing(self, mock_run: MagicMock) -> None:
        mock_run.return_value.returncode = 1
        assert network_exists("nonet") is False


# ── network_create / network_remove ──


class TestNetworkCreate:
    """Tests for network_create."""

    @patch("agentrelay.ops.docker.subprocess.run")
    def test_calls_network_create(self, mock_run: MagicMock) -> None:
        network_create("mynet")
        mock_run.assert_called_once_with(
            ["docker", "network", "create", "mynet"],
            check=True,
            capture_output=True,
        )

    @patch("agentrelay.ops.docker.subprocess.run")
    def test_uses_custom_runtime(self, mock_run: MagicMock) -> None:
        network_create("net", runtime="podman")
        assert mock_run.call_args[0][0][0] == "podman"


class TestNetworkRemove:
    """Tests for network_remove."""

    @patch("agentrelay.ops.docker.subprocess.run")
    def test_calls_network_rm(self, mock_run: MagicMock) -> None:
        network_remove("mynet")
        mock_run.assert_called_once_with(
            ["docker", "network", "rm", "mynet"],
            check=True,
            capture_output=True,
        )


# ── stop / rm ──


class TestStop:
    """Tests for stop."""

    @patch("agentrelay.ops.docker.subprocess.run")
    def test_calls_stop(self, mock_run: MagicMock) -> None:
        stop("mycontainer")
        mock_run.assert_called_once_with(
            ["docker", "stop", "mycontainer"],
            check=True,
            capture_output=True,
        )

    @patch("agentrelay.ops.docker.subprocess.run")
    def test_uses_custom_runtime(self, mock_run: MagicMock) -> None:
        stop("c", runtime="podman")
        assert mock_run.call_args[0][0][0] == "podman"


class TestRm:
    """Tests for rm."""

    @patch("agentrelay.ops.docker.subprocess.run")
    def test_calls_rm(self, mock_run: MagicMock) -> None:
        rm("mycontainer")
        mock_run.assert_called_once_with(
            ["docker", "rm", "mycontainer"],
            check=True,
            capture_output=True,
        )


# ── build_run_command ──


class TestBuildRunCommand:
    """Tests for build_run_command."""

    def test_minimal_command(self) -> None:
        result = build_run_command(
            container_name="test-ctr",
            image="myimage:latest",
            cmd="echo hello",
        )
        assert "docker run -it --rm --name test-ctr" in result
        assert "myimage:latest" in result
        assert result.endswith("'echo hello'")

    def test_volumes(self) -> None:
        result = build_run_command(
            container_name="ctr",
            image="img",
            cmd="cmd",
            volumes=[
                ("/host/a", "/container/a"),
                ("/host/b", "/container/b", "ro"),
            ],
        )
        assert "-v /host/a:/container/a" in result
        assert "-v /host/b:/container/b:ro" in result

    def test_env_vars(self) -> None:
        result = build_run_command(
            container_name="ctr",
            image="img",
            cmd="cmd",
            env_vars={"GH_TOKEN": "ghp_xxx", "KEY": "val"},
        )
        assert "-e GH_TOKEN=ghp_xxx" in result
        assert "-e KEY=val" in result

    def test_network(self) -> None:
        result = build_run_command(
            container_name="ctr",
            image="img",
            cmd="cmd",
            network="mynet",
        )
        assert "--network mynet" in result

    def test_workdir(self) -> None:
        result = build_run_command(
            container_name="ctr",
            image="img",
            cmd="cmd",
            workdir="/work/dir",
        )
        assert "-w /work/dir" in result

    def test_custom_runtime(self) -> None:
        result = build_run_command(
            container_name="ctr",
            image="img",
            cmd="cmd",
            runtime="podman",
        )
        assert result.startswith("podman run")

    def test_full_command(self) -> None:
        """Full command with all options produces correct structure."""
        result = build_run_command(
            container_name="agentrelay-task_1",
            image="agentrelay-agent:latest",
            cmd="claude --model opus --dangerously-skip-permissions",
            volumes=[
                ("/repo/wt", "/repo/wt"),
                ("/repo/signals", "/repo/signals"),
                ("/repo/.git", "/repo/.git", "ro"),
            ],
            env_vars={"GH_TOKEN": "ghp_xxx"},
            network="agentrelay-mygraph",
            workdir="/repo/wt",
        )
        # Verify ordering: runtime run flags, volumes, env, network, workdir, image, cmd
        assert result.startswith("docker run -it --rm --name agentrelay-task_1")
        assert "-v /repo/wt:/repo/wt" in result
        assert "-v /repo/.git:/repo/.git:ro" in result
        assert "-e GH_TOKEN=ghp_xxx" in result
        assert "--network agentrelay-mygraph" in result
        assert "-w /repo/wt" in result
        assert "agentrelay-agent:latest" in result

    def test_no_optional_args(self) -> None:
        """Command without optional args omits volume/env/network/workdir flags."""
        result = build_run_command(
            container_name="ctr",
            image="img",
            cmd="cmd",
        )
        assert "-v" not in result
        assert "-e" not in result
        assert "--network" not in result
        assert "-w" not in result
