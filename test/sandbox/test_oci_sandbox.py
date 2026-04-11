"""Tests for OciSandbox implementation."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentrelay.sandbox import (
    AgentSandbox,
    AnthropicCredential,
    ContainerRuntime,
    CredentialType,
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
        assert sandbox._image == "agentrelay-agent-claude-code-python:latest"

    def test_default_runtime(self) -> None:
        sandbox = OciSandbox()
        assert sandbox._runtime == "docker"

    def test_custom_image(self) -> None:
        sandbox = OciSandbox(image="custom:v1")
        assert sandbox._image == "custom:v1"

    def test_custom_runtime(self) -> None:
        sandbox = OciSandbox(runtime=ContainerRuntime.PODMAN)
        assert sandbox._runtime == "podman"

    def test_default_anthropic_credential_is_none(self) -> None:
        sandbox = OciSandbox()
        assert sandbox._anthropic_credential is None


class TestOciSandboxSetup:
    """Tests for OciSandbox.setup."""

    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_raises_when_network_not_exists(self, mock_docker: MagicMock) -> None:
        mock_docker.is_available.return_value = True
        mock_docker.network_exists.return_value = False

        sandbox = OciSandbox()
        with pytest.raises(RuntimeError, match="does not exist"):
            sandbox.setup(_make_context())

        mock_docker.is_available.assert_called_once_with("docker")
        mock_docker.network_exists.assert_called_once_with(
            "agentrelay-test-graph", "docker"
        )
        mock_docker.network_create.assert_not_called()

    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_succeeds_when_network_exists(self, mock_docker: MagicMock) -> None:
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
        mock_docker.network_exists.return_value = True

        sandbox = OciSandbox(runtime=ContainerRuntime.PODMAN)
        sandbox.setup(_make_context())

        mock_docker.is_available.assert_called_once_with("podman")
        mock_docker.network_exists.assert_called_once_with(
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
            container_name="agentrelay-test-graph-task_a-0",
            image="myimage:v1",
            cmd="claude-setup-credentials && claude-trust-workdir && claude --model opus",
            volumes=[
                (
                    str(ctx.worktree_path),
                    str(ctx.worktree_path),
                ),
                (
                    str(ctx.signal_dir),
                    str(ctx.signal_dir),
                ),
                ("/repo/.git", "/repo/.git"),
                ("/repo/.workflow/test-graph", "/repo/.workflow/test-graph", "ro"),
            ],
            env_vars={
                "GH_TOKEN": "ghp_xxx",
                "IS_AI_AGENT": "true",
                "TERM": os.environ.get("TERM", "xterm-256color"),
                "DISABLE_AUTOUPDATER": "1",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            },
            labels={
                "agentrelay.graph": "test-graph",
                "agentrelay.task": "task_a",
            },
            network="agentrelay-test-graph",
            workdir=str(ctx.worktree_path),
            runtime="docker",
        )

    @patch("agentrelay.sandbox.implementations.oci_sandbox.git_ops")
    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_injects_is_ai_agent_env_var(
        self, mock_docker: MagicMock, mock_git: MagicMock
    ) -> None:
        """IS_AI_AGENT=true is injected into container env vars."""
        mock_git.worktree_git_dir.return_value = Path("/repo/.git")
        mock_docker.build_run_command.return_value = "docker run ..."

        sandbox = OciSandbox()
        sandbox.wrap_command("claude", _make_context())

        call_kwargs = mock_docker.build_run_command.call_args.kwargs
        assert call_kwargs["env_vars"]["IS_AI_AGENT"] == "true"

    @patch("agentrelay.sandbox.implementations.oci_sandbox.git_ops")
    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_preserves_existing_env_vars_with_is_ai_agent(
        self, mock_docker: MagicMock, mock_git: MagicMock
    ) -> None:
        """IS_AI_AGENT is added alongside existing env vars."""
        mock_git.worktree_git_dir.return_value = Path("/repo/.git")
        mock_docker.build_run_command.return_value = "docker run ..."

        sandbox = OciSandbox()
        sandbox.wrap_command("claude", _make_context(env_vars={"MY_VAR": "val"}))

        call_kwargs = mock_docker.build_run_command.call_args.kwargs
        assert call_kwargs["env_vars"]["MY_VAR"] == "val"
        assert call_kwargs["env_vars"]["IS_AI_AGENT"] == "true"

    @patch("agentrelay.sandbox.implementations.oci_sandbox.git_ops")
    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_rejects_anthropic_api_key_in_env_vars(
        self, mock_docker: MagicMock, mock_git: MagicMock
    ) -> None:
        """ANTHROPIC_API_KEY in env_vars raises ValueError."""
        mock_git.worktree_git_dir.return_value = Path("/repo/.git")

        sandbox = OciSandbox()
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY must not be"):
            sandbox.wrap_command(
                "claude",
                _make_context(
                    env_vars={"ANTHROPIC_API_KEY": "sk-xxx", "GH_TOKEN": "ghp_xxx"}
                ),
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

    @patch("agentrelay.sandbox.implementations.oci_sandbox.git_ops")
    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_mounts_workflow_dir_read_only(
        self, mock_docker: MagicMock, mock_git: MagicMock
    ) -> None:
        """Workflow directory is mounted read-only for graph awareness."""
        mock_git.worktree_git_dir.return_value = Path("/repo/.git")
        mock_docker.build_run_command.return_value = "docker run ..."

        sandbox = OciSandbox()
        ctx = _make_context()
        sandbox.wrap_command("claude", ctx)

        call_kwargs = mock_docker.build_run_command.call_args.kwargs
        expected_workflow_dir = str(ctx.repo_path / ".workflow" / ctx.graph_name)
        assert (expected_workflow_dir, expected_workflow_dir, "ro") in call_kwargs[
            "volumes"
        ]

    @patch("agentrelay.sandbox.implementations.oci_sandbox.git_ops")
    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_container_name_includes_attempt_num(
        self, mock_docker: MagicMock, mock_git: MagicMock
    ) -> None:
        """Container name includes attempt number for retry uniqueness."""
        mock_git.worktree_git_dir.return_value = Path("/repo/.git")
        mock_docker.build_run_command.return_value = "docker run ..."

        sandbox = OciSandbox()
        sandbox.wrap_command("claude", _make_context(attempt_num=2))

        call_kwargs = mock_docker.build_run_command.call_args.kwargs
        assert call_kwargs["container_name"] == "agentrelay-test-graph-task_a-2"


class TestOciSandboxAnthropicCredential:
    """Tests for Anthropic credential injection."""

    @patch("agentrelay.sandbox.implementations.oci_sandbox.git_ops")
    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_api_key_credential_injects_env_var(
        self, mock_docker: MagicMock, mock_git: MagicMock
    ) -> None:
        """API_KEY credential injects _ANTHROPIC_API_KEY into env vars."""
        mock_git.worktree_git_dir.return_value = Path("/repo/.git")
        mock_docker.build_run_command.return_value = "docker run ..."

        cred = AnthropicCredential(
            name="test", credential_type=CredentialType.API_KEY, api_key="sk-test"
        )
        sandbox = OciSandbox(anthropic_credential=cred)
        sandbox.wrap_command("claude", _make_context())

        call_kwargs = mock_docker.build_run_command.call_args.kwargs
        assert call_kwargs["env_vars"]["_ANTHROPIC_API_KEY"] == "sk-test"
        # No OAuth mount (4 = worktree + signal_dir + git + workflow_dir)
        assert len(call_kwargs["volumes"]) == 4

    @patch("agentrelay.sandbox.implementations.oci_sandbox.git_ops")
    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_oauth_credential_mounts_file(
        self, mock_docker: MagicMock, mock_git: MagicMock
    ) -> None:
        """OAUTH credential mounts the credentials file read-only."""
        mock_git.worktree_git_dir.return_value = Path("/repo/.git")
        mock_docker.build_run_command.return_value = "docker run ..."

        creds_path = Path("/host/.claude/.credentials.json")
        cred = AnthropicCredential(
            name="max", credential_type=CredentialType.OAUTH, oauth_path=creds_path
        )
        sandbox = OciSandbox(anthropic_credential=cred)
        sandbox.wrap_command("claude", _make_context())

        call_kwargs = mock_docker.build_run_command.call_args.kwargs
        volumes = call_kwargs["volumes"]
        assert (str(creds_path), "/tmp/.claude-credentials.json", "ro") in volumes
        # No _ANTHROPIC_API_KEY injected
        assert "_ANTHROPIC_API_KEY" not in call_kwargs["env_vars"]

    @patch("agentrelay.sandbox.implementations.oci_sandbox.git_ops")
    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_no_credential_no_api_key_no_mount(
        self, mock_docker: MagicMock, mock_git: MagicMock
    ) -> None:
        """Without credential, no _ANTHROPIC_API_KEY and no extra mount."""
        mock_git.worktree_git_dir.return_value = Path("/repo/.git")
        mock_docker.build_run_command.return_value = "docker run ..."

        sandbox = OciSandbox()
        sandbox.wrap_command("claude", _make_context())

        call_kwargs = mock_docker.build_run_command.call_args.kwargs
        assert "_ANTHROPIC_API_KEY" not in call_kwargs["env_vars"]
        # 4 = worktree + signal_dir + git + workflow_dir (no OAuth mount)
        assert len(call_kwargs["volumes"]) == 4

    @patch("agentrelay.sandbox.implementations.oci_sandbox.git_ops")
    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_startup_chain_includes_setup_credentials(
        self, mock_docker: MagicMock, mock_git: MagicMock
    ) -> None:
        """Command prefix includes claude-setup-credentials before trust-workdir."""
        mock_git.worktree_git_dir.return_value = Path("/repo/.git")
        mock_docker.build_run_command.return_value = "docker run ..."

        sandbox = OciSandbox()
        sandbox.wrap_command("claude --model opus", _make_context())

        call_kwargs = mock_docker.build_run_command.call_args.kwargs
        assert call_kwargs["cmd"] == (
            "claude-setup-credentials && claude-trust-workdir && claude --model opus"
        )


class TestOciSandboxTeardown:
    """Tests for OciSandbox.teardown."""

    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_stops_and_removes_container(self, mock_docker: MagicMock) -> None:
        sandbox = OciSandbox()
        sandbox.teardown(_make_context())

        mock_docker.stop.assert_called_once_with(
            "agentrelay-test-graph-task_a-0", "docker"
        )
        mock_docker.rm.assert_called_once_with(
            "agentrelay-test-graph-task_a-0", "docker"
        )

    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_swallows_stop_error(self, mock_docker: MagicMock) -> None:
        """Still calls rm even if stop raises."""
        mock_docker.stop.side_effect = subprocess.CalledProcessError(1, "stop")

        sandbox = OciSandbox()
        sandbox.teardown(_make_context())

        mock_docker.rm.assert_called_once_with(
            "agentrelay-test-graph-task_a-0", "docker"
        )

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

        mock_docker.stop.assert_called_once_with(
            "agentrelay-test-graph-task_a-0", "podman"
        )
        mock_docker.rm.assert_called_once_with(
            "agentrelay-test-graph-task_a-0", "podman"
        )

    @patch("agentrelay.sandbox.implementations.oci_sandbox.docker_ops")
    def test_container_name_includes_attempt_num(self, mock_docker: MagicMock) -> None:
        """Container name includes attempt number for retry uniqueness."""
        sandbox = OciSandbox()
        sandbox.teardown(_make_context(attempt_num=3))

        mock_docker.stop.assert_called_once_with(
            "agentrelay-test-graph-task_a-3", "docker"
        )
        mock_docker.rm.assert_called_once_with(
            "agentrelay-test-graph-task_a-3", "docker"
        )
