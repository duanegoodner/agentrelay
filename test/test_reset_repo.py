"""Tests for reset_repo — RepoResetOps protocol and GitRepoResetOps."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from agentrelay.reset_repo import GitRepoResetOps

REPO = Path("/fake/repo")


class TestGitRepoResetOps:
    """Tests for GitRepoResetOps delegation to agentrelay.ops.git."""

    @patch("agentrelay.reset_repo.git.branch_delete")
    def test_branch_delete_delegates(self, mock_branch_delete: MagicMock) -> None:
        GitRepoResetOps(REPO).branch_delete("my-branch")
        mock_branch_delete.assert_called_once_with(REPO, "my-branch")

    @patch("agentrelay.reset_repo.git.push_delete_branch")
    def test_push_delete_branch_delegates(self, mock_push_delete: MagicMock) -> None:
        GitRepoResetOps(REPO).push_delete_branch("my-branch")
        mock_push_delete.assert_called_once_with(REPO, "my-branch")

    @patch("agentrelay.reset_repo.git.update_local_ref")
    def test_update_local_ref_delegates(self, mock_update: MagicMock) -> None:
        GitRepoResetOps(REPO).update_local_ref("my-branch", "abc123")
        mock_update.assert_called_once_with(REPO, "my-branch", "abc123")

    @patch("agentrelay.reset_repo.git.push_force_with_lease")
    def test_push_force_with_lease_delegates(self, mock_force: MagicMock) -> None:
        GitRepoResetOps(REPO).push_force_with_lease("my-branch")
        mock_force.assert_called_once_with(REPO, "my-branch")

    @patch("agentrelay.reset_repo.git.worktree_remove")
    def test_worktree_remove_delegates(self, mock_remove: MagicMock) -> None:
        wt = Path("/fake/worktree")
        GitRepoResetOps(REPO).worktree_remove(wt)
        mock_remove.assert_called_once_with(REPO, wt)

    @patch("agentrelay.reset_repo.git.worktree_prune")
    def test_worktree_prune_delegates(self, mock_prune: MagicMock) -> None:
        GitRepoResetOps(REPO).worktree_prune()
        mock_prune.assert_called_once_with(REPO)

    @patch("agentrelay.reset_repo.git.rev_parse")
    def test_rev_parse_delegates(self, mock_rev_parse: MagicMock) -> None:
        mock_rev_parse.return_value = "deadbeef"
        result = GitRepoResetOps(REPO).rev_parse("main")
        mock_rev_parse.assert_called_once_with(REPO, "main")
        assert result == "deadbeef"

    @patch("agentrelay.reset_repo.git.checkout")
    def test_checkout_in_delegates(self, mock_checkout: MagicMock) -> None:
        wt = Path("/fake/worktree")
        GitRepoResetOps(REPO).checkout_in(wt, "my-branch")
        # checkout_in routes through the worktree path, not the repo.
        mock_checkout.assert_called_once_with(wt, "my-branch")

    @patch("agentrelay.reset_repo.git.clean")
    def test_clean_in_delegates(self, mock_clean: MagicMock) -> None:
        wt = Path("/fake/worktree")
        GitRepoResetOps(REPO).clean_in(wt)
        mock_clean.assert_called_once_with(wt)

    @patch("agentrelay.reset_repo.git.current_branch")
    def test_current_branch_in_delegates(self, mock_current: MagicMock) -> None:
        mock_current.return_value = "my-branch"
        wt = Path("/fake/worktree")
        result = GitRepoResetOps(REPO).current_branch_in(wt)
        mock_current.assert_called_once_with(wt)
        assert result == "my-branch"

    def test_repo_path_is_exposed(self) -> None:
        """repo_path is accessible as a public attribute."""
        assert GitRepoResetOps(REPO).repo_path == REPO
