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


def worktree_prune(repo: Path) -> None:
    """Prune stale worktree references.

    Runs ``git -C <repo> worktree prune``.
    """
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "prune"],
        check=True,
        capture_output=True,
    )


def checkout(repo: Path, branch: str) -> None:
    """Checkout an existing branch.

    Runs ``git -C <repo> checkout <branch>``.
    """
    subprocess.run(
        ["git", "-C", str(repo), "checkout", branch],
        check=True,
        capture_output=True,
    )


def current_branch(repo: Path) -> str | None:
    """Return the current branch name, or ``None`` if HEAD is detached.

    Runs ``git -C <repo> symbolic-ref --short HEAD``.
    """
    result = subprocess.run(
        ["git", "-C", str(repo), "symbolic-ref", "--short", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


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


def branch_list_local(repo: Path, pattern: str) -> list[str]:
    """List local branches matching a glob pattern.

    Runs ``git -C <repo> branch --list <pattern> --format='%(refname:short)'``.

    Args:
        repo: Repository path.
        pattern: Glob pattern (e.g. ``"agentrelay/mygraph/*"``).

    Returns:
        List of matching branch names (may be empty).
    """
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "branch",
            "--list",
            pattern,
            "--format=%(refname:short)",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return [b for b in result.stdout.strip().split("\n") if b]


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


def push_delete_branch(repo: Path, branch: str) -> None:
    """Delete a branch on the remote.

    Runs ``git -C <repo> push origin --delete <branch>``.
    """
    subprocess.run(
        ["git", "-C", str(repo), "push", "origin", "--delete", branch],
        check=True,
        capture_output=True,
    )


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


def ls_remote_branches(repo: Path, pattern: str) -> list[str]:
    """List remote branches matching a glob *pattern*.

    Runs ``git -C <repo> ls-remote --heads origin <pattern>`` and extracts
    branch names (without the ``refs/heads/`` prefix).

    Returns:
        List of branch names matching the pattern.
    """
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-remote", "--heads", "origin", pattern],
        capture_output=True,
        text=True,
    )
    branches: list[str] = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        ref = line.split("\t", 1)[1]
        branches.append(ref.removeprefix("refs/heads/"))
    return branches


def rev_parse_head(repo: Path) -> str:
    """Return the full SHA of HEAD.

    Runs ``git -C <repo> rev-parse HEAD``.
    """
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def rev_parse(repo: Path, ref: str) -> str:
    """Return the full SHA of an arbitrary ref.

    Runs ``git -C <repo> rev-parse <ref>``.

    Args:
        repo: Path to the repository.
        ref: Any valid git ref (branch name, tag, SHA, ``"abc123^1"``, etc.).

    Returns:
        The resolved full SHA as a string.
    """
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", ref],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def merge_base_is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    """Check whether *ancestor* is an ancestor of *descendant*.

    Runs ``git -C <repo> merge-base --is-ancestor <ancestor> <descendant>``.

    Returns:
        ``True`` if *ancestor* is an ancestor of *descendant*.
    """
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "merge-base",
            "--is-ancestor",
            ancestor,
            descendant,
        ],
        capture_output=True,
    )
    return result.returncode == 0


def reset_hard(repo: Path, ref: str) -> None:
    """Hard-reset *repo* to *ref*.

    Runs ``git -C <repo> reset --hard <ref>``.
    """
    subprocess.run(
        ["git", "-C", str(repo), "reset", "--hard", ref],
        check=True,
        capture_output=True,
    )


def set_config(repo: Path, key: str, value: str) -> None:
    """Set a git config value in the local repo.

    Runs ``git -C <repo> config <key> <value>``.
    """
    subprocess.run(
        ["git", "-C", str(repo), "config", key, value],
        check=True,
        capture_output=True,
    )


def worktree_git_dir(worktree_path: Path) -> Path:
    """Return the main ``.git/`` directory for a git worktree.

    A worktree's ``.git`` is a file containing
    ``gitdir: <repo>/.git/worktrees/<name>``.  This reads that file and
    resolves to the parent ``.git/`` directory two levels up.

    Args:
        worktree_path: Root of the git worktree.

    Returns:
        Absolute path to the main ``.git/`` directory.

    Raises:
        ValueError: If ``.git`` is not a file or does not start with
            ``gitdir:``.
    """
    git_file = worktree_path / ".git"
    if not git_file.is_file():
        raise ValueError(f"{git_file} is not a file (not a worktree?)")
    content = git_file.read_text().strip()
    if not content.startswith("gitdir:"):
        raise ValueError(f"{git_file} does not contain a gitdir line")
    gitdir = Path(content.removeprefix("gitdir:").strip())
    if not gitdir.is_absolute():
        gitdir = (worktree_path / gitdir).resolve()
    # gitdir points to .git/worktrees/<name>; go up two levels to .git/
    return gitdir.parent.parent


def push_force_with_lease(repo: Path, branch: str) -> None:
    """Force-push *branch* to origin with lease safety.

    Runs ``git -C <repo> push --force-with-lease origin <branch>``.
    """
    subprocess.run(
        ["git", "-C", str(repo), "push", "--force-with-lease", "origin", branch],
        check=True,
        capture_output=True,
    )


def rev_list_count(repo: Path, base: str, head: str) -> int:
    """Count commits reachable from *head* but not from *base*.

    Runs ``git -C <repo> rev-list --count <base>..<head>``.

    Returns:
        Number of commits ahead.
    """
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--count", f"{base}..{head}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip())
