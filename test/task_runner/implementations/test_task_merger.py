"""Tests for GhTaskMerger."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentrelay.task import AgentRole, Task
from agentrelay.task_runner.core.io import TaskMerger
from agentrelay.task_runner.implementations.task_merger import GhTaskMerger
from agentrelay.task_runtime import TaskRuntime


def _make_runtime(
    signal_dir: Path | None = Path("/repo/.workflow/demo/signals/task_1"),
) -> TaskRuntime:
    runtime = TaskRuntime(task=Task(id="task_1", role=AgentRole.GENERIC))
    runtime.state.signal_dir = signal_dir
    return runtime


class TestGhTaskMerger:
    """Tests for GhTaskMerger.merge_pr."""

    @patch("agentrelay.task_runner.implementations.task_merger.signals")
    @patch("agentrelay.task_runner.implementations.task_merger.git")
    @patch("agentrelay.task_runner.implementations.task_merger.gh")
    def test_merges_pr_and_updates_local_ref(
        self,
        mock_gh: MagicMock,
        mock_git: MagicMock,
        _mock_signals: MagicMock,
    ) -> None:
        """Calls gh.pr_merge, then fetches and updates local ref."""
        merger = GhTaskMerger(
            repo_path=Path("/repo"), integration_branch="agentrelay/demo"
        )
        runtime = _make_runtime()

        merger.merge_pr(runtime, "https://github.com/org/repo/pull/42")

        mock_gh.pr_merge.assert_called_once_with("https://github.com/org/repo/pull/42")
        mock_git.fetch_branch.assert_called_once_with(Path("/repo"), "agentrelay/demo")
        mock_git.update_local_ref.assert_called_once_with(
            Path("/repo"), "agentrelay/demo", "origin/agentrelay/demo"
        )

    @patch("agentrelay.task_runner.implementations.task_merger.signals")
    @patch("agentrelay.task_runner.implementations.task_merger.git")
    @patch("agentrelay.task_runner.implementations.task_merger.gh")
    def test_writes_merged_signal_file(
        self,
        _mock_gh: MagicMock,
        _mock_git: MagicMock,
        mock_signals: MagicMock,
    ) -> None:
        """Writes .merged signal file with ISO timestamp."""
        merger = GhTaskMerger(
            repo_path=Path("/repo"), integration_branch="agentrelay/demo"
        )
        runtime = _make_runtime()

        merger.merge_pr(runtime, "https://github.com/org/repo/pull/42")

        signal_dir = Path("/repo/.workflow/demo/signals/task_1")
        mock_signals.write_text.assert_called_once()
        call_args = mock_signals.write_text.call_args
        assert call_args[0][0] == signal_dir
        assert call_args[0][1] == ".merged"
        assert call_args[0][2].endswith("\n")

    def test_satisfies_task_merger_protocol(self) -> None:
        """GhTaskMerger satisfies the TaskMerger protocol."""
        merger = GhTaskMerger(
            repo_path=Path("/repo"), integration_branch="agentrelay/demo"
        )
        assert isinstance(merger, TaskMerger)
