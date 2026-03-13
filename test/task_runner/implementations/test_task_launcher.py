"""Tests for TmuxTaskLauncher."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentrelay.agent import TmuxAddress, TmuxAgent
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
        launcher = TmuxTaskLauncher()
        agent = launcher.launch(runtime)

        assert agent is expected_agent
        mock_from_config.assert_called_once_with(
            config=runtime.task.primary_agent,
            task_id="task_1",
            worktree_path=Path("/repo/.workflow/demo/worktrees/task_1"),
            signal_dir=Path("/repo/.workflow/demo/signals/task_1"),
        )

    def test_raises_when_worktree_path_is_none(self) -> None:
        """Raises ValueError if worktree_path is not set."""
        runtime = _make_runtime(worktree_path=None)
        launcher = TmuxTaskLauncher()

        with pytest.raises(ValueError, match="worktree_path"):
            launcher.launch(runtime)

    def test_raises_when_signal_dir_is_none(self) -> None:
        """Raises ValueError if signal_dir is not set."""
        runtime = _make_runtime(signal_dir=None)
        launcher = TmuxTaskLauncher()

        with pytest.raises(ValueError, match="signal_dir"):
            launcher.launch(runtime)

    def test_satisfies_task_launcher_protocol(self) -> None:
        """TmuxTaskLauncher satisfies the TaskLauncher protocol."""
        launcher = TmuxTaskLauncher()
        assert isinstance(launcher, TaskLauncher)
