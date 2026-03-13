"""Tests for SignalCompletionChecker."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentrelay.task import AgentRole, Task
from agentrelay.task_runner.core.io import TaskCompletionChecker
from agentrelay.task_runner.implementations.task_completion_checker import (
    SignalCompletionChecker,
    _parse_concerns,
)
from agentrelay.task_runtime import TaskRuntime


def _make_runtime(
    signal_dir: Path | None = Path("/repo/.workflow/demo/signals/task_1"),
) -> TaskRuntime:
    runtime = TaskRuntime(task=Task(id="task_1", role=AgentRole.GENERIC))
    runtime.state.signal_dir = signal_dir
    return runtime


class TestParseConcerns:
    """Tests for _parse_concerns helper."""

    def test_empty_string(self) -> None:
        assert _parse_concerns("") == ()

    def test_none(self) -> None:
        assert _parse_concerns(None) == ()

    def test_single_concern(self) -> None:
        assert _parse_concerns("design concern 1\n") == ("design concern 1",)

    def test_multiple_concerns(self) -> None:
        text = "concern A\nconcern B\nconcern C\n"
        assert _parse_concerns(text) == ("concern A", "concern B", "concern C")

    def test_blank_lines_skipped(self) -> None:
        text = "concern A\n\n\nconcern B\n"
        assert _parse_concerns(text) == ("concern A", "concern B")


class TestSignalCompletionChecker:
    """Tests for SignalCompletionChecker.wait_for_completion."""

    @patch("agentrelay.task_runner.implementations.task_completion_checker.signals")
    def test_done_signal_returns_pr_url(self, mock_signals: MagicMock) -> None:
        """Parses .done file and returns done signal with pr_url."""
        mock_signals.poll_signal_files = AsyncMock(return_value=".done")
        mock_signals.read_signal_file.side_effect = lambda _dir, name: {
            ".done": "2026-03-13T10:00:00Z\nhttps://github.com/org/repo/pull/42\n",
            "concerns.log": None,
        }[name]

        checker = SignalCompletionChecker(poll_interval=0.01)
        runtime = _make_runtime()
        signal = asyncio.run(checker.wait_for_completion(runtime))

        assert signal.outcome == "done"
        assert signal.pr_url == "https://github.com/org/repo/pull/42"
        assert signal.error is None
        assert signal.concerns == ()

    @patch("agentrelay.task_runner.implementations.task_completion_checker.signals")
    def test_failed_signal_returns_error(self, mock_signals: MagicMock) -> None:
        """Parses .failed file and returns failed signal with error."""
        mock_signals.poll_signal_files = AsyncMock(return_value=".failed")
        mock_signals.read_signal_file.side_effect = lambda _dir, name: {
            ".failed": "2026-03-13T10:00:00Z\nGate check failed\n",
            "concerns.log": None,
        }[name]

        checker = SignalCompletionChecker(poll_interval=0.01)
        runtime = _make_runtime()
        signal = asyncio.run(checker.wait_for_completion(runtime))

        assert signal.outcome == "failed"
        assert signal.error == "Gate check failed"
        assert signal.pr_url is None

    @patch("agentrelay.task_runner.implementations.task_completion_checker.signals")
    def test_reads_concerns_log(self, mock_signals: MagicMock) -> None:
        """Includes concerns from concerns.log in the signal."""
        mock_signals.poll_signal_files = AsyncMock(return_value=".done")
        mock_signals.read_signal_file.side_effect = lambda _dir, name: {
            ".done": "2026-03-13T10:00:00Z\nhttps://github.com/org/repo/pull/1\n",
            "concerns.log": "style issue\nmissing test\n",
        }[name]

        checker = SignalCompletionChecker(poll_interval=0.01)
        signal = asyncio.run(checker.wait_for_completion(_make_runtime()))

        assert signal.concerns == ("style issue", "missing test")

    @patch("agentrelay.task_runner.implementations.task_completion_checker.signals")
    def test_handles_missing_payload_line(self, mock_signals: MagicMock) -> None:
        """Returns None payload when signal file has only a timestamp line."""
        mock_signals.poll_signal_files = AsyncMock(return_value=".failed")
        mock_signals.read_signal_file.side_effect = lambda _dir, name: {
            ".failed": "2026-03-13T10:00:00Z\n",
            "concerns.log": None,
        }[name]

        checker = SignalCompletionChecker(poll_interval=0.01)
        signal = asyncio.run(checker.wait_for_completion(_make_runtime()))

        assert signal.outcome == "failed"
        assert signal.error is None

    def test_raises_when_signal_dir_is_none(self) -> None:
        """Raises ValueError if signal_dir is not set."""
        runtime = _make_runtime(signal_dir=None)
        checker = SignalCompletionChecker()

        with pytest.raises(ValueError, match="signal_dir"):
            asyncio.run(checker.wait_for_completion(runtime))

    def test_satisfies_completion_checker_protocol(self) -> None:
        """SignalCompletionChecker satisfies the TaskCompletionChecker protocol."""
        checker = SignalCompletionChecker()
        assert isinstance(checker, TaskCompletionChecker)
