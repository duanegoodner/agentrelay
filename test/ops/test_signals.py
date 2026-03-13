"""Tests for agentrelay.ops.signals — signal directory filesystem operations."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path

from agentrelay.ops.signals import (
    ensure_signal_dir,
    poll_signal_files,
    read_signal_file,
    write_json,
    write_text,
)


class TestEnsureSignalDir:
    """Tests for ensure_signal_dir."""

    def test_creates_nested_directory(self, tmp_path: Path) -> None:
        """Creates a nested directory structure."""
        target = tmp_path / "a" / "b" / "c"
        result = ensure_signal_dir(target)
        assert target.is_dir()
        assert result == target

    def test_idempotent_on_existing(self, tmp_path: Path) -> None:
        """No error when directory already exists."""
        target = tmp_path / "signals"
        target.mkdir()
        result = ensure_signal_dir(target)
        assert target.is_dir()
        assert result == target


class TestWriteJson:
    """Tests for write_json."""

    def test_writes_formatted_json(self, tmp_path: Path) -> None:
        """Writes data as indented JSON with trailing newline."""
        signal_dir = tmp_path / "signals"
        data = {"task_id": "my_task", "role": "generic"}
        write_json(signal_dir, "task_context.json", data)

        content = (signal_dir / "task_context.json").read_text()
        assert json.loads(content) == data
        assert content.endswith("\n")
        assert "  " in content  # indented

    def test_creates_signal_dir_if_missing(self, tmp_path: Path) -> None:
        """Creates signal directory when it doesn't exist."""
        signal_dir = tmp_path / "nested" / "signals"
        write_json(signal_dir, "data.json", {"key": "value"})
        assert signal_dir.is_dir()


class TestWriteText:
    """Tests for write_text."""

    def test_writes_text_content(self, tmp_path: Path) -> None:
        """Writes text content to the specified file."""
        signal_dir = tmp_path / "signals"
        signal_dir.mkdir()
        write_text(signal_dir, "instructions.md", "# Do the thing\n")

        content = (signal_dir / "instructions.md").read_text()
        assert content == "# Do the thing\n"

    def test_creates_signal_dir_if_missing(self, tmp_path: Path) -> None:
        """Creates signal directory when it doesn't exist."""
        signal_dir = tmp_path / "nested" / "signals"
        write_text(signal_dir, "notes.txt", "hello")
        assert signal_dir.is_dir()


class TestReadSignalFile:
    """Tests for read_signal_file."""

    def test_reads_existing_file(self, tmp_path: Path) -> None:
        """Returns file contents when file exists."""
        (tmp_path / ".done").write_text("done\nhttps://github.com/org/repo/pull/1\n")
        result = read_signal_file(tmp_path, ".done")
        assert result == "done\nhttps://github.com/org/repo/pull/1\n"

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        """Returns None when file does not exist."""
        result = read_signal_file(tmp_path, ".done")
        assert result is None

    def test_returns_none_for_directory(self, tmp_path: Path) -> None:
        """Returns None when path is a directory, not a file."""
        (tmp_path / ".done").mkdir()
        result = read_signal_file(tmp_path, ".done")
        assert result is None


class TestPollSignalFiles:
    """Tests for poll_signal_files."""

    def test_returns_immediately_when_file_exists(self, tmp_path: Path) -> None:
        """Returns immediately if signal file already present."""
        (tmp_path / ".done").write_text("done\n")
        result = asyncio.run(poll_signal_files(tmp_path, poll_interval=0.05))
        assert result == ".done"

    def test_returns_first_matching_file(self, tmp_path: Path) -> None:
        """Returns the first filename in the tuple that matches."""
        (tmp_path / ".failed").write_text("failed\n")
        result = asyncio.run(poll_signal_files(tmp_path, poll_interval=0.05))
        assert result == ".failed"

    def test_waits_for_file_to_appear(self, tmp_path: Path) -> None:
        """Polls until a signal file is created by another thread."""

        def _create_after_delay() -> None:
            time.sleep(0.1)
            (tmp_path / ".done").write_text("done\nhttps://pr/1\n")

        threading.Thread(target=_create_after_delay, daemon=True).start()

        result = asyncio.run(poll_signal_files(tmp_path, poll_interval=0.05))
        assert result == ".done"

    def test_custom_filenames(self, tmp_path: Path) -> None:
        """Supports custom signal filenames."""
        (tmp_path / ".merged").write_text("merged\n")
        result = asyncio.run(
            poll_signal_files(
                tmp_path,
                filenames=(".merged", ".cancelled"),
                poll_interval=0.05,
            )
        )
        assert result == ".merged"
