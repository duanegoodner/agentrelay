"""GitHub-based integration merge checker.

Checks whether a workstream's integration PR has been merged on GitHub
by querying the PR state via the GitHub CLI.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentrelay.ops import gh
from agentrelay.workstream.core.runtime import WorkstreamRuntime


@dataclass
class GhIntegrationMergeChecker:
    """Check integration PR merge status via GitHub CLI.

    Reads the merge PR URL from workstream artifacts and delegates
    to :func:`~agentrelay.ops.gh.pr_is_merged`.
    """

    def is_merged(self, workstream_runtime: WorkstreamRuntime) -> bool:
        """Return True if the workstream's integration PR is merged on GitHub.

        Returns ``False`` when no integration PR URL is available.

        Args:
            workstream_runtime: Workstream runtime to check.

        Returns:
            True if the integration PR has been merged.
        """
        pr_url = workstream_runtime.artifacts.merge_pr_url
        if pr_url is None:
            return False
        return gh.pr_is_merged(pr_url)
