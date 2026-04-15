"""Tests for GhTaskPrProber."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from agentrelay.workstream.core.io import TaskPrProber
from agentrelay.workstream.implementations.task_pr_prober import GhTaskPrProber

_MOD = "agentrelay.workstream.implementations.task_pr_prober"


class TestGhTaskPrProberIsMerged:
    """Tests for GhTaskPrProber.is_merged."""

    @patch(f"{_MOD}.gh")
    def test_returns_true_when_pr_is_merged(self, mock_gh: MagicMock) -> None:
        """Delegates to gh.pr_is_merged and returns its result."""
        mock_gh.pr_is_merged.return_value = True
        prober = GhTaskPrProber()

        assert prober.is_merged("https://github.com/org/repo/pull/42") is True
        mock_gh.pr_is_merged.assert_called_once_with(
            "https://github.com/org/repo/pull/42"
        )

    @patch(f"{_MOD}.gh")
    def test_returns_false_when_pr_not_merged(self, mock_gh: MagicMock) -> None:
        """Returns False when gh.pr_is_merged returns False."""
        mock_gh.pr_is_merged.return_value = False
        prober = GhTaskPrProber()

        assert prober.is_merged("https://github.com/org/repo/pull/42") is False


class TestGhTaskPrProberTryMerge:
    """Tests for GhTaskPrProber.try_merge."""

    @patch(f"{_MOD}.gh")
    def test_returns_true_on_merge_success(self, mock_gh: MagicMock) -> None:
        """Returns True when gh.pr_merge succeeds."""
        mock_gh.pr_merge.return_value = None
        prober = GhTaskPrProber()

        assert prober.try_merge("https://github.com/org/repo/pull/42") is True
        mock_gh.pr_merge.assert_called_once_with("https://github.com/org/repo/pull/42")

    @patch(f"{_MOD}.gh")
    def test_returns_false_on_called_process_error(self, mock_gh: MagicMock) -> None:
        """Returns False (does not re-raise) when gh.pr_merge raises."""
        mock_gh.pr_merge.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["gh", "pr", "merge"]
        )
        prober = GhTaskPrProber()

        assert prober.try_merge("https://github.com/org/repo/pull/42") is False


class TestGhTaskPrProberProtocol:
    """Protocol conformance check."""

    def test_satisfies_task_pr_prober_protocol(self) -> None:
        """GhTaskPrProber structurally satisfies TaskPrProber."""
        assert isinstance(GhTaskPrProber(), TaskPrProber)
