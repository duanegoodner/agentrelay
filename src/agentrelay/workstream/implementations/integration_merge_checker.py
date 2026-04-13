"""GitHub-based integration merge checker.

Checks whether a workstream's integration PR has been merged on GitHub
by querying the PR state via the GitHub CLI.  When a merge is detected,
derives the pre-merge target branch SHA from the merge commit's first
parent for rollback support.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentrelay.ops import gh, git
from agentrelay.workstream.core.io import IntegrationMergeCheckResult
from agentrelay.workstream.core.runtime import WorkstreamRuntime


@dataclass
class GhIntegrationMergeChecker:
    """Check integration PR merge status via GitHub CLI.

    Reads the merge PR URL from workstream artifacts and delegates
    to :func:`~agentrelay.ops.gh.pr_is_merged`.  When a merge is detected,
    derives the pre-merge target branch SHA from the merge commit's first
    parent via :func:`~agentrelay.ops.gh.pr_merge_commit_sha` and
    :func:`~agentrelay.ops.git.rev_parse`.
    """

    repo_path: Path

    def is_merged(
        self, workstream_runtime: WorkstreamRuntime
    ) -> IntegrationMergeCheckResult:
        """Check whether the workstream's integration PR is merged on GitHub.

        When the PR is merged, attempts to derive the pre-merge target
        branch SHA from the merge commit's first parent.  Gracefully
        degrades to ``target_branch_before_merge=None`` if the merge
        commit cannot be determined.

        Args:
            workstream_runtime: Workstream runtime to check.

        Returns:
            IntegrationMergeCheckResult: Merge status and pre-merge SHA.
        """
        pr_url = workstream_runtime.artifacts.merge_pr_url
        if pr_url is None:
            return IntegrationMergeCheckResult(merged=False)
        if not gh.pr_is_merged(pr_url):
            return IntegrationMergeCheckResult(merged=False)

        # Derive the target branch SHA from the merge commit's first parent.
        before_sha: str | None = None
        merge_sha = gh.pr_merge_commit_sha(pr_url)
        if merge_sha is not None:
            try:
                before_sha = git.rev_parse(self.repo_path, merge_sha + "^1")
            except Exception:  # noqa: BLE001
                pass  # Graceful degradation — before_sha stays None.

        return IntegrationMergeCheckResult(
            merged=True, target_branch_before_merge=before_sha
        )
