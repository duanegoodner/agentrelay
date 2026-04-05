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

from agentrelay.agent_sdk.output_manifest import (
    OUTPUT_MANIFEST_FILENAME,
    OutputAction,
    OutputEntry,
    OutputManifest,
    output_manifest_from_dict,
    output_manifest_to_dict,
)

NO_PR_SENTINEL = "NO_PR"
"""Sentinel value written to ``.done`` when a task completes without a PR."""


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

    def complete_without_pr(self) -> None:
        """Signal task completion without creating a PR.

        Use this when the task produced no code changes (e.g., review-only
        tasks). Writes the ``.done`` signal file with the ``NO_PR`` sentinel
        instead of a PR URL.
        """
        self.mark_done(NO_PR_SENTINEL)

    def complete(
        self,
        *,
        title: str | None = None,
        body: str | None = None,
    ) -> None:
        """Create a PR and signal task completion.

        Call this after committing and pushing all changes. Creates a pull
        request from the task branch to the integration branch, then writes
        the ``.done`` signal file with the PR URL.

        Args:
            title: PR title. Defaults to the task ID.
            body: PR body/description. Defaults to ``"Automated task PR"``.
        """
        pr_url = self.create_pr(title=title, body=body)
        self.mark_done(pr_url)

    def create_pr(
        self,
        *,
        title: str | None = None,
        body: str | None = None,
    ) -> str:
        """Create or reuse a pull request targeting the integration branch.

        If an open PR from this branch to the integration branch already
        exists (e.g. from a previous attempt), reuses it and updates its
        body. Otherwise creates a new PR.

        Automatically appends any recorded concerns as a "Concerns" section
        in the PR body.

        Args:
            title: PR title. Defaults to the task ID.
            body: PR body/description. Defaults to ``"Automated task PR"``.

        Returns:
            The URL of the created (or reused) pull request.

        Raises:
            subprocess.CalledProcessError: If a ``gh`` command fails.
        """
        full_body = body or "Automated task PR"
        concerns = self._read_concerns()
        if concerns:
            concerns_list = "\n".join(f"- {c}" for c in concerns)
            full_body += f"\n\n## Concerns\n\n{concerns_list}"
        ops_concerns = self._read_ops_concerns()
        if ops_concerns:
            ops_list = "\n".join(f"- {c}" for c in ops_concerns)
            full_body += f"\n\n## Ops Concerns\n\n{ops_list}"

        # Check for existing open PR targeting the same base (retry scenario).
        probe = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--head",
                self.branch_name,
                "--base",
                self.integration_branch,
                "--state",
                "open",
                "--json",
                "url",
                "-q",
                ".[0].url",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        existing_url = probe.stdout.strip()

        if existing_url:
            # Update the body via REST API to avoid the gh pr edit GraphQL
            # "Projects (classic)" deprecation error.
            rest_path = existing_url.replace("https://github.com/", "repos/").replace(
                "/pull/", "/pulls/"
            )
            subprocess.run(
                [
                    "gh",
                    "api",
                    rest_path,
                    "-X",
                    "PATCH",
                    "-f",
                    f"body={full_body}",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return existing_url

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
                title or self.task_id,
                "--body",
                full_body,
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

    def record_ops_concern(self, concern: str) -> None:
        """Record an operational concern.

        Appends a line to ``ops_concerns.log`` in the signal directory.
        Ops concerns capture build errors, missing dependencies, tooling
        friction, and similar environmental issues.

        Args:
            concern: Description of the operational concern.
        """
        ops_path = self.signal_dir / "ops_concerns.log"
        with open(ops_path, "a") as f:
            f.write(concern.strip() + "\n")

    def write_summary(self, message: str) -> None:
        """Write a task summary to summary.md.

        Overwrites any existing summary. Use this to record what the task
        accomplished, especially for PR-less tasks where the orchestrator
        cannot derive a summary from a PR body.

        Args:
            message: Summary text (markdown).
        """
        (self.signal_dir / "summary.md").write_text(message)

    # -- Output declarations -----------------------------------------------

    def declare_output(self, path: Path, action: OutputAction, category: str) -> None:
        """Declare a file in the output manifest.

        Appends a single file entry to ``outputs.json`` in the signal
        directory.  Creates the file on first call; subsequent calls
        read-append-write to preserve earlier entries.

        Args:
            path: File path relative to the repository root.
            action: What was done to the file (created, modified, deleted).
            category: Semantic category (e.g. ``"stubs"``, ``"tests"``).
        """
        manifest_path = self.signal_dir / OUTPUT_MANIFEST_FILENAME
        if manifest_path.exists():
            manifest = output_manifest_from_dict(json.loads(manifest_path.read_text()))
        else:
            manifest = OutputManifest()

        manifest.files.append(OutputEntry(path=path, action=action, category=category))

        self.signal_dir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(output_manifest_to_dict(manifest), indent=2) + "\n"
        )

    # -- Internal ----------------------------------------------------------

    def _read_concerns(self) -> list[str]:
        """Read recorded concerns from concerns.log, if it exists."""
        concerns_path = self.signal_dir / "concerns.log"
        if not concerns_path.exists():
            return []
        return [line for line in concerns_path.read_text().splitlines() if line.strip()]

    def _read_ops_concerns(self) -> list[str]:
        """Read recorded ops concerns from ops_concerns.log, if it exists."""
        ops_path = self.signal_dir / "ops_concerns.log"
        if not ops_path.exists():
            return []
        return [line for line in ops_path.read_text().splitlines() if line.strip()]

    def _write_signal(self, name: str, content: str) -> None:
        self.signal_dir.mkdir(parents=True, exist_ok=True)
        (self.signal_dir / name).write_text(content)

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()
