"""Git operations — thin subprocess wrappers for worktree, branch, and remote ops.

Pure subprocess wrappers. No agentrelay domain types — just :class:`~pathlib.Path`
and strings. All functions raise :class:`subprocess.CalledProcessError` on failure
unless documented otherwise.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def worktree_add(
    repo: Path,
    worktree_path: Path,
    branch: str,
    start_point: str,
) -> None:
    """Create a git worktree with a new branch.

    Runs ``git -C <repo> worktree add -b <branch> <path> <start_point>``.
    """
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "worktree",
            "add",
            "-b",
            branch,
            str(worktree_path),
            start_point,
        ],
        check=True,
        capture_output=True,
    )


def worktree_remove(repo: Path, worktree_path: Path) -> None:
    """Forcefully remove a git worktree.

    Runs ``git -C <repo> worktree remove --force <path>``.
    """
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "remove", "--force", str(worktree_path)],
        check=True,
        capture_output=True,
    )


def branch_create(
    repo: Path,
    branch: str,
    start_point: str,
    *,
    force: bool = False,
) -> None:
    """Create a local branch at *start_point*.

    Runs ``git -C <repo> branch [-f] <branch> <start_point>``.
    With ``force=True`` the branch is created or moved if it already exists.
    """
    cmd = ["git", "-C", str(repo), "branch"]
    if force:
        cmd.append("-f")
    cmd.extend([branch, start_point])
    subprocess.run(cmd, check=True, capture_output=True)


def branch_delete(repo: Path, branch: str) -> None:
    """Force-delete a local branch.

    Runs ``git -C <repo> branch -D <branch>``.
    """
    subprocess.run(
        ["git", "-C", str(repo), "branch", "-D", branch],
        check=True,
        capture_output=True,
    )


def pull_ff_only(repo: Path) -> bool:
    """Fast-forward pull on the current branch.

    Runs ``git -C <repo> pull --ff-only``.

    Returns:
        ``True`` if the pull succeeded, ``False`` if fast-forward was not
        possible (e.g. diverged history). Does **not** raise on failure.
    """
    result = subprocess.run(
        ["git", "-C", str(repo), "pull", "--ff-only"],
        capture_output=True,
    )
    return result.returncode == 0


def fetch_branch(repo: Path, branch: str) -> None:
    """Fetch a branch from origin.

    Runs ``git -C <repo> fetch origin <branch>``.
    """
    subprocess.run(
        ["git", "-C", str(repo), "fetch", "origin", branch],
        check=True,
        capture_output=True,
    )


def update_local_ref(repo: Path, branch: str, remote_ref: str) -> None:
    """Update a local branch ref to match a remote ref.

    Runs ``git -C <repo> update-ref refs/heads/<branch> <remote_ref>``.

    This works even when *branch* is currently checked out, unlike the
    ``git fetch origin <branch>:<branch>`` refspec form.
    """
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "update-ref",
            f"refs/heads/{branch}",
            remote_ref,
        ],
        check=True,
        capture_output=True,
    )


def push_branch(repo: Path, branch: str, *, set_upstream: bool = False) -> None:
    """Push a branch to origin.

    Runs ``git -C <repo> push [-u] origin <branch>``.
    """
    cmd = ["git", "-C", str(repo), "push"]
    if set_upstream:
        cmd.append("-u")
    cmd.extend(["origin", branch])
    subprocess.run(cmd, check=True, capture_output=True)


def ls_remote_branch_exists(repo: Path, branch: str) -> bool:
    """Check whether *branch* exists on the remote.

    Runs ``git -C <repo> ls-remote --heads origin refs/heads/<branch>``.

    Returns:
        ``True`` if the branch exists on origin, ``False`` otherwise.
    """
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "ls-remote",
            "--heads",
            "origin",
            f"refs/heads/{branch}",
        ],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())
