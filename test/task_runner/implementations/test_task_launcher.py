"""Tests for TmuxTaskLauncher."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from agentrelay.agent import TmuxAddress, TmuxAgent
from agentrelay.sandbox import (
    ClaudeCodeAdapter,
    IsolationConfig,
    NullCredentialProvider,
    NullSandbox,
    SandboxContext,
    SandboxType,
    TokenTier,
)
from agentrelay.task import AgentConfig, AgentRole, Task, TmuxEnvironment
from agentrelay.task_runner.core.io import TaskLauncher
from agentrelay.task_runner.implementations.task_launcher import TmuxTaskLauncher
from agentrelay.task_runtime import TaskRuntime


def _make_runtime(
    task_id: str = "task_1",
    worktree_path: Path | None = Path("/repo/.workflow/demo/worktrees/task_1"),
    signal_dir: Path | None = Path("/repo/.workflow/demo/signals/task_1"),
) -> TaskRuntime:
    config = AgentConfig(
        model="claude-sonnet-4-6",
        environment=TmuxEnvironment(session="mysession"),
    )
    runtime = TaskRuntime(
        task=Task(id=task_id, role=AgentRole.GENERIC, primary_agent=config)
    )
    runtime.state.worktree_path = worktree_path
    runtime.state.signal_dir = signal_dir
    return runtime


def _make_launcher() -> TmuxTaskLauncher:
    return TmuxTaskLauncher(
        adapter=ClaudeCodeAdapter(),
        sandbox=NullSandbox(),
        credential_provider=NullCredentialProvider(),
        repo_path=Path("/repo"),
        graph_name="demo",
    )


class TestTmuxTaskLauncher:
    """Tests for TmuxTaskLauncher.launch."""

    @patch("agentrelay.task_runner.implementations.task_launcher.TmuxAgent.from_config")
    def test_delegates_to_tmux_agent_from_config(
        self, mock_from_config: MagicMock
    ) -> None:
        """Calls TmuxAgent.from_config with correct args from runtime."""
        expected_agent = TmuxAgent(
            _address=TmuxAddress(session="mysession", pane_id="%42")
        )
        mock_from_config.return_value = expected_agent

        runtime = _make_runtime()
        launcher = _make_launcher()
        agent = launcher.launch(runtime)

        assert agent is expected_agent
        mock_from_config.assert_called_once_with(
            config=runtime.task.primary_agent,
            task_id="demo-task_1-0",
            worktree_path=Path("/repo/.workflow/demo/worktrees/task_1"),
            cmd=(
                'AGENTRELAY_SIGNAL_DIR="/repo/.workflow/demo/signals/task_1"'
                " claude --model claude-sonnet-4-6"
                " --dangerously-skip-permissions"
            ),
        )

    def test_raises_when_worktree_path_is_none(self) -> None:
        """Raises ValueError if worktree_path is not set."""
        runtime = _make_runtime(worktree_path=None)
        launcher = _make_launcher()

        with pytest.raises(ValueError, match="worktree_path"):
            launcher.launch(runtime)

    def test_raises_when_signal_dir_is_none(self) -> None:
        """Raises ValueError if signal_dir is not set."""
        runtime = _make_runtime(signal_dir=None)
        launcher = _make_launcher()

        with pytest.raises(ValueError, match="signal_dir"):
            launcher.launch(runtime)

    def test_satisfies_task_launcher_protocol(self) -> None:
        """TmuxTaskLauncher satisfies the TaskLauncher protocol."""
        launcher = _make_launcher()
        assert isinstance(launcher, TaskLauncher)

    @patch("agentrelay.task_runner.implementations.task_launcher.TmuxAgent.from_config")
    def test_calls_adapter_build_command(self, mock_from_config: MagicMock) -> None:
        """Launcher calls adapter.build_command with config and signal_dir."""
        mock_from_config.return_value = TmuxAgent(
            _address=TmuxAddress(session="s", pane_id="%1")
        )
        mock_adapter = MagicMock()
        mock_adapter.build_command.return_value = "test-cmd"
        launcher = TmuxTaskLauncher(
            adapter=mock_adapter,
            sandbox=NullSandbox(),
            credential_provider=NullCredentialProvider(),
            repo_path=Path("/repo"),
            graph_name="demo",
        )
        runtime = _make_runtime()

        launcher.launch(runtime)

        mock_adapter.build_command.assert_called_once_with(
            runtime.task.primary_agent,
            Path("/repo/.workflow/demo/signals/task_1"),
        )

    @patch("agentrelay.task_runner.implementations.task_launcher.TmuxAgent.from_config")
    def test_calls_sandbox_setup_and_wrap(self, mock_from_config: MagicMock) -> None:
        """Launcher calls sandbox.setup then sandbox.wrap_command."""
        mock_from_config.return_value = TmuxAgent(
            _address=TmuxAddress(session="s", pane_id="%1")
        )
        mock_sandbox = MagicMock()
        mock_sandbox.wrap_command.return_value = "wrapped-cmd"
        launcher = TmuxTaskLauncher(
            adapter=ClaudeCodeAdapter(),
            sandbox=mock_sandbox,
            credential_provider=NullCredentialProvider(),
            repo_path=Path("/repo"),
            graph_name="demo",
        )
        runtime = _make_runtime()

        launcher.launch(runtime)

        expected_context = SandboxContext(
            worktree_path=Path("/repo/.workflow/demo/worktrees/task_1"),
            signal_dir=Path("/repo/.workflow/demo/signals/task_1"),
            repo_path=Path("/repo"),
            task_id="task_1",
            graph_name="demo",
        )
        mock_sandbox.setup.assert_called_once_with(expected_context)
        mock_sandbox.wrap_command.assert_called_once()
        # setup is called before wrap_command
        assert mock_sandbox.setup.call_args_list[0] == call(expected_context)

    @patch("agentrelay.task_runner.implementations.task_launcher.TmuxAgent.from_config")
    def test_passes_wrapped_command_to_from_config(
        self, mock_from_config: MagicMock
    ) -> None:
        """Launcher passes sandbox-wrapped command to TmuxAgent.from_config."""
        mock_from_config.return_value = TmuxAgent(
            _address=TmuxAddress(session="s", pane_id="%1")
        )
        mock_sandbox = MagicMock()
        mock_sandbox.wrap_command.return_value = "docker run ... claude ..."
        launcher = TmuxTaskLauncher(
            adapter=ClaudeCodeAdapter(),
            sandbox=mock_sandbox,
            credential_provider=NullCredentialProvider(),
            repo_path=Path("/repo"),
            graph_name="demo",
        )
        runtime = _make_runtime()

        launcher.launch(runtime)

        assert mock_from_config.call_args.kwargs["cmd"] == "docker run ... claude ..."

    @patch("agentrelay.task_runner.implementations.task_launcher.TmuxAgent.from_config")
    def test_resolves_credentials_with_default_tier(
        self, mock_from_config: MagicMock
    ) -> None:
        """Defaults to STANDARD tier when isolation is None."""
        mock_from_config.return_value = TmuxAgent(
            _address=TmuxAddress(session="s", pane_id="%1")
        )
        mock_credential_provider = MagicMock()
        mock_credential_provider.resolve.return_value = {}
        mock_sandbox = MagicMock()
        mock_sandbox.wrap_command.return_value = "cmd"
        launcher = TmuxTaskLauncher(
            adapter=ClaudeCodeAdapter(),
            sandbox=mock_sandbox,
            credential_provider=mock_credential_provider,
            repo_path=Path("/repo"),
            graph_name="demo",
        )
        runtime = _make_runtime()

        launcher.launch(runtime)

        mock_credential_provider.resolve.assert_called_once_with(TokenTier.STANDARD)

    @patch("agentrelay.task_runner.implementations.task_launcher.TmuxAgent.from_config")
    def test_uses_isolation_token_tier_when_present(
        self, mock_from_config: MagicMock
    ) -> None:
        """Uses isolation.token_tier for credential resolution when set."""
        mock_from_config.return_value = TmuxAgent(
            _address=TmuxAddress(session="s", pane_id="%1")
        )
        mock_credential_provider = MagicMock()
        mock_credential_provider.resolve.return_value = {"GH_TOKEN": "ghp_xxx"}
        mock_sandbox = MagicMock()
        mock_sandbox.wrap_command.return_value = "cmd"
        launcher = TmuxTaskLauncher(
            adapter=ClaudeCodeAdapter(),
            sandbox=mock_sandbox,
            credential_provider=mock_credential_provider,
            repo_path=Path("/repo"),
            graph_name="demo",
        )
        config = AgentConfig(
            model="claude-sonnet-4-6",
            environment=TmuxEnvironment(session="mysession"),
            isolation=IsolationConfig(
                sandbox_type=SandboxType.OCI,
                token_tier=TokenTier.ELEVATED,
            ),
        )
        runtime = TaskRuntime(
            task=Task(id="task_1", role=AgentRole.GENERIC, primary_agent=config)
        )
        runtime.state.worktree_path = Path("/repo/.workflow/demo/worktrees/task_1")
        runtime.state.signal_dir = Path("/repo/.workflow/demo/signals/task_1")

        launcher.launch(runtime)

        mock_credential_provider.resolve.assert_called_once_with(TokenTier.ELEVATED)
        ctx_arg = mock_sandbox.setup.call_args[0][0]
        assert ctx_arg.env_vars == {"GH_TOKEN": "ghp_xxx"}

    @patch("agentrelay.task_runner.implementations.task_launcher.TmuxAgent.from_config")
    def test_tmux_window_name_includes_attempt_num(
        self, mock_from_config: MagicMock
    ) -> None:
        """Tmux window name includes attempt number for retry visibility."""
        mock_from_config.return_value = TmuxAgent(
            _address=TmuxAddress(session="s", pane_id="%1")
        )
        runtime = _make_runtime()
        runtime.state.attempt_num = 2
        launcher = _make_launcher()

        launcher.launch(runtime)

        assert mock_from_config.call_args.kwargs["task_id"] == "demo-task_1-2"

    @patch("agentrelay.task_runner.implementations.task_launcher.TmuxAgent.from_config")
    def test_stores_sandbox_and_context_on_artifacts(
        self, mock_from_config: MagicMock
    ) -> None:
        """Launcher stores sandbox and context on runtime artifacts after launch."""
        mock_from_config.return_value = TmuxAgent(
            _address=TmuxAddress(session="s", pane_id="%1")
        )
        mock_sandbox = MagicMock()
        mock_sandbox.wrap_command.return_value = "wrapped-cmd"
        launcher = TmuxTaskLauncher(
            adapter=ClaudeCodeAdapter(),
            sandbox=mock_sandbox,
            credential_provider=NullCredentialProvider(),
            repo_path=Path("/repo"),
            graph_name="demo",
        )
        runtime = _make_runtime()

        launcher.launch(runtime)

        assert runtime.artifacts.sandbox is mock_sandbox
        assert runtime.artifacts.sandbox_context is not None
        assert runtime.artifacts.sandbox_context.task_id == "task_1"
        assert runtime.artifacts.sandbox_context.graph_name == "demo"
        assert runtime.artifacts.sandbox_context.attempt_num == 0

    @patch("agentrelay.task_runner.implementations.task_launcher.TmuxAgent.from_config")
    def test_sandbox_context_includes_attempt_num(
        self, mock_from_config: MagicMock
    ) -> None:
        """SandboxContext includes attempt_num from runtime state."""
        mock_from_config.return_value = TmuxAgent(
            _address=TmuxAddress(session="s", pane_id="%1")
        )
        mock_sandbox = MagicMock()
        mock_sandbox.wrap_command.return_value = "wrapped-cmd"
        launcher = TmuxTaskLauncher(
            adapter=ClaudeCodeAdapter(),
            sandbox=mock_sandbox,
            credential_provider=NullCredentialProvider(),
            repo_path=Path("/repo"),
            graph_name="demo",
        )
        runtime = _make_runtime()
        runtime.state.attempt_num = 3

        launcher.launch(runtime)

        assert runtime.artifacts.sandbox_context is not None
        assert runtime.artifacts.sandbox_context.attempt_num == 3
