"""Implementations of :class:`~agentrelay.workstream.core.io.WorkstreamPreparer`.

Classes:
    GitWorkstreamPreparer: Creates a worktree and integration branch for a
    workstream lane.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from agentrelay.errors import _WorkspaceIntegrationError
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
    run_dir: Path

    def prepare_workstream(self, workstream_runtime: WorkstreamRuntime) -> None:
        """Provision worktree and integration branch for this workstream.

        Args:
            workstream_runtime: Workstream runtime to provision.
        """
        spec = workstream_runtime.spec
        branch_name = f"agentrelay/{self.graph_name}/{spec.id}/integration"
        worktree_path = self.repo_path / ".worktrees" / self.graph_name / spec.id

        if worktree_path.is_dir():
            # Resume scenario: worktree already exists from a prior run.
            # Skip git operations — the integration branch and config are
            # already in place.
            pass
        else:
            try:
                # Ensure the base branch is current before creating the
                # worktree.  Integration PR merges happen on the remote; the
                # local ref may be stale unless we fetch + update before
                # branching from it.
                git.fetch_branch(self.repo_path, spec.base_branch)
                git.update_local_ref(
                    self.repo_path,
                    spec.base_branch,
                    f"origin/{spec.base_branch}",
                )

                # Check if the integration branch already exists (e.g.,
                # after reset-to rolled back the branch but didn't delete
                # it, and the prior run's teardown removed the worktree).
                branch_exists = False
                try:
                    git.rev_parse(self.repo_path, branch_name)
                    branch_exists = True
                except subprocess.CalledProcessError:
                    pass

                if branch_exists:
                    # Reuse existing branch — create worktree without -b.
                    git.worktree_add_existing(
                        self.repo_path, worktree_path, branch_name
                    )
                else:
                    git.worktree_add(
                        self.repo_path,
                        worktree_path,
                        branch_name,
                        spec.base_branch,
                    )
                    git.push_branch(self.repo_path, branch_name, set_upstream=True)
                git.set_config(worktree_path, "push.autoSetupRemote", "true")
            except subprocess.CalledProcessError as exc:
                raise _WorkspaceIntegrationError(
                    f"Failed to provision workstream {spec.id!r}: {exc}",
                ) from exc

        signal_dir = self.run_dir / "workstreams" / spec.id
        workstream_runtime.state.signal_dir = signal_dir
        workstream_runtime.state.worktree_path = worktree_path
        workstream_runtime.state.branch_name = branch_name
        workstream_runtime.mark_pending()
