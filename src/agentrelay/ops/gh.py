"""GitHub CLI operations — thin subprocess wrappers for PR management.

Pure subprocess wrappers. No agentrelay domain types — just strings and
:class:`~pathlib.Path`. All functions raise :class:`subprocess.CalledProcessError`
on failure.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


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
