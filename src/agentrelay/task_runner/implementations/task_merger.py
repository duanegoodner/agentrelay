"""Implementations of :class:`~agentrelay.task_runner.core.io.TaskMerger`.

Classes:
    GhTaskMerger: Merges a task PR via GitHub CLI and updates local refs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agentrelay.ops import gh, git, signals
from agentrelay.task_runner.core.io import TaskMergeResult
from agentrelay.task_runtime import TaskRuntime


@dataclass
class GhTaskMerger:
    """Merge a task PR via GitHub CLI and update the local integration branch.

    After merging, fetches the updated integration branch and writes a
    ``.merged`` signal file to the task's signal directory.

    Reads ``integration_branch`` from ``runtime.state`` (set by the
    orchestrator before dispatch).
    """

    repo_path: Path

    def merge_pr(self, runtime: TaskRuntime, pr_url: str) -> TaskMergeResult:
        """Merge the completed task PR.

        Captures the integration branch SHA before merging for rollback
        support. Returns a :class:`TaskMergeResult` with the pre-merge SHA.

        Args:
            runtime: Runtime envelope being merged.
            pr_url: Pull request URL to merge.

        Returns:
            TaskMergeResult: Pre-merge SHA of the integration branch.

        Raises:
            ValueError: If ``runtime.state.integration_branch`` is None.
        """
        integration_branch = runtime.state.integration_branch
        if integration_branch is None:
            raise ValueError(
                "runtime.state.integration_branch must be set before merge_pr()"
            )

        before_sha = git.rev_parse(self.repo_path, integration_branch)

        gh.pr_merge(pr_url)

        git.fetch_branch(self.repo_path, integration_branch)
        git.update_local_ref(
            self.repo_path,
            integration_branch,
            f"origin/{integration_branch}",
        )

        if runtime.state.signal_dir is not None:
            timestamp = datetime.now(timezone.utc).isoformat() + "\n"
            signals.write_text(runtime.state.signal_dir, ".merged", timestamp)

        return TaskMergeResult(
            integration_branch_before_merge=before_sha,
        )
