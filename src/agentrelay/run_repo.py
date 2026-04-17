"""Repo-level operations for the run lifecycle layer.

This module defines the ``RunRepoManager`` protocol and its
``GitRunRepoManager`` implementation for repo-level operations that
the run composition layer needs — capturing the current HEAD and
cleaning up worktree branches during resume.

Protocols:
    RunRepoManager: Repo operations for run lifecycle management.

Classes:
    GitRunRepoManager: Git-based implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from agentrelay.ops import git
from agentrelay.task_graph import TaskGraph


@runtime_checkable
class RunRepoManager(Protocol):
    """Repo operations needed by the run lifecycle layer.

    Abstracts the git operations that ``run_graph`` uses so the
    composition layer does not depend on ``ops.git`` directly.

    Methods:
        current_head: Return the current HEAD SHA.
        reset_stale_worktree_branches: Clean up worktrees for resume.
    """

    def current_head(self) -> str:
        """Return the current HEAD SHA of the repository.

        Returns:
            The full commit SHA string.
        """
        ...

    def reset_stale_worktree_branches(
        self,
        graph: TaskGraph,
        frozen_task_ids: set[str],
    ) -> None:
        """Switch worktrees off non-frozen task branches for clean resume.

        When a worktree is checked out on a non-frozen task's branch,
        the task preparer would treat it as a retry (preserving old WIP
        commits).  Switching to the integration branch forces the
        preparer to force-create a clean task branch.

        Args:
            graph: Current graph definition.
            frozen_task_ids: Task IDs that are frozen (should not be
                touched).
        """
        ...


class GitRunRepoManager:
    """Git-based implementation of run lifecycle repo operations.

    Attributes:
        repo_path: Path to the repository root.
        graph_name: Name of the graph (used for branch naming
            conventions and worktree paths).
    """

    def __init__(self, repo_path: Path, graph_name: str) -> None:
        self.repo_path = repo_path
        self.graph_name = graph_name

    def current_head(self) -> str:
        """Return the current HEAD SHA via ``git rev-parse HEAD``.

        Returns:
            The full commit SHA string.
        """
        return git.rev_parse_head(self.repo_path)

    def reset_stale_worktree_branches(
        self,
        graph: TaskGraph,
        frozen_task_ids: set[str],
    ) -> None:
        """Switch worktrees off stale task branches before dispatch.

        Iterates all workstreams in the graph.  For each worktree that
        is checked out on a non-frozen task branch, switches to the
        integration branch and removes untracked files.  This ensures
        new agents get a coherent fresh start rather than seeing partial
        artifacts from an interrupted prior run.

        Args:
            graph: Current graph definition.
            frozen_task_ids: Task IDs that are frozen (should not be
                touched).
        """
        task_branch_prefix = f"agentrelay/{self.graph_name}/"
        for ws_id in graph.workstream_ids():
            worktree_path = self.repo_path / ".worktrees" / self.graph_name / ws_id
            if not worktree_path.is_dir():
                continue

            try:
                current = git.current_branch(worktree_path)
            except Exception:
                continue

            if current is None:
                continue

            # Task branches: agentrelay/<graph>/<task_id> (no further slashes).
            # Integration branches have an extra /integration suffix.
            if not current.startswith(task_branch_prefix):
                continue
            suffix = current[len(task_branch_prefix) :]
            if "/" in suffix:
                continue
            task_id = suffix
            if task_id in frozen_task_ids:
                continue

            # Switch to integration branch and clean untracked files.
            integration_branch = f"agentrelay/{self.graph_name}/{ws_id}/integration"
            git.checkout(worktree_path, integration_branch)
            git.clean(worktree_path)
