"""Tests for the pre-push git hook that blocks agent pushes to protected branches."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_HOOK_PATH = Path(__file__).parent.parent.parent / "docker" / "hooks" / "pre-push"

# Base env with PATH preserved so bash can find builtins.
_BASE_ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}


def _run_hook(stdin: str, *, is_agent: bool = True) -> subprocess.CompletedProcess[str]:
    """Run the pre-push hook script with controlled input."""
    env = {**_BASE_ENV, "IS_AI_AGENT": "true"} if is_agent else _BASE_ENV
    return subprocess.run(
        ["bash", str(_HOOK_PATH)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
    )


class TestPrePushHook:
    """Tests for docker/hooks/pre-push."""

    def test_blocks_push_to_main(self) -> None:
        """Agent push to refs/heads/main is rejected."""
        result = _run_hook("refs/heads/my_task abc123 refs/heads/main def456\n")
        assert result.returncode != 0
        assert "protected branch" in result.stderr.lower()

    def test_blocks_push_to_master(self) -> None:
        """Agent push to refs/heads/master is rejected."""
        result = _run_hook("refs/heads/my_task abc123 refs/heads/master def456\n")
        assert result.returncode != 0

    def test_allows_push_to_task_branch(self) -> None:
        """Agent push to a task branch is allowed."""
        result = _run_hook(
            "refs/heads/task_a abc123 refs/heads/agentrelay/graph/task_a def456\n"
        )
        assert result.returncode == 0

    def test_allows_push_when_not_agent(self) -> None:
        """Push to main is allowed when IS_AI_AGENT is not set."""
        result = _run_hook(
            "refs/heads/my_task abc123 refs/heads/main def456\n",
            is_agent=False,
        )
        assert result.returncode == 0

    def test_allows_empty_stdin(self) -> None:
        """Empty stdin (no refs) is allowed."""
        result = _run_hook("", is_agent=True)
        assert result.returncode == 0

    def test_blocks_only_protected_in_multi_ref_push(self) -> None:
        """Mixed push with one protected ref is rejected."""
        stdin = (
            "refs/heads/task_a abc123 refs/heads/agentrelay/graph/task_a def456\n"
            "refs/heads/task_a abc123 refs/heads/main def456\n"
        )
        result = _run_hook(stdin)
        assert result.returncode != 0
