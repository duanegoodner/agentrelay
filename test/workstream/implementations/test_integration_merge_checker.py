"""Tests for GhIntegrationMergeChecker."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agentrelay.workstream.core.io import IntegrationMergeChecker
from agentrelay.workstream.core.runtime import WorkstreamArtifacts, WorkstreamRuntime
from agentrelay.workstream.core.workstream import WorkstreamSpec
from agentrelay.workstream.implementations.integration_merge_checker import (
    GhIntegrationMergeChecker,
)


def _make_runtime(merge_pr_url: str | None = None) -> WorkstreamRuntime:
    runtime = WorkstreamRuntime(spec=WorkstreamSpec(id="ws-1"))
    runtime.artifacts = WorkstreamArtifacts(merge_pr_url=merge_pr_url)
    return runtime


class TestGhIntegrationMergeChecker:
    """Tests for GhIntegrationMergeChecker.is_merged."""

    @patch("agentrelay.workstream.implementations.integration_merge_checker.gh")
    def test_returns_true_when_gh_reports_merged(self, mock_gh: MagicMock) -> None:
        """Returns True when the GitHub CLI reports the PR is merged."""
        mock_gh.pr_is_merged.return_value = True
        checker = GhIntegrationMergeChecker()
        runtime = _make_runtime("https://github.com/org/repo/pull/99")

        assert checker.is_merged(runtime) is True
        mock_gh.pr_is_merged.assert_called_once_with(
            "https://github.com/org/repo/pull/99"
        )

    @patch("agentrelay.workstream.implementations.integration_merge_checker.gh")
    def test_returns_false_when_gh_reports_not_merged(self, mock_gh: MagicMock) -> None:
        """Returns False when the GitHub CLI reports the PR is not merged."""
        mock_gh.pr_is_merged.return_value = False
        checker = GhIntegrationMergeChecker()
        runtime = _make_runtime("https://github.com/org/repo/pull/99")

        assert checker.is_merged(runtime) is False

    @patch("agentrelay.workstream.implementations.integration_merge_checker.gh")
    def test_returns_false_when_no_pr_url(self, mock_gh: MagicMock) -> None:
        """Returns False when no integration PR URL is set."""
        checker = GhIntegrationMergeChecker()
        runtime = _make_runtime(merge_pr_url=None)

        assert checker.is_merged(runtime) is False
        mock_gh.pr_is_merged.assert_not_called()

    def test_satisfies_protocol(self) -> None:
        """GhIntegrationMergeChecker satisfies the IntegrationMergeChecker protocol."""
        checker = GhIntegrationMergeChecker()
        assert isinstance(checker, IntegrationMergeChecker)
