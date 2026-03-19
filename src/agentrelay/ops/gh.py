"""GitHub CLI operations — thin subprocess wrappers for PR management.

Pure subprocess wrappers. No agentrelay domain types — just strings and
:class:`~pathlib.Path`. All functions raise :class:`subprocess.CalledProcessError`
on failure.
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
