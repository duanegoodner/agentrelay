"""Tests for reset_pr module — IntegrationPrOps protocol + GhIntegrationPrOps."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from agentrelay.reset_pr import GhIntegrationPrOps


class TestGhIntegrationPrOpsAppendResetActivity:
    """Tests for GhIntegrationPrOps.append_reset_activity."""

    @patch("agentrelay.reset_pr.gh.pr_update_body")
    @patch("agentrelay.reset_pr.gh.pr_body")
    def test_appends_section_to_pr_body(
        self, mock_body: MagicMock, mock_update: MagicMock
    ) -> None:
        """Adds ## Reset activity section when none exists."""
        mock_body.return_value = "## Summary\nOriginal body."
        updater = GhIntegrationPrOps()

        log = updater.append_reset_activity(
            "https://github.com/org/repo/pull/5",
            [("task_a", "pr_merged")],
        )

        assert len(log) == 1
        assert "Updated" in log[0]
        mock_update.assert_called_once()
        new_body = mock_update.call_args[0][1]
        assert "## Reset activity" in new_body
        assert "Task `task_a` reset (was pr_merged)" in new_body
        assert new_body.startswith("## Summary\nOriginal body.")

    @patch("agentrelay.reset_pr.gh.pr_update_body")
    @patch("agentrelay.reset_pr.gh.pr_body")
    def test_appends_to_existing_section(
        self, mock_body: MagicMock, mock_update: MagicMock
    ) -> None:
        """Appends to existing ## Reset activity without duplicating header."""
        mock_body.return_value = (
            "## Summary\nBody.\n\n---\n## Reset activity\n"
            "- 2026-04-19T10:00:00+00:00: Task `task_a` reset (was pr_merged)"
        )
        updater = GhIntegrationPrOps()

        log = updater.append_reset_activity(
            "https://github.com/org/repo/pull/5",
            [("task_b", "completed")],
        )

        assert len(log) == 1
        new_body = mock_update.call_args[0][1]
        # Only one ## Reset activity header.
        assert new_body.count("## Reset activity") == 1
        assert "Task `task_b` reset (was completed)" in new_body
        # Old entry preserved.
        assert "Task `task_a` reset (was pr_merged)" in new_body

    @patch("agentrelay.reset_pr.gh.pr_update_body")
    @patch("agentrelay.reset_pr.gh.pr_body")
    def test_empty_entries_returns_empty(
        self, mock_body: MagicMock, mock_update: MagicMock
    ) -> None:
        """Returns empty list and makes no API calls for empty entries."""
        updater = GhIntegrationPrOps()

        log = updater.append_reset_activity("https://github.com/org/repo/pull/5", [])

        assert log == []
        mock_body.assert_not_called()
        mock_update.assert_not_called()

    @patch("agentrelay.reset_pr.gh.pr_update_body")
    @patch("agentrelay.reset_pr.gh.pr_body")
    def test_pr_body_failure_returns_warning(
        self, mock_body: MagicMock, mock_update: MagicMock
    ) -> None:
        """Returns warning log when pr_body fails."""
        mock_body.side_effect = subprocess.CalledProcessError(1, "gh")
        updater = GhIntegrationPrOps()

        log = updater.append_reset_activity(
            "https://github.com/org/repo/pull/5",
            [("task_a", "pr_merged")],
        )

        assert len(log) == 1
        assert "WARNING" in log[0]
        mock_update.assert_not_called()

    @patch("agentrelay.reset_pr.gh.pr_update_body")
    @patch("agentrelay.reset_pr.gh.pr_body")
    def test_update_failure_returns_warning(
        self, mock_body: MagicMock, mock_update: MagicMock
    ) -> None:
        """Returns warning log when pr_update_body fails."""
        mock_body.return_value = "## Summary\nBody."
        mock_update.side_effect = subprocess.CalledProcessError(1, "gh")
        updater = GhIntegrationPrOps()

        log = updater.append_reset_activity(
            "https://github.com/org/repo/pull/5",
            [("task_a", "pr_merged")],
        )

        assert len(log) == 1
        assert "WARNING" in log[0]


class TestGhIntegrationPrOpsClosePr:
    """Tests for GhIntegrationPrOps.close_pr."""

    @patch("agentrelay.reset_pr.gh.pr_close_by_url")
    def test_close_pr_success(self, mock_close: MagicMock) -> None:
        """Returns a success log line when the close call succeeds."""
        updater = GhIntegrationPrOps()

        log = updater.close_pr("https://github.com/org/repo/pull/5")

        mock_close.assert_called_once_with("https://github.com/org/repo/pull/5")
        assert log == ["Closed integration PR https://github.com/org/repo/pull/5"]

    @patch("agentrelay.reset_pr.gh.pr_close_by_url")
    def test_close_pr_failure_returns_warning(self, mock_close: MagicMock) -> None:
        """Returns a WARNING log line when the close call fails."""
        mock_close.side_effect = subprocess.CalledProcessError(1, "gh")
        updater = GhIntegrationPrOps()

        log = updater.close_pr("https://github.com/org/repo/pull/5")

        assert len(log) == 1
        assert "WARNING" in log[0]
        assert "https://github.com/org/repo/pull/5" in log[0]
