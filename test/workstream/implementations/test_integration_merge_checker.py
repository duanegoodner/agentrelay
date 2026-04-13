"""Tests for GhIntegrationMergeChecker."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from agentrelay.workstream.core.io import (
    IntegrationMergeChecker,
    IntegrationMergeCheckResult,
)
from agentrelay.workstream.core.runtime import WorkstreamArtifacts, WorkstreamRuntime
from agentrelay.workstream.core.workstream import WorkstreamSpec
from agentrelay.workstream.implementations.integration_merge_checker import (
    GhIntegrationMergeChecker,
)

_MOD = "agentrelay.workstream.implementations.integration_merge_checker"


def _make_runtime(merge_pr_url: str | None = None) -> WorkstreamRuntime:
    runtime = WorkstreamRuntime(spec=WorkstreamSpec(id="ws-1"))
    runtime.artifacts = WorkstreamArtifacts(merge_pr_url=merge_pr_url)
    return runtime


def _make_checker() -> GhIntegrationMergeChecker:
    return GhIntegrationMergeChecker(repo_path=Path("/repo"))


class TestGhIntegrationMergeChecker:
    """Tests for GhIntegrationMergeChecker.is_merged."""

    @patch(f"{_MOD}.git")
    @patch(f"{_MOD}.gh")
    def test_returns_merged_with_pre_merge_sha(
        self, mock_gh: MagicMock, mock_git: MagicMock
    ) -> None:
        """Returns merged=True with pre-merge SHA from merge commit parent."""
        mock_gh.pr_is_merged.return_value = True
        mock_gh.pr_merge_commit_sha.return_value = "merge_commit_sha"
        mock_git.rev_parse.return_value = "parent_sha_abc"
        checker = _make_checker()
        runtime = _make_runtime("https://github.com/org/repo/pull/99")

        result = checker.is_merged(runtime)

        assert result == IntegrationMergeCheckResult(
            merged=True, target_branch_before_merge="parent_sha_abc"
        )
        mock_gh.pr_is_merged.assert_called_once_with(
            "https://github.com/org/repo/pull/99"
        )
        mock_git.rev_parse.assert_called_once_with(Path("/repo"), "merge_commit_sha^1")

    @patch(f"{_MOD}.git")
    @patch(f"{_MOD}.gh")
    def test_returns_not_merged(self, mock_gh: MagicMock, mock_git: MagicMock) -> None:
        """Returns merged=False when the GitHub CLI reports not merged."""
        mock_gh.pr_is_merged.return_value = False
        checker = _make_checker()
        runtime = _make_runtime("https://github.com/org/repo/pull/99")

        result = checker.is_merged(runtime)

        assert result == IntegrationMergeCheckResult(merged=False)
        mock_git.rev_parse.assert_not_called()

    @patch(f"{_MOD}.gh")
    def test_returns_not_merged_when_no_pr_url(self, mock_gh: MagicMock) -> None:
        """Returns merged=False when no integration PR URL is set."""
        checker = _make_checker()
        runtime = _make_runtime(merge_pr_url=None)

        result = checker.is_merged(runtime)

        assert result == IntegrationMergeCheckResult(merged=False)
        mock_gh.pr_is_merged.assert_not_called()

    @patch(f"{_MOD}.git")
    @patch(f"{_MOD}.gh")
    def test_graceful_degradation_when_merge_commit_unavailable(
        self, mock_gh: MagicMock, mock_git: MagicMock
    ) -> None:
        """Returns merged=True with None SHA when merge commit cannot be found."""
        mock_gh.pr_is_merged.return_value = True
        mock_gh.pr_merge_commit_sha.return_value = None
        checker = _make_checker()
        runtime = _make_runtime("https://github.com/org/repo/pull/99")

        result = checker.is_merged(runtime)

        assert result == IntegrationMergeCheckResult(
            merged=True, target_branch_before_merge=None
        )
        mock_git.rev_parse.assert_not_called()

    @patch(f"{_MOD}.git")
    @patch(f"{_MOD}.gh")
    def test_graceful_degradation_when_rev_parse_fails(
        self, mock_gh: MagicMock, mock_git: MagicMock
    ) -> None:
        """Returns merged=True with None SHA when rev_parse fails."""
        mock_gh.pr_is_merged.return_value = True
        mock_gh.pr_merge_commit_sha.return_value = "merge_commit_sha"
        mock_git.rev_parse.side_effect = Exception("git error")
        checker = _make_checker()
        runtime = _make_runtime("https://github.com/org/repo/pull/99")

        result = checker.is_merged(runtime)

        assert result == IntegrationMergeCheckResult(
            merged=True, target_branch_before_merge=None
        )

    def test_satisfies_protocol(self) -> None:
        """GhIntegrationMergeChecker satisfies the IntegrationMergeChecker protocol."""
        checker = _make_checker()
        assert isinstance(checker, IntegrationMergeChecker)
