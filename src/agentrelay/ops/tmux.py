"""Tmux operations — thin subprocess wrappers for window and pane management.

Pure subprocess wrappers. No agentrelay domain types — just strings and
:class:`~pathlib.Path`. All functions raise :class:`subprocess.CalledProcessError`
on failure unless documented otherwise.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path


def new_window(session: str, window_name: str, cwd: Path) -> str:
    """Create a tmux window in *session* and return its pane ID.

    Runs ``tmux new-window -t <session> -n <name> -P -F '#{pane_id}' -c <cwd>``.

    Returns:
        The pane ID string (e.g. ``"%42"``).
    """
    result = subprocess.run(
        [
            "tmux",
            "new-window",
            "-t",
            session,
            "-n",
            window_name,
            "-P",
            "-F",
            "#{pane_id}",
            "-c",
            str(cwd),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def send_keys(pane_id: str, keys: str, *, press_enter: bool = True) -> None:
    """Send keystrokes to a tmux pane.

    Runs ``tmux send-keys -t <pane_id> <keys> [Enter]``.

    Args:
        pane_id: Target pane (e.g. ``"%42"``).
        keys: Text to send.
        press_enter: If ``True``, append ``Enter`` to submit.
    """
    cmd = ["tmux", "send-keys", "-t", pane_id, keys]
    if press_enter:
        cmd.append("Enter")
    subprocess.run(cmd, check=True, capture_output=True)


def capture_pane(pane_id: str, *, full_history: bool = False) -> str:
    """Capture the visible content of a tmux pane.

    Runs ``tmux capture-pane -t <pane_id> -p [-S -]``.

    Args:
        pane_id: Target pane.
        full_history: If ``True``, capture the entire scrollback buffer
            (``-S -``), not just the visible area.

    Returns:
        Captured text.
    """
    cmd = ["tmux", "capture-pane", "-t", pane_id, "-p"]
    if full_history:
        cmd.extend(["-S", "-"])
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout


def kill_window(pane_id: str) -> None:
    """Kill a tmux window by pane ID.

    Runs ``tmux kill-window -t <pane_id>``.
    """
    subprocess.run(
        ["tmux", "kill-window", "-t", pane_id],
        check=True,
        capture_output=True,
    )


def wait_for_tui_ready(
    pane_id: str,
    marker: str = "bypass permissions",
    timeout: float = 30.0,
    poll_interval: float = 0.5,
) -> bool:
    """Block until *marker* appears in the pane content.

    Polls :func:`capture_pane` at *poll_interval* seconds until *marker*
    is found (case-insensitive) or *timeout* is reached.

    Returns:
        ``True`` if the marker was found, ``False`` on timeout.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            content = capture_pane(pane_id)
        except subprocess.CalledProcessError:
            pass
        else:
            if marker.lower() in content.lower():
                return True
        time.sleep(poll_interval)
    return False
