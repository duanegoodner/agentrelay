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
    worktree_path: Path | None = Path("/worktrees/demo/ws-1"),
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
    def test_delegates_to_agent_address_teardown(
        self,
        _mock_git: MagicMock,
    ) -> None:
        """Calls agent_address.teardown with signal_dir and keep_panes."""
        mock_address = MagicMock()
        teardown = WorktreeTaskTeardown(repo_path=Path("/repo"))
        runtime = _make_runtime()
        runtime.artifacts.agent_address = mock_address

        teardown.teardown(runtime)

        mock_address.teardown.assert_called_once_with(
            signal_dir=Path("/repo/.workflow/demo/signals/task_1/attempts/0"),
            keep_panes=False,
        )

    @patch("agentrelay.task_runner.implementations.task_teardown.git")
    def test_passes_keep_panes_flag(
        self,
        _mock_git: MagicMock,
    ) -> None:
        """Passes keep_panes=True through to agent_address.teardown."""
        mock_address = MagicMock()
        teardown = WorktreeTaskTeardown(repo_path=Path("/repo"), keep_panes=True)
        runtime = _make_runtime()
        runtime.artifacts.agent_address = mock_address

        teardown.teardown(runtime)

        mock_address.teardown.assert_called_once_with(
            signal_dir=Path("/repo/.workflow/demo/signals/task_1/attempts/0"),
            keep_panes=True,
        )

    @patch("agentrelay.task_runner.implementations.task_teardown.git")
    def test_deletes_branch(
        self,
        mock_git: MagicMock,
    ) -> None:
        """Deletes the task branch but does not remove the worktree."""
        teardown = WorktreeTaskTeardown(repo_path=Path("/repo"))
        runtime = _make_runtime()
        runtime.artifacts.agent_address = MagicMock()

        teardown.teardown(runtime)

        mock_git.branch_delete.assert_called_once_with(
            Path("/repo"), "agentrelay/demo/task_1"
        )
        mock_git.worktree_remove.assert_not_called()

    @patch("agentrelay.task_runner.implementations.task_teardown.git")
    def test_handles_missing_agent_address(
        self,
        mock_git: MagicMock,
    ) -> None:
        """Does not call teardown when agent_address is None."""
        teardown = WorktreeTaskTeardown(repo_path=Path("/repo"))
        runtime = _make_runtime(agent_address=None)

        teardown.teardown(runtime)

        mock_git.branch_delete.assert_called_once()

    @patch("agentrelay.task_runner.implementations.task_teardown.git")
    def test_handles_branch_delete_error_gracefully(
        self,
        mock_git: MagicMock,
    ) -> None:
        """Catches CalledProcessError from branch_delete without propagating."""
        mock_git.branch_delete.side_effect = subprocess.CalledProcessError(1, "git")
        teardown = WorktreeTaskTeardown(repo_path=Path("/repo"))
        runtime = _make_runtime()
        runtime.artifacts.agent_address = MagicMock()

        teardown.teardown(runtime)  # Should not raise

    @patch("agentrelay.task_runner.implementations.task_teardown.git")
    def test_calls_sandbox_teardown_when_present(
        self,
        _mock_git: MagicMock,
    ) -> None:
        """Calls sandbox.teardown with context when both are set."""
        mock_sandbox = MagicMock()
        mock_context = MagicMock()
        teardown = WorktreeTaskTeardown(repo_path=Path("/repo"))
        runtime = _make_runtime()
        runtime.artifacts.agent_address = MagicMock()
        runtime.artifacts.sandbox = mock_sandbox
        runtime.artifacts.sandbox_context = mock_context

        teardown.teardown(runtime)

        mock_sandbox.teardown.assert_called_once_with(mock_context)

    @patch("agentrelay.task_runner.implementations.task_teardown.git")
    def test_handles_missing_sandbox_gracefully(
        self,
        mock_git: MagicMock,
    ) -> None:
        """Does not error when sandbox is None."""
        teardown = WorktreeTaskTeardown(repo_path=Path("/repo"))
        runtime = _make_runtime()
        runtime.artifacts.agent_address = MagicMock()

        teardown.teardown(runtime)  # Should not raise

        mock_git.branch_delete.assert_called_once()

    @patch("agentrelay.task_runner.implementations.task_teardown.git")
    def test_sandbox_teardown_error_swallowed(
        self,
        mock_git: MagicMock,
    ) -> None:
        """Sandbox teardown errors are swallowed (best-effort)."""
        mock_sandbox = MagicMock()
        mock_sandbox.teardown.side_effect = RuntimeError("container gone")
        teardown = WorktreeTaskTeardown(repo_path=Path("/repo"))
        runtime = _make_runtime()
        runtime.artifacts.agent_address = MagicMock()
        runtime.artifacts.sandbox = mock_sandbox
        runtime.artifacts.sandbox_context = MagicMock()

        teardown.teardown(runtime)  # Should not raise

        # Branch delete still runs after sandbox teardown error
        mock_git.branch_delete.assert_called_once()

    def test_satisfies_task_teardown_protocol(self) -> None:
        """WorktreeTaskTeardown satisfies the TaskTeardown protocol."""
        teardown = WorktreeTaskTeardown(repo_path=Path("/repo"))
        assert isinstance(teardown, TaskTeardown)
