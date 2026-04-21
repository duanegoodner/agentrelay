"""Shared reset utilities for stack-based undo operations.

Stateless building blocks composed by the primitive undo commands
(:mod:`reset_task`, :mod:`reset_workstream`) and the batch rollback
command (``reset-to``).  Each function performs a targeted cleanup
operation using :mod:`ops.git` subprocess wrappers.

Functions:
    reset_branch: Reset a branch to a target SHA and force-push.
    reset_task_state: Mark a task as RESET and delete its branches.
    reset_workstream_state: Mark a workstream as RESET, remove worktree,
        and delete its branches.
    find_workstream_tip: Find the most recently touched task in a
        workstream (excluding RESET tasks).
    workstream_merge_order: Determine the merge order of workstreams on
        their target branch (excluding RESET workstreams).
    write_rollback_entry: Append a timestamped entry to the workstream
        rollback log (``rollback_log.json``).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from agentrelay.ops import git
from agentrelay.resolved import ResolvedWorkstream
from agentrelay.task_graph import TaskGraph
from agentrelay.task_runtime import TaskStatus
from agentrelay.task_runtime.runtime import _read_task_status_from_signals
from agentrelay.workstream.core.runtime import (
    WorkstreamStatus,
    _read_status_from_signals,
)

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


def reset_task_state(
    run_dir: Path,
    task_id: str,
    graph_name: str,
    repo_path: Path,
) -> list[str]:
    """Mark a task as RESET and delete its branches.

    Writes ``status/reset`` to the task signal directory (preserving all
    prior artifacts for history) and deletes the task branch.  Best-effort:
    missing signal directories are skipped, and branch deletion failures
    are caught silently.

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
        status_dir = signal_dir / "status"
        status_dir.mkdir(parents=True, exist_ok=True)
        (status_dir / "reset").write_text("")
        log.append(f"Marked task '{task_id}' as RESET")

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


def reset_workstream_state(
    run_dir: Path,
    ws_id: str,
    graph_name: str,
    repo_path: Path,
) -> list[str]:
    """Mark a workstream as RESET, remove worktree, and delete branches.

    Writes a ``reset`` signal file to the workstream signal directory
    (preserving all prior artifacts for history), removes the worktree,
    and deletes the integration branch.  Best-effort at each step.

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
        (signal_dir / "reset").write_text("")
        log.append(f"Marked workstream '{ws_id}' as RESET")

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
    exists on disk and whose status is not ``RESET``.

    Args:
        run_dir: Path to the per-run directory.
        graph: Current task graph.
        ws_id: Workstream identifier.

    Returns:
        Task ID of the tip, or ``None`` if no active task has a signal
        directory.
    """
    tip: str | None = None
    for task_id in graph.tasks_in_workstream(ws_id):
        signal_dir = run_dir / "signals" / task_id
        if signal_dir.is_dir():
            status = _read_task_status_from_signals(signal_dir)
            if status != TaskStatus.RESET:
                tip = task_id
    return tip


def workstream_merge_order(
    run_dir: Path,
    graph: TaskGraph,
) -> list[str]:
    """Determine the merge order of workstreams on their target branch.

    Reads ``resolved.json`` for each workstream and returns those with
    ``merge_occurred=True`` and status not ``RESET``, sorted by
    ``merged_at`` timestamp (oldest first).

    Args:
        run_dir: Path to the per-run directory.
        graph: Current task graph.

    Returns:
        List of workstream IDs in merge order (oldest first).
    """
    merged: list[tuple[str, str]] = []  # (merged_at, ws_id)
    for ws_id in graph.workstream_ids():
        # Skip RESET workstreams — they've been undone.
        ws_signal_dir = run_dir / "workstreams" / ws_id
        if ws_signal_dir.is_dir():
            ws_status = _read_status_from_signals(ws_signal_dir)
            if ws_status == WorkstreamStatus.RESET:
                continue

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


def write_rollback_entry(
    ws_signal_dir: Path,
    task_id: str,
    prior_status: str,
    integration_branch_sha_before: str,
    integration_branch_sha_after: str,
) -> None:
    """Append a rollback entry to the workstream rollback log.

    Reads the existing ``rollback_log.json`` (if present), appends a
    new timestamped entry, and writes the updated array back.  Creates
    the file and parent directory on first call.

    Args:
        ws_signal_dir: Workstream signal directory.
        task_id: Task that was reset.
        prior_status: Task status before reset (e.g. ``"pr_merged"``).
        integration_branch_sha_before: SHA before rollback.
        integration_branch_sha_after: SHA after rollback.
    """
    log_path = ws_signal_dir / "rollback_log.json"
    entries: list[dict[str, str]] = []
    if log_path.is_file():
        try:
            entries = json.loads(log_path.read_text())
        except json.JSONDecodeError:
            entries = []

    entries.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": task_id,
            "prior_status": prior_status,
            "integration_branch_sha_before": integration_branch_sha_before,
            "integration_branch_sha_after": integration_branch_sha_after,
        }
    )

    ws_signal_dir.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(entries, indent=2) + "\n")
