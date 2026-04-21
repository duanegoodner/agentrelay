"""PR body update protocol and GitHub implementation.

Abstracts the GitHub-specific logic for appending reset activity
entries to integration PR bodies.  The :class:`PrBodyUpdater` protocol
is consumed by :mod:`reset_task` and :mod:`reset_workstream`; the
concrete :class:`GhPrBodyUpdater` is constructed in :mod:`cli` and
injected at call time.

Classes:
    PrBodyUpdater: Protocol for appending reset activity to a PR body.
    GhPrBodyUpdater: GitHub implementation via ``gh api`` REST.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from typing import Protocol

from agentrelay.ops import gh


class PrBodyUpdater(Protocol):
    """Append reset activity entries to a pull request body.

    Implementations fetch the current PR body, format and append
    ``## Reset activity`` entries, and update the PR body.  Failures
    are handled best-effort — callers should not expect exceptions.
    """

    def append_reset_activity(
        self, pr_url: str, entries: list[tuple[str, str]]
    ) -> list[str]:
        """Append reset activity entries to a PR body.

        Args:
            pr_url: Full PR URL.
            entries: List of ``(task_id, prior_status)`` tuples.

        Returns:
            List of log messages describing what happened.
        """
        ...


class GhPrBodyUpdater:
    """GitHub implementation of :class:`PrBodyUpdater`.

    Uses :func:`~agentrelay.ops.gh.pr_body` and
    :func:`~agentrelay.ops.gh.pr_update_body` to fetch and update the
    PR body via the GitHub REST API.  All failures are caught and
    returned as warning log messages.
    """

    def append_reset_activity(
        self, pr_url: str, entries: list[tuple[str, str]]
    ) -> list[str]:
        """Append reset activity entries to a PR body.

        Fetches the current body, appends a ``## Reset activity``
        section (or extends an existing one), and updates the PR.

        Args:
            pr_url: Full PR URL.
            entries: List of ``(task_id, prior_status)`` tuples.

        Returns:
            List of log messages.
        """
        if not entries:
            return []

        try:
            current_body = gh.pr_body(pr_url)
            timestamp = datetime.now(timezone.utc).isoformat()
            lines = [
                f"- {timestamp}: Task `{tid}` reset (was {status})"
                for tid, status in entries
            ]
            new_text = "\n".join(lines)

            if "## Reset activity" in current_body:
                new_body = current_body + "\n" + new_text
            else:
                new_body = current_body + "\n\n---\n## Reset activity\n" + new_text

            gh.pr_update_body(pr_url, new_body)
            return [f"Updated integration PR body: {pr_url}"]
        except subprocess.CalledProcessError:
            return [f"WARNING: Could not update integration PR body ({pr_url})"]
