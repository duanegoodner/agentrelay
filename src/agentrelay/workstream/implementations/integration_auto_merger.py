"""GitHub-based integration auto-merger.

Merges a workstream's integration PR on GitHub via the GitHub CLI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentrelay.ops import gh, git
from agentrelay.workstream.core.io import IntegrationMergeResult
from agentrelay.workstream.core.runtime import WorkstreamRuntime


@dataclass
class GhIntegrationAutoMerger:
    """Merge a workstream's integration PR via GitHub CLI.

    Captures the target branch SHA before merging for rollback support.
    Reads the merge PR URL from workstream artifacts and delegates
    to :func:`~agentrelay.ops.gh.pr_merge`.
    """

    repo_path: Path

    def merge(self, workstream_runtime: WorkstreamRuntime) -> IntegrationMergeResult:
        """Merge the integration PR for this workstream.

        Returns:
            IntegrationMergeResult: Pre-merge SHA of the target branch.

        Raises:
            RuntimeError: If no integration PR URL is available.
            subprocess.CalledProcessError: If the ``gh pr merge`` call fails.
        """
        pr_url = workstream_runtime.artifacts.merge_pr_url
        if pr_url is None:
            raise RuntimeError("No integration PR URL available for auto-merge")

        target_branch = workstream_runtime.spec.merge_target_branch
        before_sha = git.rev_parse(self.repo_path, target_branch)

        gh.pr_merge(pr_url)

        return IntegrationMergeResult(target_branch_before_merge=before_sha)
