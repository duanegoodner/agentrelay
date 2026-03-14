"""Tests for GhWorkstreamMerger."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from agentrelay.workstream.core.io import WorkstreamMerger
from agentrelay.workstream.core.runtime import WorkstreamRuntime
from agentrelay.workstream.core.workstream import WorkstreamSpec
from agentrelay.workstream.implementations.workstream_merger import (
    GhWorkstreamMerger,
)


def _make_runtime(
    workstream_id: str = "ws-1",
    merge_target_branch: str = "main",
    branch_name: str = "agentrelay/demo/ws-1/integration",
) -> WorkstreamRuntime:
    runtime = WorkstreamRuntime(
        spec=WorkstreamSpec(
            id=workstream_id,
            merge_target_branch=merge_target_branch,
        ),
    )
    runtime.state.branch_name = branch_name
    return runtime


class TestGhWorkstreamMerger:
    """Tests for GhWorkstreamMerger.merge_workstream."""

    @patch("agentrelay.workstream.implementations.workstream_merger.git")
    @patch("agentrelay.workstream.implementations.workstream_merger.gh")
    def test_creates_pr_with_correct_base_and_head(
        self,
        mock_gh: MagicMock,
        _mock_git: MagicMock,
    ) -> None:
        """Creates a PR from integration branch into merge_target_branch."""
        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        merger = GhWorkstreamMerger(repo_path=Path("/repo"))
        runtime = _make_runtime()

        merger.merge_workstream(runtime)

        mock_gh.pr_create.assert_called_once_with(
            Path("/repo"),
            title="Integrate workstream ws-1",
            body="Merge integration branch `agentrelay/demo/ws-1/integration` into `main`.",
            base="main",
            head="agentrelay/demo/ws-1/integration",
        )

    @patch("agentrelay.workstream.implementations.workstream_merger.git")
    @patch("agentrelay.workstream.implementations.workstream_merger.gh")
    def test_merges_pr(
        self,
        mock_gh: MagicMock,
        _mock_git: MagicMock,
    ) -> None:
        """Calls gh.pr_merge with the PR URL."""
        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        merger = GhWorkstreamMerger(repo_path=Path("/repo"))
        runtime = _make_runtime()

        merger.merge_workstream(runtime)

        mock_gh.pr_merge.assert_called_once_with("https://github.com/org/repo/pull/99")

    @patch("agentrelay.workstream.implementations.workstream_merger.git")
    @patch("agentrelay.workstream.implementations.workstream_merger.gh")
    def test_fetches_and_updates_local_ref(
        self,
        mock_gh: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """Fetches merge target and updates local ref after merge."""
        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        merger = GhWorkstreamMerger(repo_path=Path("/repo"))
        runtime = _make_runtime()

        merger.merge_workstream(runtime)

        mock_git.fetch_branch.assert_called_once_with(Path("/repo"), "main")
        mock_git.update_local_ref.assert_called_once_with(
            Path("/repo"), "main", "origin/main"
        )

    @patch("agentrelay.workstream.implementations.workstream_merger.git")
    @patch("agentrelay.workstream.implementations.workstream_merger.gh")
    def test_sets_merge_pr_url_artifact(
        self,
        mock_gh: MagicMock,
        _mock_git: MagicMock,
    ) -> None:
        """Sets merge_pr_url on workstream artifacts."""
        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        merger = GhWorkstreamMerger(repo_path=Path("/repo"))
        runtime = _make_runtime()

        merger.merge_workstream(runtime)

        assert runtime.artifacts.merge_pr_url == "https://github.com/org/repo/pull/99"

    def test_satisfies_workstream_merger_protocol(self) -> None:
        """GhWorkstreamMerger satisfies the WorkstreamMerger protocol."""
        merger = GhWorkstreamMerger(repo_path=Path("/repo"))
        assert isinstance(merger, WorkstreamMerger)
