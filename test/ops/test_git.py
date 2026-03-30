"""Tests for agentrelay.ops.git — git subprocess wrappers."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agentrelay.ops.git import (
    branch_create,
    branch_delete,
    branch_list_local,
    current_branch,
    fetch_branch,
    ls_remote_branch_exists,
    pull_ff_only,
    push_branch,
    set_config,
    update_local_ref,
    worktree_add,
    worktree_git_dir,
    worktree_prune,
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


# ── Current branch tests ──


class TestCurrentBranch:
    """Tests for current_branch."""

    def test_returns_branch_name(self, tmp_git_repo: Path) -> None:
        """Returns the current branch name."""
        assert current_branch(tmp_git_repo) == "main"

    def test_returns_branch_after_checkout(self, tmp_git_repo: Path) -> None:
        """Returns the correct branch after switching."""
        branch_create(tmp_git_repo, "feat/test", "main")
        subprocess.run(
            ["git", "-C", str(tmp_git_repo), "checkout", "feat/test"],
            check=True,
            capture_output=True,
        )
        assert current_branch(tmp_git_repo) == "feat/test"

    def test_returns_none_on_detached_head(self, tmp_git_repo: Path) -> None:
        """Returns None when HEAD is detached."""
        sha = _head_sha(tmp_git_repo)
        subprocess.run(
            ["git", "-C", str(tmp_git_repo), "checkout", sha],
            check=True,
            capture_output=True,
        )
        assert current_branch(tmp_git_repo) is None


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


class TestWorktreePrune:
    """Tests for worktree_prune."""

    def test_prunes_stale_worktree(self, tmp_git_repo: Path) -> None:
        """Prunes references to worktrees whose directories were deleted."""
        import shutil

        wt = tmp_git_repo.parent / "worktree"
        worktree_add(tmp_git_repo, wt, "feat/prune-me", "main")
        assert wt.is_dir()

        # Remove directory without git's knowledge.
        shutil.rmtree(wt)

        # Before prune, git still thinks the worktree exists.
        result = subprocess.run(
            ["git", "-C", str(tmp_git_repo), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert "worktree" in result.stdout

        worktree_prune(tmp_git_repo)

        # After prune, the stale reference is cleaned up.
        result = subprocess.run(
            ["git", "-C", str(tmp_git_repo), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        # Only the main worktree should remain.
        worktree_lines = [
            line for line in result.stdout.splitlines() if line.startswith("worktree ")
        ]
        assert len(worktree_lines) == 1

    def test_no_op_when_nothing_to_prune(self, tmp_git_repo: Path) -> None:
        """Does not error when there are no stale worktrees."""
        worktree_prune(tmp_git_repo)


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


class TestBranchListLocal:
    """Tests for branch_list_local."""

    def test_lists_matching_branches(self, tmp_git_repo: Path) -> None:
        """Returns branches matching a glob pattern."""
        branch_create(tmp_git_repo, "agentrelay/graph/task_a", "main")
        branch_create(tmp_git_repo, "agentrelay/graph/task_b", "main")
        branch_create(tmp_git_repo, "agentrelay/other/task_c", "main")

        result = branch_list_local(tmp_git_repo, "agentrelay/graph/*")
        assert sorted(result) == [
            "agentrelay/graph/task_a",
            "agentrelay/graph/task_b",
        ]

    def test_returns_empty_when_no_match(self, tmp_git_repo: Path) -> None:
        """Returns empty list when no branches match."""
        result = branch_list_local(tmp_git_repo, "agentrelay/no-such/*")
        assert result == []

    def test_returns_empty_for_no_branches(self, tmp_git_repo: Path) -> None:
        """Returns empty list when pattern matches nothing."""
        result = branch_list_local(tmp_git_repo, "nonexistent/*")
        assert result == []


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


class TestSetConfig:
    """Tests for set_config."""

    def test_sets_config_value(self, tmp_git_repo: Path) -> None:
        """Sets a git config value in the local repo."""
        set_config(tmp_git_repo, "push.autoSetupRemote", "true")

        result = subprocess.run(
            ["git", "-C", str(tmp_git_repo), "config", "--get", "push.autoSetupRemote"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "true"


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


# ── worktree_git_dir ──


class TestWorktreeGitDir:
    """Tests for worktree_git_dir."""

    def test_resolves_absolute_gitdir(self, tmp_path: Path) -> None:
        """Reads .git file with absolute gitdir and returns main .git/ dir."""
        git_dir = tmp_path / "repo" / ".git"
        git_dir.mkdir(parents=True)
        worktrees_dir = git_dir / "worktrees" / "my-branch"
        worktrees_dir.mkdir(parents=True)

        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        (wt_path / ".git").write_text(f"gitdir: {worktrees_dir}\n")

        result = worktree_git_dir(wt_path)
        assert result == git_dir

    def test_resolves_relative_gitdir(self, tmp_path: Path) -> None:
        """Handles relative gitdir path by resolving against worktree."""
        repo = tmp_path / "repo"
        git_dir = repo / ".git"
        git_dir.mkdir(parents=True)
        worktrees_dir = git_dir / "worktrees" / "my-branch"
        worktrees_dir.mkdir(parents=True)

        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        # Relative path from worktree to gitdir (e.g. ../repo/.git/worktrees/my-branch)
        rel = Path("..") / "repo" / ".git" / "worktrees" / "my-branch"
        (wt_path / ".git").write_text(f"gitdir: {rel}\n")

        result = worktree_git_dir(wt_path)
        assert result == git_dir

    def test_raises_when_git_is_directory(self, tmp_path: Path) -> None:
        """Raises ValueError when .git is a directory (not a worktree)."""
        wt_path = tmp_path / "repo"
        wt_path.mkdir()
        (wt_path / ".git").mkdir()

        with pytest.raises(ValueError, match="not a file"):
            worktree_git_dir(wt_path)

    def test_raises_when_no_gitdir_prefix(self, tmp_path: Path) -> None:
        """Raises ValueError when .git file lacks gitdir: prefix."""
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        (wt_path / ".git").write_text("something unexpected\n")

        with pytest.raises(ValueError, match="does not contain a gitdir line"):
            worktree_git_dir(wt_path)
