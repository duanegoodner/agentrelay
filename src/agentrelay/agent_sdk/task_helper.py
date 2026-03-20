"""Agent-side task helper for orchestrator interaction.

Provides :class:`TaskHelper`, a class that agents instantiate inside their
tmux session to manage the mechanical parts of the workflow: PR creation,
completion signaling, and concern recording. Reads task metadata from
``manifest.json`` in ``$AGENTRELAY_SIGNAL_DIR``.

Usage from an agent::

    from agentrelay.agent_sdk import TaskHelper

    helper = TaskHelper.from_env()
    # ... do work, commit, push ...
    helper.complete()
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


class TaskHelper:
    """Agent-side helper for task workflow interaction.

    Encapsulates signal file I/O, PR creation, and concern recording so
    agents don't need to know protocol details.

    Use :meth:`from_env` to construct from the environment.
    """

    def __init__(
        self,
        signal_dir: Path,
        task_id: str,
        branch_name: str,
        integration_branch: str,
    ) -> None:
        self.signal_dir = signal_dir
        self.task_id = task_id
        self.branch_name = branch_name
        self.integration_branch = integration_branch

    @classmethod
    def from_env(cls) -> TaskHelper:
        """Construct from ``$AGENTRELAY_SIGNAL_DIR`` and its ``manifest.json``.

        Raises:
            KeyError: If ``AGENTRELAY_SIGNAL_DIR`` is not set.
            FileNotFoundError: If ``manifest.json`` does not exist.
        """
        signal_dir = Path(os.environ["AGENTRELAY_SIGNAL_DIR"])
        manifest = json.loads((signal_dir / "manifest.json").read_text())
        return cls(
            signal_dir=signal_dir,
            task_id=manifest["task"]["id"],
            branch_name=manifest["workspace"]["branch_name"],
            integration_branch=manifest["workspace"]["integration_branch"],
        )

    # -- Completion workflow ------------------------------------------------

    def complete(self) -> None:
        """Create a PR and signal task completion.

        Call this after committing and pushing all changes. Creates a pull
        request from the task branch to the integration branch, then writes
        the ``.done`` signal file with the PR URL.
        """
        pr_url = self.create_pr()
        self.mark_done(pr_url)

    def create_pr(self) -> str:
        """Create a pull request targeting the integration branch.

        Returns:
            The URL of the created pull request.

        Raises:
            subprocess.CalledProcessError: If ``gh pr create`` fails.
        """
        result = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--base",
                self.integration_branch,
                "--head",
                self.branch_name,
                "--title",
                self.task_id,
                "--body",
                "Automated task PR",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def mark_done(self, pr_url: str) -> None:
        """Write the ``.done`` signal file.

        Args:
            pr_url: URL of the pull request created for this task.
        """
        self._write_signal(".done", f"{self._timestamp()}\n{pr_url}")

    def mark_failed(self, reason: str) -> None:
        """Write the ``.failed`` signal file.

        Args:
            reason: Human-readable reason for the failure.
        """
        self._write_signal(".failed", f"{self._timestamp()}\n{reason}")

    # -- Observations ------------------------------------------------------

    def record_concern(self, concern: str) -> None:
        """Record a design concern.

        Appends a line to ``concerns.log`` in the signal directory. The
        orchestrator reads this file after task completion.

        Args:
            concern: Description of the concern.
        """
        concerns_path = self.signal_dir / "concerns.log"
        with open(concerns_path, "a") as f:
            f.write(concern.strip() + "\n")

    # -- Internal ----------------------------------------------------------

    def _write_signal(self, name: str, content: str) -> None:
        self.signal_dir.mkdir(parents=True, exist_ok=True)
        (self.signal_dir / name).write_text(content)

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()
