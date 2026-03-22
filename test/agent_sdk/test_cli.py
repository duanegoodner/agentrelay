"""Tests for :mod:`agentrelay.agent_sdk.cli`."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agentrelay.agent_sdk import cli


@pytest.fixture()
def signal_dir(tmp_path: Path) -> Path:
    """Create a signal dir with a minimal manifest.json."""
    manifest = {
        "task": {"id": "test_task"},
        "workspace": {
            "branch_name": "test-branch",
            "integration_branch": "main",
        },
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    return tmp_path


class TestCompleteCli:
    def test_calls_helper_complete(
        self, signal_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AGENTRELAY_SIGNAL_DIR", str(signal_dir))
        monkeypatch.setattr(
            "sys.argv", ["agentrelay-complete", "--title", "T", "--body", "B"]
        )
        with patch("agentrelay.agent_sdk.cli.TaskHelper") as mock_cls:
            instance = mock_cls.from_env.return_value
            cli.complete()
            instance.complete.assert_called_once_with(title="T", body="B")

    def test_defaults_title_and_body(
        self, signal_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AGENTRELAY_SIGNAL_DIR", str(signal_dir))
        monkeypatch.setattr("sys.argv", ["agentrelay-complete"])
        with patch("agentrelay.agent_sdk.cli.TaskHelper") as mock_cls:
            instance = mock_cls.from_env.return_value
            cli.complete()
            instance.complete.assert_called_once_with(title=None, body=None)


class TestCompleteNoPrCli:
    def test_calls_helper_complete_without_pr(
        self, signal_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AGENTRELAY_SIGNAL_DIR", str(signal_dir))
        monkeypatch.setattr("sys.argv", ["agentrelay-complete-no-pr"])
        with patch("agentrelay.agent_sdk.cli.TaskHelper") as mock_cls:
            instance = mock_cls.from_env.return_value
            cli.complete_no_pr()
            instance.complete_without_pr.assert_called_once_with()


class TestFailedCli:
    def test_calls_helper_mark_failed(
        self, signal_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AGENTRELAY_SIGNAL_DIR", str(signal_dir))
        monkeypatch.setattr("sys.argv", ["agentrelay-failed", "--reason", "broken"])
        with patch("agentrelay.agent_sdk.cli.TaskHelper") as mock_cls:
            instance = mock_cls.from_env.return_value
            cli.failed()
            instance.mark_failed.assert_called_once_with("broken")

    def test_reason_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.argv", ["agentrelay-failed"])
        with pytest.raises(SystemExit):
            cli.failed()


class TestConcernCli:
    def test_calls_helper_record_concern(
        self, signal_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AGENTRELAY_SIGNAL_DIR", str(signal_dir))
        monkeypatch.setattr(
            "sys.argv", ["agentrelay-concern", "--message", "spec conflict"]
        )
        with patch("agentrelay.agent_sdk.cli.TaskHelper") as mock_cls:
            instance = mock_cls.from_env.return_value
            cli.concern()
            instance.record_concern.assert_called_once_with("spec conflict")

    def test_message_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.argv", ["agentrelay-concern"])
        with pytest.raises(SystemExit):
            cli.concern()
