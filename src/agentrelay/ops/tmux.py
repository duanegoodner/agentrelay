"""Tmux operations — thin subprocess wrappers for window and pane management.

Pure subprocess wrappers. No agentrelay domain types — just strings and
:class:`~pathlib.Path`. All functions raise :class:`subprocess.CalledProcessError`
on failure unless documented otherwise.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Optional


def has_session(session: str) -> bool:
    """Check whether a tmux session exists.

    Runs ``tmux has-session -t <session>``.

    Returns:
        ``True`` if the session exists, ``False`` otherwise.
    """
    result = subprocess.run(
        ["tmux", "has-session", "-t", session],
        capture_output=True,
    )
    return result.returncode == 0


def current_session() -> Optional[str]:
    """Return the name of the current tmux session, or ``None`` if not in tmux.

    Checks ``$TMUX`` and ``$TMUX_PANE`` environment variables, then
    verifies the process is genuinely inside that tmux pane by comparing
    the current TTY against the pane's TTY.  This prevents false
    positives when a standalone terminal inherits tmux env vars from a
    parent process launched inside tmux (e.g. ``alacritty & disown``).

    Returns ``None`` when the process is not running inside a tmux pane.
    """
    pane = os.environ.get("TMUX_PANE")
    if not os.environ.get("TMUX") or not pane:
        return None

    # Verify our TTY matches the tmux pane's TTY.
    try:
        our_tty = os.ttyname(0)
    except OSError:
        return None
    result = subprocess.run(
        ["tmux", "display-message", "-t", pane, "-p", "#{pane_tty}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    if result.stdout.strip() != our_tty:
        return None

    # Genuinely inside tmux — get the session name.
    result = subprocess.run(
        ["tmux", "display-message", "-p", "#S"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


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
