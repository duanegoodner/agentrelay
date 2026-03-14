"""Tests for GitWorkstreamPreparer."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentrelay.errors import WorkspaceIntegrationError
from agentrelay.workstream.core.io import WorkstreamPreparer
from agentrelay.workstream.core.runtime import WorkstreamRuntime
from agentrelay.workstream.core.workstream import WorkstreamSpec
from agentrelay.workstream.implementations.workstream_preparer import (
    GitWorkstreamPreparer,
)


def _make_runtime(
    workstream_id: str = "ws-1",
    base_branch: str = "main",
) -> WorkstreamRuntime:
    return WorkstreamRuntime(
        spec=WorkstreamSpec(id=workstream_id, base_branch=base_branch),
    )


def _make_preparer(
    repo_path: Path = Path("/repo"),
    graph_name: str = "demo",
) -> GitWorkstreamPreparer:
    return GitWorkstreamPreparer(repo_path=repo_path, graph_name=graph_name)


class TestGitWorkstreamPreparer:
    """Tests for GitWorkstreamPreparer.prepare_workstream."""

    @patch("agentrelay.workstream.implementations.workstream_preparer.git")
    def test_creates_worktree_with_correct_args(
        self,
        mock_git: MagicMock,
    ) -> None:
        """Calls git.worktree_add with expected branch, path, and base."""
        preparer = _make_preparer()
        runtime = _make_runtime()

        preparer.prepare_workstream(runtime)

        mock_git.worktree_add.assert_called_once_with(
            Path("/repo"),
            Path("/repo/.worktrees/demo/ws-1"),
            "agentrelay/demo/ws-1/integration",
            "main",
        )

    @patch("agentrelay.workstream.implementations.workstream_preparer.git")
    def test_pushes_integration_branch(
        self,
        mock_git: MagicMock,
    ) -> None:
        """Pushes integration branch with set_upstream=True."""
        preparer = _make_preparer()
        runtime = _make_runtime()

        preparer.prepare_workstream(runtime)

        mock_git.push_branch.assert_called_once_with(
            Path("/repo"),
            "agentrelay/demo/ws-1/integration",
            set_upstream=True,
        )

    @patch("agentrelay.workstream.implementations.workstream_preparer.git")
    def test_sets_runtime_state(
        self,
        _mock_git: MagicMock,
    ) -> None:
        """Sets worktree_path and branch_name on workstream runtime state."""
        preparer = _make_preparer()
        runtime = _make_runtime()

        preparer.prepare_workstream(runtime)

        assert runtime.state.worktree_path == Path("/repo/.worktrees/demo/ws-1")
        assert runtime.state.branch_name == "agentrelay/demo/ws-1/integration"

    @patch("agentrelay.workstream.implementations.workstream_preparer.git")
    def test_wraps_git_error_in_workspace_integration_error(
        self,
        mock_git: MagicMock,
    ) -> None:
        """Wraps CalledProcessError from git in WorkspaceIntegrationError."""
        mock_git.worktree_add.side_effect = subprocess.CalledProcessError(
            1, "git worktree add"
        )
        preparer = _make_preparer()
        runtime = _make_runtime()

        with pytest.raises(WorkspaceIntegrationError, match="ws-1"):
            preparer.prepare_workstream(runtime)

    @patch("agentrelay.workstream.implementations.workstream_preparer.git")
    def test_uses_custom_base_branch(
        self,
        mock_git: MagicMock,
    ) -> None:
        """Uses the workstream spec's base_branch as the start point."""
        preparer = _make_preparer()
        runtime = _make_runtime(base_branch="develop")

        preparer.prepare_workstream(runtime)

        mock_git.worktree_add.assert_called_once_with(
            Path("/repo"),
            Path("/repo/.worktrees/demo/ws-1"),
            "agentrelay/demo/ws-1/integration",
            "develop",
        )

    def test_satisfies_workstream_preparer_protocol(self) -> None:
        """GitWorkstreamPreparer satisfies the WorkstreamPreparer protocol."""
        preparer = _make_preparer()
        assert isinstance(preparer, WorkstreamPreparer)
