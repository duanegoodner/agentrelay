"""OCI container sandbox — runs agents inside Docker/Podman containers.

This module provides :class:`OciSandbox`, which satisfies the
:class:`AgentSandbox` protocol by wrapping agent commands in
``docker run`` (or ``podman run``) with bind mounts, environment
variable injection, and network isolation.

Classes:
    OciSandbox: Container-based agent sandbox.
"""

from __future__ import annotations

import os
import subprocess

from agentrelay.ops import docker as docker_ops
from agentrelay.ops import git as git_ops
from agentrelay.sandbox.core.config import ContainerRuntime, SandboxContext

_DEFAULT_IMAGE = "agentrelay-agent-claude-code-python:latest"


class OciSandbox:
    """OCI container sandbox — wraps agent commands in ``docker run``.

    Mounts the git worktree, signal directory, and main ``.git/``
    directory into the container at their original absolute paths so
    that internal git references resolve without modification.

    Attributes:
        _image: Container image to use.
        _runtime: Container runtime binary name (``"docker"`` or
            ``"podman"``).
    """

    def __init__(
        self,
        image: str | None = None,
        runtime: ContainerRuntime | None = None,
    ) -> None:
        self._image = image or _DEFAULT_IMAGE
        self._runtime = (runtime or ContainerRuntime.DOCKER).value

    def setup(self, context: SandboxContext) -> None:
        """Validate runtime and network are available.

        Args:
            context: Execution context with graph name for network naming.

        Raises:
            RuntimeError: If the container runtime is not available or
                the Docker network does not exist.
        """
        if not docker_ops.is_available(self._runtime):
            raise RuntimeError(f"Container runtime '{self._runtime}' is not available")
        network = f"agentrelay-{context.graph_name}"
        if not docker_ops.network_exists(network, self._runtime):
            raise RuntimeError(
                f"Docker network '{network}' does not exist. "
                "Network must be created by run_graph before task execution."
            )

    def wrap_command(self, cmd: str, context: SandboxContext) -> str:
        """Wrap an agent command in ``docker run`` with bind mounts and env vars.

        Mounts:
            - worktree_path → worktree_path (read-write)
            - signal_dir → signal_dir (read-write)
            - main .git/ dir → same path (read-write, needed for commits)

        Args:
            cmd: The raw agent command to execute inside the container.
            context: Execution context with paths and environment.

        Returns:
            The full ``docker run ...`` command string.
        """
        git_dir = git_ops.worktree_git_dir(context.worktree_path)
        volumes: list[tuple[str, str] | tuple[str, str, str]] = [
            (str(context.worktree_path), str(context.worktree_path)),
            (str(context.signal_dir), str(context.signal_dir)),
            (str(git_dir), str(git_dir)),
        ]
        # Rename ANTHROPIC_API_KEY to _ANTHROPIC_API_KEY so Claude Code
        # doesn't detect it and show an interactive confirmation prompt.
        # The apiKeyHelper in settings.json echoes $_ANTHROPIC_API_KEY.
        renamed_vars = {}
        for key, value in context.env_vars.items():
            if key == "ANTHROPIC_API_KEY":
                renamed_vars["_ANTHROPIC_API_KEY"] = value
            else:
                renamed_vars[key] = value
        env_vars = {
            **renamed_vars,
            "IS_AI_AGENT": "true",
            "TERM": os.environ.get("TERM", "xterm-256color"),
            "DISABLE_AUTOUPDATER": "1",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        }
        # Seed Claude Code folder trust for the container workdir.
        # The trust-workdir script is baked into the framework image.
        full_cmd = f"claude-trust-workdir && {cmd}"
        return docker_ops.build_run_command(
            container_name=f"agentrelay-{context.graph_name}-{context.task_id}",
            image=self._image,
            cmd=full_cmd,
            volumes=volumes,
            env_vars=env_vars,
            labels={
                "agentrelay.graph": context.graph_name,
                "agentrelay.task": context.task_id,
            },
            network=f"agentrelay-{context.graph_name}",
            workdir=str(context.worktree_path),
            runtime=self._runtime,
        )

    def teardown(self, context: SandboxContext) -> None:
        """Stop and remove the container, swallowing errors if already gone.

        Args:
            context: Execution context with task ID for container naming.
        """
        name = f"agentrelay-{context.graph_name}-{context.task_id}"
        try:
            docker_ops.stop(name, self._runtime)
        except subprocess.CalledProcessError:
            pass
        try:
            docker_ops.rm(name, self._runtime)
        except subprocess.CalledProcessError:
            pass
