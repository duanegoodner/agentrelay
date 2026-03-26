"""GitHub-based integration auto-merger.

Merges a workstream's integration PR on GitHub via the GitHub CLI.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentrelay.ops import gh
from agentrelay.workstream.core.runtime import WorkstreamRuntime


@dataclass
class GhIntegrationAutoMerger:
    """Merge a workstream's integration PR via GitHub CLI.

    Reads the merge PR URL from workstream artifacts and delegates
    to :func:`~agentrelay.ops.gh.pr_merge`.
    """

    def merge(self, workstream_runtime: WorkstreamRuntime) -> None:
        """Merge the integration PR for this workstream.

        Raises:
            RuntimeError: If no integration PR URL is available.
            subprocess.CalledProcessError: If the ``gh pr merge`` call fails.
        """
        pr_url = workstream_runtime.artifacts.merge_pr_url
        if pr_url is None:
            raise RuntimeError("No integration PR URL available for auto-merge")
        gh.pr_merge(pr_url)
