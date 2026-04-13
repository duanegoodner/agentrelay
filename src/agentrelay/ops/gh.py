"""GitHub CLI operations — thin subprocess wrappers for PR management.

Pure subprocess wrappers. No agentrelay domain types — just strings and
:class:`~pathlib.Path`. Most functions raise :class:`subprocess.CalledProcessError`
on failure; :func:`pr_is_merged` is an exception — see its docstring.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def pr_create(
    repo_dir: Path,
    *,
    title: str,
    body: str,
    base: str,
    head: str,
) -> str:
    """Create a pull request and return its URL.

    Runs ``gh pr create --title ... --body ... --base ... --head ...``
    with *repo_dir* as the working directory.

    Returns:
        The PR URL printed by ``gh``.
    """
    result = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--base",
            base,
            "--head",
            head,
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(repo_dir),
    )
    return result.stdout.strip()


def pr_list(
    repo_dir: Path,
    *,
    state: str = "open",
    head_prefix: str | None = None,
) -> list[dict[str, Any]]:
    """List pull requests, optionally filtered by head branch prefix.

    Runs ``gh pr list --json number,headRefName --state <state>``
    in *repo_dir*.

    Args:
        repo_dir: Repository working directory.
        state: PR state filter (``"open"``, ``"closed"``, ``"all"``).
        head_prefix: If given, only return PRs whose ``headRefName``
            starts with this string.

    Returns:
        List of dicts with ``"number"`` and ``"headRefName"`` keys.
    """
    result = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "--state",
            state,
            "--json",
            "number,headRefName",
            "--limit",
            "200",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(repo_dir),
    )
    prs: list[dict[str, Any]] = json.loads(result.stdout)
    if head_prefix is not None:
        prs = [pr for pr in prs if pr["headRefName"].startswith(head_prefix)]
    return prs


def pr_close(repo_dir: Path, pr_number: int) -> None:
    """Close a pull request by number.

    Runs ``gh pr close <number>`` in *repo_dir*.
    """
    subprocess.run(
        ["gh", "pr", "close", str(pr_number)],
        check=True,
        capture_output=True,
        cwd=str(repo_dir),
    )


def pr_merge(pr_url: str) -> None:
    """Merge a pull request using the merge strategy.

    Runs ``gh pr merge <url> --merge``.

    No retry logic — callers are responsible for retry policy.
    """
    subprocess.run(
        ["gh", "pr", "merge", pr_url, "--merge"],
        check=True,
        capture_output=True,
    )


def pr_is_merged(pr_url: str) -> bool:
    """Check whether a pull request has been merged.

    Runs ``gh pr view <url> --json state --jq '.state'``.

    Unlike the other functions in this module, this returns ``False``
    on :class:`subprocess.CalledProcessError` instead of raising.  The
    function is designed for polling loops where transient network or
    CLI failures should not crash the orchestrator.

    Returns:
        ``True`` if the PR state is ``"MERGED"``, ``False`` otherwise.
    """
    try:
        result = subprocess.run(
            ["gh", "pr", "view", pr_url, "--json", "state", "--jq", ".state"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() == "MERGED"
    except subprocess.CalledProcessError:
        return False


def pr_body(pr_url: str) -> str:
    """Fetch the body text of a pull request.

    Runs ``gh pr view <url> --json body --jq '.body'``.

    Returns:
        The PR body as a string.
    """
    result = subprocess.run(
        ["gh", "pr", "view", pr_url, "--json", "body", "--jq", ".body"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def pr_merge_commit_sha(pr_url: str) -> str | None:
    """Return the merge commit SHA for a merged pull request.

    Runs ``gh pr view <url> --json mergeCommit --jq '.mergeCommit.oid'``.

    Like :func:`pr_is_merged`, this returns ``None`` on failure instead of
    raising, making it safe for use in polling loops.

    Returns:
        The merge commit SHA as a string, or ``None`` if the PR is not
        merged or on transient failure.
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                pr_url,
                "--json",
                "mergeCommit",
                "--jq",
                ".mergeCommit.oid",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        sha = result.stdout.strip()
        return sha if sha else None
    except subprocess.CalledProcessError:
        return None
