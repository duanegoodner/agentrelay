"""Tests for reset_pr module — PrBodyUpdater protocol and GhPrBodyUpdater."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from agentrelay.reset_pr import GhPrBodyUpdater


class TestGhPrBodyUpdater:
    """Tests for GhPrBodyUpdater.append_reset_activity."""

    @patch("agentrelay.reset_pr.gh.pr_update_body")
    @patch("agentrelay.reset_pr.gh.pr_body")
    def test_appends_section_to_pr_body(
        self, mock_body: MagicMock, mock_update: MagicMock
    ) -> None:
        """Adds ## Reset activity section when none exists."""
        mock_body.return_value = "## Summary\nOriginal body."
        updater = GhPrBodyUpdater()

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
        updater = GhPrBodyUpdater()

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
        updater = GhPrBodyUpdater()

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
        updater = GhPrBodyUpdater()

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
        updater = GhPrBodyUpdater()

        log = updater.append_reset_activity(
            "https://github.com/org/repo/pull/5",
            [("task_a", "pr_merged")],
        )

        assert len(log) == 1
        assert "WARNING" in log[0]
