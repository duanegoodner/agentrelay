"""Implementations of :class:`~agentrelay.task_runner.core.io.TaskLauncher`.

Classes:
    TmuxTaskLauncher: Launches a Claude Code agent in a tmux pane.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentrelay.agent import Agent, TmuxAgent
from agentrelay.sandbox import (
    AgentFrameworkAdapter,
    AgentSandbox,
    CredentialProvider,
    SandboxContext,
    TokenTier,
)
from agentrelay.task_runtime import TaskRuntime


@dataclass
class TmuxTaskLauncher:
    """Launch an agent in a tmux pane using a framework adapter and sandbox.

    Orchestrates the command-building pipeline: the adapter builds the
    framework-specific CLI command, the sandbox wraps it with isolation,
    and :meth:`TmuxAgent.from_config` sends the final command to a tmux pane.

    Attributes:
        adapter: Framework adapter that builds the raw CLI command.
        sandbox: Sandbox that wraps the command with isolation.
        credential_provider: Credential provider that resolves token tier
            to environment variables.
        repo_path: Path to the main repository.
        graph_name: Name of the task graph being executed.
    """

    adapter: AgentFrameworkAdapter
    sandbox: AgentSandbox
    credential_provider: CredentialProvider
    repo_path: Path
    graph_name: str

    def launch(self, runtime: TaskRuntime) -> Agent:
        """Launch and return the primary agent for this task runtime.

        Builds the agent command via the adapter, wraps it with the sandbox,
        and sends it to a new tmux pane.

        Args:
            runtime: Runtime envelope to launch against.  Must have
                ``state.worktree_path`` and ``state.signal_dir`` set
                (typically by a prior :class:`TaskPreparer` step).

        Returns:
            Agent: Live agent handle bound to this task.

        Raises:
            ValueError: If ``worktree_path`` or ``signal_dir`` are not set.
        """
        if runtime.state.worktree_path is None:
            raise ValueError("runtime.state.worktree_path must be set before launch")
        if runtime.state.signal_dir is None:
            raise ValueError("runtime.state.signal_dir must be set before launch")

        config = runtime.task.primary_agent
        cmd = self.adapter.build_command(config, runtime.state.signal_dir)

        isolation = config.isolation
        tier = isolation.token_tier if isolation is not None else TokenTier.STANDARD
        env_vars = self.credential_provider.resolve(tier)

        context = SandboxContext(
            worktree_path=runtime.state.worktree_path,
            signal_dir=runtime.state.signal_dir,
            repo_path=self.repo_path,
            task_id=runtime.task.id,
            graph_name=self.graph_name,
            attempt_num=runtime.state.attempt_num,
            env_vars=env_vars,
        )
        self.sandbox.setup(context)
        cmd = self.sandbox.wrap_command(cmd, context)

        runtime.artifacts.sandbox = self.sandbox
        runtime.artifacts.sandbox_context = context

        attempt = runtime.state.attempt_num
        return TmuxAgent.from_config(
            config=config,
            task_id=f"{self.graph_name}-{runtime.task.id}-{attempt}",
            worktree_path=runtime.state.worktree_path,
            cmd=cmd,
        )
