"""Tests for WorktreeTaskTeardown."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from agentrelay.agent import TmuxAddress
from agentrelay.task import AgentRole, Task
from agentrelay.task_runner.core.io import TaskTeardown
from agentrelay.task_runner.implementations.task_teardown import (
    WorktreeTaskTeardown,
)
from agentrelay.task_runtime import TaskRuntime


def _make_runtime(
    worktree_path: Path | None = Path("/repo/.workflow/demo/worktrees/task_1"),
    branch_name: str | None = "agentrelay/demo/task_1",
    signal_dir: Path | None = Path("/repo/.workflow/demo/signals/task_1"),
    agent_address: TmuxAddress | None = TmuxAddress(session="s", pane_id="%42"),
) -> TaskRuntime:
    runtime = TaskRuntime(task=Task(id="task_1", role=AgentRole.GENERIC))
    runtime.state.worktree_path = worktree_path
    runtime.state.branch_name = branch_name
    runtime.state.signal_dir = signal_dir
    runtime.artifacts.agent_address = agent_address
    return runtime


class TestWorktreeTaskTeardown:
    """Tests for WorktreeTaskTeardown.teardown."""

    @patch("agentrelay.task_runner.implementations.task_teardown.git")
    @patch("agentrelay.task_runner.implementations.task_teardown.signals")
    @patch("agentrelay.task_runner.implementations.task_teardown.tmux")
    def test_captures_pane_log_and_writes_it(
        self,
        mock_tmux: MagicMock,
        mock_signals: MagicMock,
        _mock_git: MagicMock,
    ) -> None:
        """Captures pane scrollback and writes agent.log."""
        mock_tmux.capture_pane.return_value = "pane output\n"
        teardown = WorktreeTaskTeardown(repo_path=Path("/repo"))
        runtime = _make_runtime()

        teardown.teardown(runtime)

        mock_tmux.capture_pane.assert_called_once_with("%42", full_history=True)
        mock_signals.write_text.assert_called_once_with(
            Path("/repo/.workflow/demo/signals/task_1"), "agent.log", "pane output\n"
        )

    @patch("agentrelay.task_runner.implementations.task_teardown.git")
    @patch("agentrelay.task_runner.implementations.task_teardown.signals")
    @patch("agentrelay.task_runner.implementations.task_teardown.tmux")
    def test_kills_window_by_default(
        self,
        mock_tmux: MagicMock,
        _mock_signals: MagicMock,
        _mock_git: MagicMock,
    ) -> None:
        """Kills the tmux window when keep_panes=False."""
        mock_tmux.capture_pane.return_value = ""
        teardown = WorktreeTaskTeardown(repo_path=Path("/repo"))
        runtime = _make_runtime()

        teardown.teardown(runtime)

        mock_tmux.kill_window.assert_called_once_with("%42")

    @patch("agentrelay.task_runner.implementations.task_teardown.git")
    @patch("agentrelay.task_runner.implementations.task_teardown.signals")
    @patch("agentrelay.task_runner.implementations.task_teardown.tmux")
    def test_keeps_panes_when_flag_set(
        self,
        mock_tmux: MagicMock,
        _mock_signals: MagicMock,
        _mock_git: MagicMock,
    ) -> None:
        """Does not kill the tmux window when keep_panes=True."""
        mock_tmux.capture_pane.return_value = ""
        teardown = WorktreeTaskTeardown(repo_path=Path("/repo"), keep_panes=True)
        runtime = _make_runtime()

        teardown.teardown(runtime)

        mock_tmux.kill_window.assert_not_called()

    @patch("agentrelay.task_runner.implementations.task_teardown.git")
    @patch("agentrelay.task_runner.implementations.task_teardown.signals")
    @patch("agentrelay.task_runner.implementations.task_teardown.tmux")
    def test_removes_worktree_and_deletes_branch(
        self,
        mock_tmux: MagicMock,
        _mock_signals: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """Removes worktree and deletes branch."""
        mock_tmux.capture_pane.return_value = ""
        teardown = WorktreeTaskTeardown(repo_path=Path("/repo"))
        runtime = _make_runtime()

        teardown.teardown(runtime)

        mock_git.worktree_remove.assert_called_once_with(
            Path("/repo"), Path("/repo/.workflow/demo/worktrees/task_1")
        )
        mock_git.branch_delete.assert_called_once_with(
            Path("/repo"), "agentrelay/demo/task_1"
        )

    @patch("agentrelay.task_runner.implementations.task_teardown.git")
    @patch("agentrelay.task_runner.implementations.task_teardown.signals")
    @patch("agentrelay.task_runner.implementations.task_teardown.tmux")
    def test_handles_missing_agent_address(
        self,
        _mock_tmux: MagicMock,
        _mock_signals: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """Does not try to capture pane when agent_address is None."""
        teardown = WorktreeTaskTeardown(repo_path=Path("/repo"))
        runtime = _make_runtime(agent_address=None)

        teardown.teardown(runtime)

        _mock_tmux.capture_pane.assert_not_called()
        _mock_tmux.kill_window.assert_not_called()
        mock_git.worktree_remove.assert_called_once()

    @patch("agentrelay.task_runner.implementations.task_teardown.git")
    @patch("agentrelay.task_runner.implementations.task_teardown.signals")
    @patch("agentrelay.task_runner.implementations.task_teardown.tmux")
    def test_handles_capture_pane_error_gracefully(
        self,
        mock_tmux: MagicMock,
        _mock_signals: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """Catches CalledProcessError from capture_pane without propagating."""
        mock_tmux.capture_pane.side_effect = subprocess.CalledProcessError(1, "tmux")
        teardown = WorktreeTaskTeardown(repo_path=Path("/repo"))
        runtime = _make_runtime()

        teardown.teardown(runtime)  # Should not raise

        mock_git.worktree_remove.assert_called_once()

    def test_satisfies_task_teardown_protocol(self) -> None:
        """WorktreeTaskTeardown satisfies the TaskTeardown protocol."""
        teardown = WorktreeTaskTeardown(repo_path=Path("/repo"))
        assert isinstance(teardown, TaskTeardown)
