"""Implementations of :class:`~agentrelay.workstream.core.io.WorkstreamTeardown`.

Classes:
    GitWorkstreamTeardown: Removes worktree and deletes integration branch
    (local and remote).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from agentrelay.ops import git
from agentrelay.workstream.core.runtime import WorkstreamRuntime


@dataclass
class GitWorkstreamTeardown:
    """Clean up workstream worktree and integration branch.

    Performs best-effort cleanup: removes the worktree directory, deletes
    the local integration branch, and deletes the remote integration branch.
    Errors during any step are silently caught so that subsequent cleanup
    steps still execute.
    """

    repo_path: Path

    def teardown_workstream(self, workstream_runtime: WorkstreamRuntime) -> None:
        """Delete worktree and integration branch for this workstream.

        Args:
            workstream_runtime: Workstream runtime whose resources should be
                cleaned up.
        """
        worktree_path = workstream_runtime.state.worktree_path
        branch_name = workstream_runtime.state.branch_name

        if worktree_path is not None:
            try:
                git.worktree_remove(self.repo_path, worktree_path)
            except subprocess.CalledProcessError:
                pass  # Best-effort: worktree may already be gone

        if branch_name is not None:
            try:
                git.branch_delete(self.repo_path, branch_name)
            except subprocess.CalledProcessError:
                pass  # Best-effort: branch may already be deleted

            try:
                git.push_delete_branch(self.repo_path, branch_name)
            except subprocess.CalledProcessError:
                pass  # Best-effort: remote branch may already be gone
