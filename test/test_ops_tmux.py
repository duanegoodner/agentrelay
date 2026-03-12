"""Tests for agentrelay.ops.tmux — tmux subprocess wrappers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentrelay.ops.tmux import (
    capture_pane,
    kill_window,
    new_window,
    send_keys,
    wait_for_tui_ready,
)


class TestNewWindow:
    """Tests for new_window."""

    @patch("agentrelay.ops.tmux.subprocess.run")
    def test_creates_window_and_returns_pane_id(self, mock_run: MagicMock) -> None:
        """Runs correct tmux command and returns pane ID from stdout."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="%42\n", stderr=""
        )
        result = new_window("mysession", "task_1", Path("/tmp/worktree"))

        assert result == "%42"
        mock_run.assert_called_once_with(
            [
                "tmux",
                "new-window",
                "-t",
                "mysession",
                "-n",
                "task_1",
                "-P",
                "-F",
                "#{pane_id}",
                "-c",
                "/tmp/worktree",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    @patch("agentrelay.ops.tmux.subprocess.run")
    def test_raises_on_failure(self, mock_run: MagicMock) -> None:
        """Raises CalledProcessError when tmux fails."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "tmux")
        with pytest.raises(subprocess.CalledProcessError):
            new_window("bad_session", "task_1", Path("/tmp"))


class TestSendKeys:
    """Tests for send_keys."""

    @patch("agentrelay.ops.tmux.subprocess.run")
    def test_sends_keys_with_enter(self, mock_run: MagicMock) -> None:
        """Sends keys followed by Enter by default."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"", stderr=b""
        )
        send_keys("%42", "echo hello")

        mock_run.assert_called_once_with(
            ["tmux", "send-keys", "-t", "%42", "echo hello", "Enter"],
            check=True,
            capture_output=True,
        )

    @patch("agentrelay.ops.tmux.subprocess.run")
    def test_sends_keys_without_enter(self, mock_run: MagicMock) -> None:
        """Omits Enter when press_enter=False."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"", stderr=b""
        )
        send_keys("%42", "partial text", press_enter=False)

        mock_run.assert_called_once_with(
            ["tmux", "send-keys", "-t", "%42", "partial text"],
            check=True,
            capture_output=True,
        )


class TestCapturePane:
    """Tests for capture_pane."""

    @patch("agentrelay.ops.tmux.subprocess.run")
    def test_captures_visible_content(self, mock_run: MagicMock) -> None:
        """Captures visible pane content without full history flag."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="some output\n", stderr=""
        )
        result = capture_pane("%42")

        assert result == "some output\n"
        mock_run.assert_called_once_with(
            ["tmux", "capture-pane", "-t", "%42", "-p"],
            check=True,
            capture_output=True,
            text=True,
        )

    @patch("agentrelay.ops.tmux.subprocess.run")
    def test_captures_full_scrollback(self, mock_run: MagicMock) -> None:
        """Includes -S - flag when full_history=True."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="full log\n", stderr=""
        )
        result = capture_pane("%42", full_history=True)

        assert result == "full log\n"
        mock_run.assert_called_once_with(
            ["tmux", "capture-pane", "-t", "%42", "-p", "-S", "-"],
            check=True,
            capture_output=True,
            text=True,
        )


class TestKillWindow:
    """Tests for kill_window."""

    @patch("agentrelay.ops.tmux.subprocess.run")
    def test_kills_window_by_pane_id(self, mock_run: MagicMock) -> None:
        """Runs correct kill-window command."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"", stderr=b""
        )
        kill_window("%42")

        mock_run.assert_called_once_with(
            ["tmux", "kill-window", "-t", "%42"],
            check=True,
            capture_output=True,
        )


class TestWaitForTuiReady:
    """Tests for wait_for_tui_ready."""

    @patch("agentrelay.ops.tmux.capture_pane")
    def test_returns_true_when_marker_found_immediately(
        self, mock_capture: MagicMock
    ) -> None:
        """Returns True when marker is present on first poll."""
        mock_capture.return_value = "Welcome! bypass permissions to continue\n"
        result = wait_for_tui_ready("%42", timeout=1.0, poll_interval=0.01)
        assert result is True

    @patch("agentrelay.ops.tmux.time.sleep")
    @patch("agentrelay.ops.tmux.capture_pane")
    def test_returns_true_after_several_polls(
        self, mock_capture: MagicMock, _mock_sleep: MagicMock
    ) -> None:
        """Returns True when marker appears after several polls."""
        mock_capture.side_effect = [
            "loading...",
            "loading...",
            "Ready! Bypass Permissions prompt here\n",
        ]
        result = wait_for_tui_ready("%42", timeout=10.0, poll_interval=0.01)
        assert result is True
        assert mock_capture.call_count == 3

    @patch("agentrelay.ops.tmux.time.monotonic")
    @patch("agentrelay.ops.tmux.capture_pane")
    def test_returns_false_on_timeout(
        self, mock_capture: MagicMock, mock_monotonic: MagicMock
    ) -> None:
        """Returns False when marker never appears before timeout."""
        mock_capture.return_value = "loading..."
        # Simulate: first call returns 0.0 (start), second returns 0.0 (in loop),
        # third returns 100.0 (past deadline).
        mock_monotonic.side_effect = [0.0, 0.0, 100.0]
        result = wait_for_tui_ready("%42", timeout=1.0, poll_interval=0.01)
        assert result is False

    @patch("agentrelay.ops.tmux.capture_pane")
    def test_case_insensitive_marker_match(self, mock_capture: MagicMock) -> None:
        """Marker matching is case-insensitive."""
        mock_capture.return_value = "BYPASS PERMISSIONS"
        result = wait_for_tui_ready("%42", timeout=1.0, poll_interval=0.01)
        assert result is True

    @patch("agentrelay.ops.tmux.time.monotonic")
    @patch("agentrelay.ops.tmux.capture_pane")
    def test_handles_capture_pane_error_gracefully(
        self, mock_capture: MagicMock, mock_monotonic: MagicMock
    ) -> None:
        """Continues polling when capture_pane raises CalledProcessError."""
        mock_capture.side_effect = [
            subprocess.CalledProcessError(1, "tmux"),
            "bypass permissions prompt\n",
        ]
        mock_monotonic.side_effect = [0.0, 0.0, 0.0]
        result = wait_for_tui_ready("%42", timeout=10.0, poll_interval=0.01)
        assert result is True
