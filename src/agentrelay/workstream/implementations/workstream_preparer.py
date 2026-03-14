"""Implementations of :class:`~agentrelay.workstream.core.io.WorkstreamPreparer`.

Classes:
    GitWorkstreamPreparer: Creates a worktree and integration branch for a
    workstream lane.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from agentrelay.errors import WorkspaceIntegrationError
from agentrelay.ops import git
from agentrelay.workstream.core.runtime import WorkstreamRuntime


@dataclass
class GitWorkstreamPreparer:
    """Provision a worktree and integration branch for a workstream lane.

    Creates a git worktree rooted at
    ``<repo_path>/.worktrees/<graph_name>/<workstream_id>`` with a new
    integration branch
    ``agentrelay/<graph_name>/<workstream_id>/integration`` off the
    workstream's ``base_branch``. Pushes the integration branch to origin
    so that task PRs can target it.
    """

    repo_path: Path
    graph_name: str

    def prepare_workstream(self, workstream_runtime: WorkstreamRuntime) -> None:
        """Provision worktree and integration branch for this workstream.

        Args:
            workstream_runtime: Workstream runtime to provision.
        """
        spec = workstream_runtime.spec
        branch_name = f"agentrelay/{self.graph_name}/{spec.id}/integration"
        worktree_path = self.repo_path / ".worktrees" / self.graph_name / spec.id

        try:
            git.worktree_add(
                self.repo_path, worktree_path, branch_name, spec.base_branch
            )
            git.push_branch(self.repo_path, branch_name, set_upstream=True)
        except subprocess.CalledProcessError as exc:
            raise WorkspaceIntegrationError(
                f"Failed to provision workstream {spec.id!r}: {exc}",
            ) from exc

        workstream_runtime.state.worktree_path = worktree_path
        workstream_runtime.state.branch_name = branch_name
