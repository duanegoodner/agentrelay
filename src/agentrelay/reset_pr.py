"""Integration PR mutation protocol and GitHub implementation.

Abstracts the GitHub-specific logic for mutating integration PRs from
the reset command layer.  The :class:`IntegrationPrOps` protocol is
consumed by :mod:`reset_task`, :mod:`reset_workstream`, and
:mod:`reset_to`; the concrete :class:`GhIntegrationPrOps` is constructed
in :mod:`cli` and injected at call time.

Two operations are supported:

* :meth:`IntegrationPrOps.append_reset_activity` — append a
  ``## Reset activity`` entry to the PR body when a task is rolled back.
* :meth:`IntegrationPrOps.close_pr` — close an integration PR when its
  workstream is unmerged or torn down.

Classes:
    IntegrationPrOps: Protocol for integration-PR mutations.
    GhIntegrationPrOps: GitHub implementation via ``gh api`` REST.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from agentrelay.ops import gh


@runtime_checkable
class IntegrationPrOps(Protocol):
    """Integration-PR mutations used by the reset command layer.

    Implementations handle appending reset-activity entries and closing
    integration PRs.  Failures are handled best-effort — callers should
    not expect exceptions.

    Methods:
        append_reset_activity: Append reset entries to a PR body.
        close_pr: Close an integration PR.
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

    def close_pr(self, pr_url: str) -> list[str]:
        """Close an integration PR.

        Args:
            pr_url: Full PR URL.

        Returns:
            List of log messages (single success line, or a warning on
            failure).  No exceptions are raised.
        """
        ...


class GhIntegrationPrOps:
    """GitHub implementation of :class:`IntegrationPrOps`.

    Uses :func:`~agentrelay.ops.gh.pr_body`,
    :func:`~agentrelay.ops.gh.pr_update_body`, and
    :func:`~agentrelay.ops.gh.pr_close_by_url` to mutate the PR via the
    GitHub REST API.  All failures are caught and returned as log
    messages (``WARNING:`` prefix when the mutation fails).
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

    def close_pr(self, pr_url: str) -> list[str]:
        """Close an integration PR (best-effort).

        Args:
            pr_url: Full PR URL.

        Returns:
            List with a single log entry describing the outcome.
        """
        try:
            gh.pr_close_by_url(pr_url)
            return [f"Closed integration PR {pr_url}"]
        except subprocess.CalledProcessError:
            return [
                f"WARNING: Could not close integration PR {pr_url} "
                "(may already be closed)"
            ]
