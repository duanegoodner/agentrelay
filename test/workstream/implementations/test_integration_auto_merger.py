"""Tests for GhIntegrationAutoMerger."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentrelay.workstream.core.io import (
    IntegrationAutoMerger,
    IntegrationMergeResult,
)
from agentrelay.workstream.core.runtime import WorkstreamArtifacts, WorkstreamRuntime
from agentrelay.workstream.core.workstream import WorkstreamSpec
from agentrelay.workstream.implementations.integration_auto_merger import (
    GhIntegrationAutoMerger,
)

_MOD = "agentrelay.workstream.implementations.integration_auto_merger"


def _make_runtime(merge_pr_url: str | None = None) -> WorkstreamRuntime:
    runtime = WorkstreamRuntime(spec=WorkstreamSpec(id="ws-1"))
    runtime.artifacts = WorkstreamArtifacts(merge_pr_url=merge_pr_url)
    return runtime


def _make_merger() -> GhIntegrationAutoMerger:
    return GhIntegrationAutoMerger(repo_path=Path("/repo"))


class TestGhIntegrationAutoMerger:
    """Tests for GhIntegrationAutoMerger.merge."""

    @patch(f"{_MOD}.git")
    @patch(f"{_MOD}.gh")
    def test_merges_pr_via_gh(self, mock_gh: MagicMock, mock_git: MagicMock) -> None:
        """Calls gh.pr_merge with the integration PR URL."""
        mock_git.rev_parse.return_value = "before_sha"
        merger = _make_merger()
        runtime = _make_runtime("https://github.com/org/repo/pull/42")

        merger.merge(runtime)
        mock_gh.pr_merge.assert_called_once_with("https://github.com/org/repo/pull/42")

    def test_raises_when_no_pr_url(self) -> None:
        """Raises RuntimeError when no integration PR URL is available."""
        merger = _make_merger()
        runtime = _make_runtime(merge_pr_url=None)

        with pytest.raises(RuntimeError, match="No integration PR URL"):
            merger.merge(runtime)

    @patch(f"{_MOD}.git")
    @patch(f"{_MOD}.gh")
    def test_propagates_gh_error(self, mock_gh: MagicMock, mock_git: MagicMock) -> None:
        """Propagates CalledProcessError from gh.pr_merge."""
        mock_git.rev_parse.return_value = "before_sha"
        mock_gh.pr_merge.side_effect = subprocess.CalledProcessError(1, "gh")
        merger = _make_merger()
        runtime = _make_runtime("https://github.com/org/repo/pull/42")

        with pytest.raises(subprocess.CalledProcessError):
            merger.merge(runtime)

    @patch(f"{_MOD}.git")
    @patch(f"{_MOD}.gh")
    def test_returns_merge_result_with_pre_merge_sha(
        self, mock_gh: MagicMock, mock_git: MagicMock
    ) -> None:
        """Returns IntegrationMergeResult with the pre-merge target branch SHA."""
        mock_git.rev_parse.return_value = "pre_merge_sha_xyz"
        merger = _make_merger()
        runtime = _make_runtime("https://github.com/org/repo/pull/42")

        result = merger.merge(runtime)

        assert result == IntegrationMergeResult(
            target_branch_before_merge="pre_merge_sha_xyz"
        )
        mock_git.rev_parse.assert_called_once_with(Path("/repo"), "main")

    def test_satisfies_protocol(self) -> None:
        """GhIntegrationAutoMerger satisfies the IntegrationAutoMerger protocol."""
        merger = _make_merger()
        assert isinstance(merger, IntegrationAutoMerger)
