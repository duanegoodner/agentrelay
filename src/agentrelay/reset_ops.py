"""Shared reset utilities for stack-based undo operations.

Stateless building blocks composed by the primitive undo commands
(:mod:`reset_task`, :mod:`reset_workstream`) and the batch rollback
command (``reset-to``).  Each function performs a targeted cleanup
operation using :mod:`ops.git` subprocess wrappers.

Functions:
    reset_branch: Reset a branch to a target SHA and force-push.
    delete_task_state: Remove a task's signal directory and branches.
    delete_workstream_state: Remove a workstream's worktree, branches,
        and signal directory.
    find_workstream_tip: Find the most recently touched task in a
        workstream.
    workstream_merge_order: Determine the merge order of workstreams on
        their target branch.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from agentrelay.ops import git
from agentrelay.resolved import ResolvedWorkstream
from agentrelay.task_graph import TaskGraph

_BRANCH_PREFIX = "agentrelay"


def reset_branch(repo_path: Path, branch: str, target_sha: str) -> None:
    """Reset a branch to a target SHA and force-push.

    Uses ``git update-ref`` to move the branch pointer, which works even
    when the branch is checked out in a worktree (unlike ``git branch -f``).
    Then force-pushes with lease safety.

    Args:
        repo_path: Path to the repository root.
        branch: Branch name to reset.
        target_sha: SHA to reset the branch to (from ``resolved.json``).
    """
    git.update_local_ref(repo_path, branch, target_sha)
    git.push_force_with_lease(repo_path, branch)


def delete_task_state(
    run_dir: Path,
    task_id: str,
    graph_name: str,
    repo_path: Path,
) -> list[str]:
    """Remove a task's signal directory and branches.

    Performs best-effort cleanup: missing signal directories are skipped,
    and branch deletion failures are caught silently.

    Args:
        run_dir: Path to the per-run directory.
        task_id: Task identifier.
        graph_name: Graph name (for branch naming convention).
        repo_path: Path to the repository root.

    Returns:
        List of log messages describing actions taken.
    """
    log: list[str] = []

    signal_dir = run_dir / "signals" / task_id
    if signal_dir.is_dir():
        shutil.rmtree(signal_dir)
        log.append(f"Removed signal directory for task '{task_id}'")

    branch = f"{_BRANCH_PREFIX}/{graph_name}/{task_id}"

    try:
        git.branch_delete(repo_path, branch)
        log.append(f"Deleted local branch {branch}")
    except subprocess.CalledProcessError:
        pass  # Best-effort: branch may already be deleted

    try:
        git.push_delete_branch(repo_path, branch)
        log.append(f"Deleted remote branch {branch}")
    except subprocess.CalledProcessError:
        pass  # Best-effort: remote branch may already be gone

    return log


def delete_workstream_state(
    run_dir: Path,
    ws_id: str,
    graph_name: str,
    repo_path: Path,
) -> list[str]:
    """Remove a workstream's worktree, branches, and signal directory.

    Performs best-effort cleanup at each step so that subsequent steps
    still execute even if an earlier one fails.

    Args:
        run_dir: Path to the per-run directory.
        ws_id: Workstream identifier.
        graph_name: Graph name (for path and branch naming conventions).
        repo_path: Path to the repository root.

    Returns:
        List of log messages describing actions taken.
    """
    log: list[str] = []

    worktree_path = repo_path / ".worktrees" / graph_name / ws_id
    if worktree_path.is_dir():
        try:
            git.worktree_remove(repo_path, worktree_path)
            log.append(f"Removed worktree {worktree_path}")
        except subprocess.CalledProcessError:
            # Worktree may be in a broken state — fall back to rmtree.
            try:
                shutil.rmtree(worktree_path)
                log.append(f"Removed worktree directory {worktree_path} (fallback)")
            except OSError:
                log.append(f"WARNING: Cannot remove worktree {worktree_path}")

    branch = f"{_BRANCH_PREFIX}/{graph_name}/{ws_id}/integration"

    try:
        git.branch_delete(repo_path, branch)
        log.append(f"Deleted local branch {branch}")
    except subprocess.CalledProcessError:
        pass  # Best-effort

    try:
        git.push_delete_branch(repo_path, branch)
        log.append(f"Deleted remote branch {branch}")
    except subprocess.CalledProcessError:
        pass  # Best-effort

    signal_dir = run_dir / "workstreams" / ws_id
    if signal_dir.is_dir():
        shutil.rmtree(signal_dir)
        log.append(f"Removed workstream signal directory for '{ws_id}'")

    try:
        git.worktree_prune(repo_path)
    except subprocess.CalledProcessError:
        pass  # Best-effort

    return log


def find_workstream_tip(
    run_dir: Path,
    graph: TaskGraph,
    ws_id: str,
) -> str | None:
    """Find the most recently touched task in a workstream.

    Tasks within a workstream execute sequentially in topological order.
    The "tip" is the last task in that order whose signal directory
    exists on disk.

    Args:
        run_dir: Path to the per-run directory.
        graph: Current task graph.
        ws_id: Workstream identifier.

    Returns:
        Task ID of the tip, or ``None`` if no task has a signal directory.
    """
    tip: str | None = None
    for task_id in graph.tasks_in_workstream(ws_id):
        if (run_dir / "signals" / task_id).is_dir():
            tip = task_id
    return tip


def workstream_merge_order(
    run_dir: Path,
    graph: TaskGraph,
) -> list[str]:
    """Determine the merge order of workstreams on their target branch.

    Reads ``resolved.json`` for each workstream and returns those with
    ``merge_occurred=True``, sorted by ``merged_at`` timestamp (oldest
    first).

    Args:
        run_dir: Path to the per-run directory.
        graph: Current task graph.

    Returns:
        List of workstream IDs in merge order (oldest first).
    """
    merged: list[tuple[str, str]] = []  # (merged_at, ws_id)
    for ws_id in graph.workstream_ids():
        resolved_path = run_dir / "workstreams" / ws_id / "resolved.json"
        if not resolved_path.is_file():
            continue
        try:
            data = json.loads(resolved_path.read_text())
            resolved = ResolvedWorkstream.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            continue
        if resolved.merge_occurred and resolved.merged_at is not None:
            merged.append((resolved.merged_at, ws_id))
    merged.sort(key=lambda x: x[0])
    return [ws_id for _, ws_id in merged]
