"""Shared test fixtures for agentrelay tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _git(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    """Run a git command with check=True and captured output."""
    return subprocess.run(["git", *args], check=True, capture_output=True)


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository with one commit.

    Returns the repo root path.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main", str(repo)])
    _git(["-C", str(repo), "config", "user.email", "test@test.com"])
    _git(["-C", str(repo), "config", "user.name", "Test"])
    (repo / "README.md").write_text("# test\n")
    _git(["-C", str(repo), "add", "README.md"])
    _git(["-C", str(repo), "commit", "-m", "initial"])
    return repo


@pytest.fixture
def tmp_git_repo_with_remote(tmp_path: Path) -> tuple[Path, Path]:
    """Create a bare remote and a clone. Returns (clone_path, bare_path)."""
    bare = tmp_path / "remote.git"
    _git(["init", "--bare", "-b", "main", str(bare)])

    clone = tmp_path / "clone"
    _git(["clone", str(bare), str(clone)])
    _git(["-C", str(clone), "config", "user.email", "test@test.com"])
    _git(["-C", str(clone), "config", "user.name", "Test"])

    # Create an initial commit so the clone has a main branch.
    (clone / "README.md").write_text("# test\n")
    _git(["-C", str(clone), "add", "README.md"])
    _git(["-C", str(clone), "commit", "-m", "initial"])
    _git(["-C", str(clone), "push", "-u", "origin", "main"])

    return clone, bare
