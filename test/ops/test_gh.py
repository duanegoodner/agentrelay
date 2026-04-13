"""Tests for agentrelay.ops.gh — GitHub CLI subprocess wrappers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentrelay.ops.gh import (
    pr_body,
    pr_create,
    pr_is_merged,
    pr_merge,
    pr_merge_commit_sha,
)


class TestPrCreate:
    """Tests for pr_create."""

    @patch("agentrelay.ops.gh.subprocess.run")
    def test_creates_pr_and_returns_url(self, mock_run: MagicMock) -> None:
        """Runs gh pr create with correct args and returns URL from stdout."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="https://github.com/org/repo/pull/42\n",
            stderr="",
        )
        url = pr_create(
            Path("/tmp/repo"),
            title="feat: add thing",
            body="## Summary\nAdded a thing.",
            base="main",
            head="feat/thing",
        )

        assert url == "https://github.com/org/repo/pull/42"
        mock_run.assert_called_once_with(
            [
                "gh",
                "pr",
                "create",
                "--title",
                "feat: add thing",
                "--body",
                "## Summary\nAdded a thing.",
                "--base",
                "main",
                "--head",
                "feat/thing",
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd="/tmp/repo",
        )

    @patch("agentrelay.ops.gh.subprocess.run")
    def test_raises_on_failure(self, mock_run: MagicMock) -> None:
        """Raises CalledProcessError when gh fails."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "gh")
        with pytest.raises(subprocess.CalledProcessError):
            pr_create(
                Path("/tmp/repo"),
                title="t",
                body="b",
                base="main",
                head="feat/x",
            )


class TestPrMerge:
    """Tests for pr_merge."""

    @patch("agentrelay.ops.gh.subprocess.run")
    def test_merges_pr(self, mock_run: MagicMock) -> None:
        """Runs gh pr merge with correct args."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"", stderr=b""
        )
        pr_merge("https://github.com/org/repo/pull/42")

        mock_run.assert_called_once_with(
            ["gh", "pr", "merge", "https://github.com/org/repo/pull/42", "--merge"],
            check=True,
            capture_output=True,
        )

    @patch("agentrelay.ops.gh.subprocess.run")
    def test_raises_on_failure(self, mock_run: MagicMock) -> None:
        """Raises CalledProcessError when merge fails."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "gh")
        with pytest.raises(subprocess.CalledProcessError):
            pr_merge("https://github.com/org/repo/pull/99")


class TestPrIsMerged:
    """Tests for pr_is_merged."""

    @patch("agentrelay.ops.gh.subprocess.run")
    def test_returns_true_when_merged(self, mock_run: MagicMock) -> None:
        """Returns True when gh reports state as MERGED."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="MERGED\n", stderr=""
        )
        assert pr_is_merged("https://github.com/org/repo/pull/42") is True
        mock_run.assert_called_once_with(
            [
                "gh",
                "pr",
                "view",
                "https://github.com/org/repo/pull/42",
                "--json",
                "state",
                "--jq",
                ".state",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    @patch("agentrelay.ops.gh.subprocess.run")
    def test_returns_false_when_open(self, mock_run: MagicMock) -> None:
        """Returns False when PR is still open."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="OPEN\n", stderr=""
        )
        assert pr_is_merged("https://github.com/org/repo/pull/42") is False

    @patch("agentrelay.ops.gh.subprocess.run")
    def test_returns_false_when_closed(self, mock_run: MagicMock) -> None:
        """Returns False when PR is closed without merge."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="CLOSED\n", stderr=""
        )
        assert pr_is_merged("https://github.com/org/repo/pull/42") is False

    @patch("agentrelay.ops.gh.subprocess.run")
    def test_returns_false_on_subprocess_error(self, mock_run: MagicMock) -> None:
        """Returns False on CalledProcessError instead of raising."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "gh")
        assert pr_is_merged("https://github.com/org/repo/pull/42") is False


class TestPrBody:
    """Tests for pr_body."""

    @patch("agentrelay.ops.gh.subprocess.run")
    def test_returns_pr_body_text(self, mock_run: MagicMock) -> None:
        """Returns the PR body from gh pr view output."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="## Summary\nDid the thing.\n",
            stderr="",
        )
        body = pr_body("https://github.com/org/repo/pull/42")

        assert body == "## Summary\nDid the thing."
        mock_run.assert_called_once_with(
            [
                "gh",
                "pr",
                "view",
                "https://github.com/org/repo/pull/42",
                "--json",
                "body",
                "--jq",
                ".body",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    @patch("agentrelay.ops.gh.subprocess.run")
    def test_raises_on_failure(self, mock_run: MagicMock) -> None:
        """Raises CalledProcessError when gh fails."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "gh")
        with pytest.raises(subprocess.CalledProcessError):
            pr_body("https://github.com/org/repo/pull/99")


class TestPrMergeCommitSha:
    """Tests for pr_merge_commit_sha."""

    @patch("agentrelay.ops.gh.subprocess.run")
    def test_returns_sha_when_merged(self, mock_run: MagicMock) -> None:
        """Returns the merge commit SHA for a merged PR."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="abc123def456\n", stderr=""
        )
        sha = pr_merge_commit_sha("https://github.com/org/repo/pull/42")

        assert sha == "abc123def456"
        mock_run.assert_called_once_with(
            [
                "gh",
                "pr",
                "view",
                "https://github.com/org/repo/pull/42",
                "--json",
                "mergeCommit",
                "--jq",
                ".mergeCommit.oid",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    @patch("agentrelay.ops.gh.subprocess.run")
    def test_returns_none_when_empty_output(self, mock_run: MagicMock) -> None:
        """Returns None when gh returns empty output (PR not merged)."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="\n", stderr=""
        )
        assert pr_merge_commit_sha("https://github.com/org/repo/pull/42") is None

    @patch("agentrelay.ops.gh.subprocess.run")
    def test_returns_none_on_subprocess_error(self, mock_run: MagicMock) -> None:
        """Returns None on CalledProcessError instead of raising."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "gh")
        assert pr_merge_commit_sha("https://github.com/org/repo/pull/42") is None
