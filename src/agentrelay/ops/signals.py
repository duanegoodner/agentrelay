"""Signal directory operations — filesystem I/O for task coordination.

Pure filesystem wrappers for reading/writing signal files used by the
task completion protocol. No agentrelay domain types — just paths,
strings, and dicts.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any


def ensure_signal_dir(signal_dir: Path) -> Path:
    """Create *signal_dir* and parents if they don't exist.

    Returns:
        The *signal_dir* path (for chaining convenience).
    """
    signal_dir.mkdir(parents=True, exist_ok=True)
    return signal_dir


def write_json(signal_dir: Path, filename: str, data: dict[str, Any]) -> None:
    """Write *data* as formatted JSON to *signal_dir/filename*.

    Creates *signal_dir* if it doesn't exist.
    """
    ensure_signal_dir(signal_dir)
    (signal_dir / filename).write_text(json.dumps(data, indent=2) + "\n")


def write_text(signal_dir: Path, filename: str, content: str) -> None:
    """Write *content* as text to *signal_dir/filename*.

    Creates *signal_dir* if it doesn't exist.
    """
    ensure_signal_dir(signal_dir)
    (signal_dir / filename).write_text(content)


def read_signal_file(signal_dir: Path, filename: str) -> str | None:
    """Read *signal_dir/filename* and return its contents.

    Returns:
        File contents as a string, or ``None`` if the file doesn't exist.
    """
    path = signal_dir / filename
    if not path.is_file():
        return None
    return path.read_text()


async def poll_signal_files(
    signal_dir: Path,
    filenames: tuple[str, ...] = (".done", ".failed"),
    poll_interval: float = 2.0,
) -> str:
    """Async-poll *signal_dir* until any of *filenames* appears.

    Returns:
        The filename that was found (e.g. ``".done"`` or ``".failed"``).
    """
    while True:
        for filename in filenames:
            if (signal_dir / filename).is_file():
                return filename
        await asyncio.sleep(poll_interval)
