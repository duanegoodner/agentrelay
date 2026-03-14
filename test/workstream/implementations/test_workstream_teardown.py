"""Tests for GitWorkstreamTeardown."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from agentrelay.workstream.core.io import WorkstreamTeardown
from agentrelay.workstream.core.runtime import WorkstreamRuntime
from agentrelay.workstream.core.workstream import WorkstreamSpec
from agentrelay.workstream.implementations.workstream_teardown import (
    GitWorkstreamTeardown,
)


def _make_runtime(
    worktree_path: Path | None = Path("/repo/.worktrees/demo/ws-1"),
    branch_name: str | None = "agentrelay/demo/ws-1/integration",
) -> WorkstreamRuntime:
    runtime = WorkstreamRuntime(spec=WorkstreamSpec(id="ws-1"))
    runtime.state.worktree_path = worktree_path
    runtime.state.branch_name = branch_name
    return runtime


class TestGitWorkstreamTeardown:
    """Tests for GitWorkstreamTeardown.teardown_workstream."""

    @patch("agentrelay.workstream.implementations.workstream_teardown.git")
    def test_removes_worktree(
        self,
        mock_git: MagicMock,
    ) -> None:
        """Removes the worktree via git.worktree_remove."""
        teardown = GitWorkstreamTeardown(repo_path=Path("/repo"))
        runtime = _make_runtime()

        teardown.teardown_workstream(runtime)

        mock_git.worktree_remove.assert_called_once_with(
            Path("/repo"),
            Path("/repo/.worktrees/demo/ws-1"),
        )

    @patch("agentrelay.workstream.implementations.workstream_teardown.git")
    def test_deletes_local_branch(
        self,
        mock_git: MagicMock,
    ) -> None:
        """Deletes the local integration branch."""
        teardown = GitWorkstreamTeardown(repo_path=Path("/repo"))
        runtime = _make_runtime()

        teardown.teardown_workstream(runtime)

        mock_git.branch_delete.assert_called_once_with(
            Path("/repo"),
            "agentrelay/demo/ws-1/integration",
        )

    @patch("agentrelay.workstream.implementations.workstream_teardown.git")
    def test_deletes_remote_branch(
        self,
        mock_git: MagicMock,
    ) -> None:
        """Deletes the remote integration branch."""
        teardown = GitWorkstreamTeardown(repo_path=Path("/repo"))
        runtime = _make_runtime()

        teardown.teardown_workstream(runtime)

        mock_git.push_delete_branch.assert_called_once_with(
            Path("/repo"),
            "agentrelay/demo/ws-1/integration",
        )

    @patch("agentrelay.workstream.implementations.workstream_teardown.git")
    def test_skips_worktree_remove_when_path_is_none(
        self,
        mock_git: MagicMock,
    ) -> None:
        """Does not call worktree_remove when worktree_path is None."""
        teardown = GitWorkstreamTeardown(repo_path=Path("/repo"))
        runtime = _make_runtime(worktree_path=None)

        teardown.teardown_workstream(runtime)

        mock_git.worktree_remove.assert_not_called()
        mock_git.branch_delete.assert_called_once()

    @patch("agentrelay.workstream.implementations.workstream_teardown.git")
    def test_skips_branch_ops_when_branch_name_is_none(
        self,
        mock_git: MagicMock,
    ) -> None:
        """Does not call branch_delete or push_delete_branch when branch_name is None."""
        teardown = GitWorkstreamTeardown(repo_path=Path("/repo"))
        runtime = _make_runtime(branch_name=None)

        teardown.teardown_workstream(runtime)

        mock_git.worktree_remove.assert_called_once()
        mock_git.branch_delete.assert_not_called()
        mock_git.push_delete_branch.assert_not_called()

    @patch("agentrelay.workstream.implementations.workstream_teardown.git")
    def test_handles_worktree_remove_error_gracefully(
        self,
        mock_git: MagicMock,
    ) -> None:
        """Catches CalledProcessError from worktree_remove without propagating."""
        mock_git.worktree_remove.side_effect = subprocess.CalledProcessError(
            1, "git worktree remove"
        )
        teardown = GitWorkstreamTeardown(repo_path=Path("/repo"))
        runtime = _make_runtime()

        teardown.teardown_workstream(runtime)  # Should not raise

        mock_git.branch_delete.assert_called_once()

    @patch("agentrelay.workstream.implementations.workstream_teardown.git")
    def test_handles_branch_delete_error_gracefully(
        self,
        mock_git: MagicMock,
    ) -> None:
        """Catches CalledProcessError from branch_delete without propagating."""
        mock_git.branch_delete.side_effect = subprocess.CalledProcessError(
            1, "git branch -D"
        )
        teardown = GitWorkstreamTeardown(repo_path=Path("/repo"))
        runtime = _make_runtime()

        teardown.teardown_workstream(runtime)  # Should not raise

        mock_git.push_delete_branch.assert_called_once()

    @patch("agentrelay.workstream.implementations.workstream_teardown.git")
    def test_handles_push_delete_error_gracefully(
        self,
        mock_git: MagicMock,
    ) -> None:
        """Catches CalledProcessError from push_delete_branch without propagating."""
        mock_git.push_delete_branch.side_effect = subprocess.CalledProcessError(
            1, "git push origin --delete"
        )
        teardown = GitWorkstreamTeardown(repo_path=Path("/repo"))
        runtime = _make_runtime()

        teardown.teardown_workstream(runtime)  # Should not raise

    def test_satisfies_workstream_teardown_protocol(self) -> None:
        """GitWorkstreamTeardown satisfies the WorkstreamTeardown protocol."""
        teardown = GitWorkstreamTeardown(repo_path=Path("/repo"))
        assert isinstance(teardown, WorkstreamTeardown)
