"""Tests for GhIntegrationAutoMerger."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from agentrelay.workstream.core.io import IntegrationAutoMerger
from agentrelay.workstream.core.runtime import WorkstreamArtifacts, WorkstreamRuntime
from agentrelay.workstream.core.workstream import WorkstreamSpec
from agentrelay.workstream.implementations.integration_auto_merger import (
    GhIntegrationAutoMerger,
)


def _make_runtime(merge_pr_url: str | None = None) -> WorkstreamRuntime:
    runtime = WorkstreamRuntime(spec=WorkstreamSpec(id="ws-1"))
    runtime.artifacts = WorkstreamArtifacts(merge_pr_url=merge_pr_url)
    return runtime


class TestGhIntegrationAutoMerger:
    """Tests for GhIntegrationAutoMerger.merge."""

    @patch("agentrelay.workstream.implementations.integration_auto_merger.gh")
    def test_merges_pr_via_gh(self, mock_gh: MagicMock) -> None:
        """Calls gh.pr_merge with the integration PR URL."""
        merger = GhIntegrationAutoMerger()
        runtime = _make_runtime("https://github.com/org/repo/pull/42")

        merger.merge(runtime)
        mock_gh.pr_merge.assert_called_once_with("https://github.com/org/repo/pull/42")

    def test_raises_when_no_pr_url(self) -> None:
        """Raises RuntimeError when no integration PR URL is available."""
        merger = GhIntegrationAutoMerger()
        runtime = _make_runtime(merge_pr_url=None)

        with pytest.raises(RuntimeError, match="No integration PR URL"):
            merger.merge(runtime)

    @patch("agentrelay.workstream.implementations.integration_auto_merger.gh")
    def test_propagates_gh_error(self, mock_gh: MagicMock) -> None:
        """Propagates CalledProcessError from gh.pr_merge."""
        mock_gh.pr_merge.side_effect = subprocess.CalledProcessError(1, "gh")
        merger = GhIntegrationAutoMerger()
        runtime = _make_runtime("https://github.com/org/repo/pull/42")

        with pytest.raises(subprocess.CalledProcessError):
            merger.merge(runtime)

    def test_satisfies_protocol(self) -> None:
        """GhIntegrationAutoMerger satisfies the IntegrationAutoMerger protocol."""
        merger = GhIntegrationAutoMerger()
        assert isinstance(merger, IntegrationAutoMerger)
