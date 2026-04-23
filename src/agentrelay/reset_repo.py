"""Repo-level operations for the reset command layer.

This module defines the :class:`RepoResetOps` protocol and its
:class:`GitRepoResetOps` implementation for the git operations that the
reset command layer performs (branch and worktree mutation, rev-parse,
force-push, checkout-in-worktree).  It mirrors :mod:`run_repo` for the
run-lifecycle layer.

Non-worktree methods operate on the repository the implementation is
bound to; worktree-scoped methods take the worktree path explicitly.

Protocols:
    RepoResetOps: Git operations needed by the reset command layer.

Classes:
    GitRepoResetOps: Git-based implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from agentrelay.ops import git


@runtime_checkable
class RepoResetOps(Protocol):
    """Git operations needed by the reset command layer.

    Abstracts the git subprocess wrappers that the reset modules use so
    they do not depend on :mod:`agentrelay.ops.git` directly.  The main
    repository path is held by the implementation; worktree-scoped
    methods take the worktree path explicitly.

    Methods:
        branch_delete: Force-delete a local branch.
        push_delete_branch: Delete a branch on the remote.
        update_local_ref: Move a local branch ref to a target SHA.
        push_force_with_lease: Force-push a branch with lease safety.
        worktree_remove: Forcefully remove a git worktree.
        worktree_prune: Prune stale worktree references.
        rev_parse: Resolve a ref to its SHA.
        checkout_in: Checkout a branch inside a worktree.
        clean_in: Remove untracked files inside a worktree.
        current_branch_in: Current branch name inside a worktree.
    """

    def branch_delete(self, branch: str) -> None:
        """Force-delete a local branch in the main repository."""
        ...

    def push_delete_branch(self, branch: str) -> None:
        """Delete a branch on the remote."""
        ...

    def update_local_ref(self, branch: str, target_sha: str) -> None:
        """Move a local branch ref to *target_sha* via ``git update-ref``."""
        ...

    def push_force_with_lease(self, branch: str) -> None:
        """Force-push *branch* with lease safety."""
        ...

    def worktree_remove(self, worktree_path: Path) -> None:
        """Forcefully remove the worktree at *worktree_path*."""
        ...

    def worktree_prune(self) -> None:
        """Prune stale worktree references in the main repository."""
        ...

    def rev_parse(self, ref: str) -> str:
        """Return the SHA *ref* resolves to in the main repository."""
        ...

    def checkout_in(self, worktree_path: Path, branch: str) -> None:
        """Checkout *branch* inside the worktree at *worktree_path*."""
        ...

    def clean_in(self, worktree_path: Path) -> None:
        """Remove untracked files inside the worktree at *worktree_path*."""
        ...

    def current_branch_in(self, worktree_path: Path) -> Optional[str]:
        """Return the current branch inside *worktree_path*, or ``None``."""
        ...


class GitRepoResetOps:
    """Git-based implementation of :class:`RepoResetOps`.

    Thin delegating wrapper around :mod:`agentrelay.ops.git`.  Holds the
    main repository path; worktree-scoped operations take an explicit
    worktree path.

    Attributes:
        repo_path: Path to the main repository root.
    """

    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path

    def branch_delete(self, branch: str) -> None:
        git.branch_delete(self.repo_path, branch)

    def push_delete_branch(self, branch: str) -> None:
        git.push_delete_branch(self.repo_path, branch)

    def update_local_ref(self, branch: str, target_sha: str) -> None:
        git.update_local_ref(self.repo_path, branch, target_sha)

    def push_force_with_lease(self, branch: str) -> None:
        git.push_force_with_lease(self.repo_path, branch)

    def worktree_remove(self, worktree_path: Path) -> None:
        git.worktree_remove(self.repo_path, worktree_path)

    def worktree_prune(self) -> None:
        git.worktree_prune(self.repo_path)

    def rev_parse(self, ref: str) -> str:
        return git.rev_parse(self.repo_path, ref)

    def checkout_in(self, worktree_path: Path, branch: str) -> None:
        git.checkout(worktree_path, branch)

    def clean_in(self, worktree_path: Path) -> None:
        git.clean(worktree_path)

    def current_branch_in(self, worktree_path: Path) -> Optional[str]:
        return git.current_branch(worktree_path)
