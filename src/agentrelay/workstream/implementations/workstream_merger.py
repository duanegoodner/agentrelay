"""Implementations of :class:`~agentrelay.workstream.core.io.WorkstreamMerger`.

Classes:
    GhWorkstreamMerger: Creates and merges a workstream integration PR via
    GitHub CLI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentrelay.ops import gh, git
from agentrelay.workstream.core.runtime import WorkstreamRuntime


@dataclass
class GhWorkstreamMerger:
    """Create and merge the workstream integration PR.

    Creates a pull request from the workstream's integration branch into
    its ``merge_target_branch``, merges it, and updates the local ref to
    match.
    """

    repo_path: Path

    def merge_workstream(self, workstream_runtime: WorkstreamRuntime) -> None:
        """Merge the workstream integration branch into its merge target.

        Args:
            workstream_runtime: Workstream runtime whose integration branch
                should be merged.
        """
        spec = workstream_runtime.spec
        branch_name = workstream_runtime.state.branch_name
        assert branch_name is not None, "branch_name must be set before merge"

        pr_url = gh.pr_create(
            self.repo_path,
            title=f"Integrate workstream {spec.id}",
            body=f"Merge integration branch `{branch_name}` into `{spec.merge_target_branch}`.",
            base=spec.merge_target_branch,
            head=branch_name,
        )
        gh.pr_merge(pr_url)

        git.fetch_branch(self.repo_path, spec.merge_target_branch)
        git.update_local_ref(
            self.repo_path,
            spec.merge_target_branch,
            f"origin/{spec.merge_target_branch}",
        )

        workstream_runtime.artifacts.merge_pr_url = pr_url
