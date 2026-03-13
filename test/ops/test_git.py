"""Tests for agentrelay.ops.git — git subprocess wrappers."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agentrelay.ops.git import (
    branch_create,
    branch_delete,
    fetch_branch,
    ls_remote_branch_exists,
    pull_ff_only,
    push_branch,
    update_local_ref,
    worktree_add,
    worktree_remove,
)

# ── Helpers ──


def _branches(repo: Path) -> list[str]:
    """Return local branch names for *repo*."""
    result = subprocess.run(
        ["git", "-C", str(repo), "branch", "--format=%(refname:short)"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip().splitlines()


def _head_sha(repo: Path) -> str:
    """Return HEAD sha for *repo*."""
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


# ── Worktree tests ──


class TestWorktreeAdd:
    """Tests for worktree_add."""

    def test_creates_worktree_with_new_branch(self, tmp_git_repo: Path) -> None:
        """Creates a worktree directory and a new branch."""
        wt = tmp_git_repo.parent / "worktree"
        worktree_add(tmp_git_repo, wt, "feat/test", "main")

        assert wt.is_dir()
        assert (wt / "README.md").is_file()
        assert "feat/test" in _branches(tmp_git_repo)

    def test_raises_on_existing_branch(self, tmp_git_repo: Path) -> None:
        """Raises when the branch already exists."""
        branch_create(tmp_git_repo, "existing", "main")
        wt = tmp_git_repo.parent / "worktree"

        with pytest.raises(subprocess.CalledProcessError):
            worktree_add(tmp_git_repo, wt, "existing", "main")


class TestWorktreeRemove:
    """Tests for worktree_remove."""

    def test_removes_worktree_directory(self, tmp_git_repo: Path) -> None:
        """Removes the worktree directory."""
        wt = tmp_git_repo.parent / "worktree"
        worktree_add(tmp_git_repo, wt, "feat/remove-me", "main")
        assert wt.is_dir()

        worktree_remove(tmp_git_repo, wt)
        assert not wt.exists()

    def test_raises_on_nonexistent_worktree(self, tmp_git_repo: Path) -> None:
        """Raises when worktree path does not exist."""
        wt = tmp_git_repo.parent / "no-such-worktree"
        with pytest.raises(subprocess.CalledProcessError):
            worktree_remove(tmp_git_repo, wt)


# ── Branch tests ──


class TestBranchCreate:
    """Tests for branch_create."""

    def test_creates_branch(self, tmp_git_repo: Path) -> None:
        """Creates a new local branch."""
        branch_create(tmp_git_repo, "feat/new", "main")
        assert "feat/new" in _branches(tmp_git_repo)

    def test_force_moves_existing_branch(self, tmp_git_repo: Path) -> None:
        """With force=True, moves an existing branch to a new start point."""
        branch_create(tmp_git_repo, "feat/movable", "main")
        sha_before = _head_sha(tmp_git_repo)

        # Create a second commit on main.
        (tmp_git_repo / "extra.txt").write_text("extra\n")
        subprocess.run(
            ["git", "-C", str(tmp_git_repo), "add", "extra.txt"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_git_repo), "commit", "-m", "second"],
            check=True,
            capture_output=True,
        )
        sha_after = _head_sha(tmp_git_repo)
        assert sha_before != sha_after

        branch_create(tmp_git_repo, "feat/movable", "main", force=True)
        # Branch should now point at the new HEAD.
        result = subprocess.run(
            ["git", "-C", str(tmp_git_repo), "rev-parse", "feat/movable"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == sha_after

    def test_raises_without_force_on_existing(self, tmp_git_repo: Path) -> None:
        """Raises when branch exists and force=False."""
        branch_create(tmp_git_repo, "feat/dup", "main")
        with pytest.raises(subprocess.CalledProcessError):
            branch_create(tmp_git_repo, "feat/dup", "main")


class TestBranchDelete:
    """Tests for branch_delete."""

    def test_deletes_branch(self, tmp_git_repo: Path) -> None:
        """Deletes an existing local branch."""
        branch_create(tmp_git_repo, "feat/delete-me", "main")
        assert "feat/delete-me" in _branches(tmp_git_repo)

        branch_delete(tmp_git_repo, "feat/delete-me")
        assert "feat/delete-me" not in _branches(tmp_git_repo)

    def test_raises_on_nonexistent_branch(self, tmp_git_repo: Path) -> None:
        """Raises when branch does not exist."""
        with pytest.raises(subprocess.CalledProcessError):
            branch_delete(tmp_git_repo, "no-such-branch")


# ── Remote-requiring tests ──


class TestPullFfOnly:
    """Tests for pull_ff_only."""

    def test_returns_true_on_fast_forward(
        self, tmp_git_repo_with_remote: tuple[Path, Path]
    ) -> None:
        """Returns True when pull fast-forwards successfully."""
        clone, bare = tmp_git_repo_with_remote

        # Create a second clone, commit, push — so origin is ahead.
        clone2 = clone.parent / "clone2"
        subprocess.run(
            ["git", "clone", str(bare), str(clone2)], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(clone2), "config", "user.email", "t@t.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(clone2), "config", "user.name", "T"],
            check=True,
            capture_output=True,
        )
        (clone2 / "new.txt").write_text("new\n")
        subprocess.run(
            ["git", "-C", str(clone2), "add", "new.txt"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(clone2), "commit", "-m", "ahead"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(clone2), "push"], check=True, capture_output=True
        )

        assert pull_ff_only(clone) is True
        assert (clone / "new.txt").is_file()

    def test_returns_false_on_diverged(
        self, tmp_git_repo_with_remote: tuple[Path, Path]
    ) -> None:
        """Returns False when histories have diverged."""
        clone, bare = tmp_git_repo_with_remote

        # Commit locally.
        (clone / "local.txt").write_text("local\n")
        subprocess.run(
            ["git", "-C", str(clone), "add", "local.txt"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(clone), "commit", "-m", "local"],
            check=True,
            capture_output=True,
        )

        # Push a different commit from another clone.
        clone2 = clone.parent / "clone2"
        subprocess.run(
            ["git", "clone", str(bare), str(clone2)], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(clone2), "config", "user.email", "t@t.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(clone2), "config", "user.name", "T"],
            check=True,
            capture_output=True,
        )
        (clone2 / "remote.txt").write_text("remote\n")
        subprocess.run(
            ["git", "-C", str(clone2), "add", "remote.txt"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(clone2), "commit", "-m", "remote"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(clone2), "push"], check=True, capture_output=True
        )

        assert pull_ff_only(clone) is False


class TestFetchBranch:
    """Tests for fetch_branch."""

    def test_fetches_remote_branch(
        self, tmp_git_repo_with_remote: tuple[Path, Path]
    ) -> None:
        """Fetches a branch from origin and updates tracking ref."""
        clone, bare = tmp_git_repo_with_remote

        # Push a new branch from a second clone.
        clone2 = clone.parent / "clone2"
        subprocess.run(
            ["git", "clone", str(bare), str(clone2)], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(clone2), "config", "user.email", "t@t.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(clone2), "config", "user.name", "T"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(clone2), "checkout", "-b", "feat/remote-branch"],
            check=True,
            capture_output=True,
        )
        (clone2 / "feature.txt").write_text("feat\n")
        subprocess.run(
            ["git", "-C", str(clone2), "add", "feature.txt"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(clone2), "commit", "-m", "feature"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(clone2), "push", "-u", "origin", "feat/remote-branch"],
            check=True,
            capture_output=True,
        )

        # Fetch in original clone — should not raise.
        fetch_branch(clone, "feat/remote-branch")

        # Verify the ref exists locally.
        result = subprocess.run(
            ["git", "-C", str(clone), "rev-parse", "origin/feat/remote-branch"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0


class TestUpdateLocalRef:
    """Tests for update_local_ref."""

    def test_updates_local_branch_to_remote_ref(
        self, tmp_git_repo_with_remote: tuple[Path, Path]
    ) -> None:
        """Updates a local branch ref to match a remote tracking ref."""
        clone, bare = tmp_git_repo_with_remote

        # Advance origin/main from a second clone.
        clone2 = clone.parent / "clone2"
        subprocess.run(
            ["git", "clone", str(bare), str(clone2)], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(clone2), "config", "user.email", "t@t.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(clone2), "config", "user.name", "T"],
            check=True,
            capture_output=True,
        )
        (clone2 / "update.txt").write_text("update\n")
        subprocess.run(
            ["git", "-C", str(clone2), "add", "update.txt"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(clone2), "commit", "-m", "update"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(clone2), "push"], check=True, capture_output=True
        )

        # Fetch in original clone so origin/main is updated.
        subprocess.run(
            ["git", "-C", str(clone), "fetch", "origin"],
            check=True,
            capture_output=True,
        )

        old_sha = _head_sha(clone)
        remote_sha = subprocess.run(
            ["git", "-C", str(clone), "rev-parse", "origin/main"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert old_sha != remote_sha

        # update-ref should work even though main is checked out.
        update_local_ref(clone, "main", "origin/main")
        assert _head_sha(clone) == remote_sha


class TestPushBranch:
    """Tests for push_branch."""

    def test_pushes_branch_to_origin(
        self, tmp_git_repo_with_remote: tuple[Path, Path]
    ) -> None:
        """Pushes a local branch to origin."""
        clone, _bare = tmp_git_repo_with_remote

        subprocess.run(
            ["git", "-C", str(clone), "checkout", "-b", "feat/push-test"],
            check=True,
            capture_output=True,
        )
        (clone / "pushed.txt").write_text("pushed\n")
        subprocess.run(
            ["git", "-C", str(clone), "add", "pushed.txt"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(clone), "commit", "-m", "push test"],
            check=True,
            capture_output=True,
        )

        push_branch(clone, "feat/push-test", set_upstream=True)

        # Verify on remote.
        assert ls_remote_branch_exists(clone, "feat/push-test")


class TestLsRemoteBranchExists:
    """Tests for ls_remote_branch_exists."""

    def test_returns_true_for_existing_branch(
        self, tmp_git_repo_with_remote: tuple[Path, Path]
    ) -> None:
        """Returns True for a branch that exists on origin."""
        clone, _bare = tmp_git_repo_with_remote
        assert ls_remote_branch_exists(clone, "main") is True

    def test_returns_false_for_nonexistent_branch(
        self, tmp_git_repo_with_remote: tuple[Path, Path]
    ) -> None:
        """Returns False for a branch that does not exist on origin."""
        clone, _bare = tmp_git_repo_with_remote
        assert ls_remote_branch_exists(clone, "no-such-branch") is False
