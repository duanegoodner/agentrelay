"""Workstream-level undo and infrastructure cleanup.

Usage::

    agentrelay teardown-workstream <graph.yaml> --workstream <ws-id>
    agentrelay reset-workstream <graph.yaml> --workstream <ws-id> --yes

Functions:
    teardown_workstream: Remove worktree and integration infrastructure.
    reset_workstream: Undo a merged workstream from its target branch.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from agentrelay.ops import gh, git
from agentrelay.reset_ops import (
    reset_branch,
    reset_task_state,
    reset_workstream_state,
    workstream_merge_order,
    write_rollback_entry,
)
from agentrelay.reset_pr import PrBodyUpdater
from agentrelay.resolved import ResolvedWorkstream
from agentrelay.task_graph import TaskGraph
from agentrelay.task_runtime import TaskStatus
from agentrelay.task_runtime.runtime import (
    SUCCESS_STATUSES,
    _read_task_status_from_signals,
)


def teardown_workstream(
    graph_name: str,
    graph: TaskGraph,
    run_dir: Path,
    repo_path: Path,
    ws_id: str,
) -> list[str]:
    """Remove workstream infrastructure (worktree + integration branch).

    Only valid when all tasks in the workstream have been reset or have
    no signal directory.  This is infrastructure cleanup, not an undo
    of merged work.

    Args:
        graph_name: Graph name (for path conventions).
        graph: Current task graph.
        run_dir: Path to the per-run directory.
        repo_path: Path to the repository root.
        ws_id: Workstream identifier.

    Returns:
        List of log messages describing actions taken.

    Raises:
        KeyError: If the workstream ID is unknown.
        ValueError: If any task still has active execution state.
    """
    graph.workstream(ws_id)  # Validate workstream exists.

    for tid in graph.tasks_in_workstream(ws_id):
        signal_dir = run_dir / "signals" / tid
        if signal_dir.is_dir():
            status = _read_task_status_from_signals(signal_dir)
            if status != TaskStatus.RESET:
                raise ValueError(
                    f"Task '{tid}' still has active execution state. "
                    f"Reset all tasks in workstream '{ws_id}' first."
                )

    log = reset_workstream_state(run_dir, ws_id, graph_name, repo_path)
    log.append(
        f"Teardown workstream '{ws_id}'. Infrastructure removed. "
        "Next run will create fresh worktree from current base branch."
    )
    return log


def reset_workstream(
    graph_name: str,
    graph: TaskGraph,
    run_dir: Path,
    repo_path: Path,
    ws_id: str,
    *,
    pr_body_updater: PrBodyUpdater | None = None,
) -> list[str]:
    """Undo a merged workstream from its target branch.

    Rolls back the target branch (typically ``main``) to its pre-merge
    SHA, closes the integration PR, and marks all task and workstream
    state as RESET.  Only valid when the workstream is the most recently
    merged on its target branch (stack constraint).

    Args:
        graph_name: Graph name (for path conventions).
        graph: Current task graph.
        run_dir: Path to the per-run directory.
        repo_path: Path to the repository root.
        ws_id: Workstream identifier.
        pr_body_updater: Optional updater to append reset activity to
            the integration PR body.  ``None`` skips PR body updates.

    Returns:
        List of log messages describing actions taken.

    Raises:
        KeyError: If the workstream ID is unknown.
        ValueError: If the workstream is not merged, or is not the most
            recently merged on its target branch.
    """
    ws_spec = graph.workstream(ws_id)  # Validate + get spec.

    # Load resolved.json.
    resolved_path = run_dir / "workstreams" / ws_id / "resolved.json"
    if not resolved_path.is_file():
        raise ValueError(
            f"Workstream '{ws_id}' has no resolved.json. "
            "Only merged workstreams can be reset."
        )

    data = json.loads(resolved_path.read_text())
    resolved = ResolvedWorkstream.from_dict(data)

    if not resolved.merge_occurred:
        raise ValueError(
            f"Workstream '{ws_id}' was not merged (merge_occurred=False). "
            "Nothing to undo on the target branch."
        )

    # Validate tip-of-target-branch (stack constraint).
    merge_order = workstream_merge_order(run_dir, graph)
    if not merge_order or merge_order[-1] != ws_id:
        if merge_order:
            last = merge_order[-1]
            raise ValueError(
                f"Workstream '{ws_id}' is not the most recently merged. "
                f"'{last}' was merged after it. Reset '{last}' first."
            )
        raise ValueError(
            f"Workstream '{ws_id}' not found in merge order. "
            "Cannot determine stack position."
        )

    log: list[str] = []

    # Capture current target branch SHA before rollback.
    target_sha = resolved.target_branch_before_any_merge
    target_branch = ws_spec.merge_target_branch
    sha_before = git.rev_parse(repo_path, target_branch)

    # Reset target branch.
    reset_branch(repo_path, target_branch, target_sha)
    log.append(f"Reset '{target_branch}' to {target_sha[:12]}")

    # Write rollback log entries and collect PR body entries.
    ws_signal_dir = run_dir / "workstreams" / ws_id
    pr_body_entries: list[tuple[str, str]] = []
    for tid in graph.tasks_in_workstream(ws_id):
        task_signal_dir = run_dir / "signals" / tid
        if task_signal_dir.is_dir():
            task_status = _read_task_status_from_signals(task_signal_dir)
            if task_status in SUCCESS_STATUSES:
                write_rollback_entry(
                    ws_signal_dir,
                    tid,
                    task_status.value,
                    sha_before,
                    target_sha,
                    source="reset-workstream",
                )
                log.append(f"Wrote rollback log entry for task '{tid}'")
                pr_body_entries.append((tid, task_status.value))

    # Append to integration PR body (best-effort), before closing.
    if pr_body_updater is not None and pr_body_entries:
        try:
            pr_created = ws_signal_dir / "pr_created"
            if pr_created.is_file():
                pr_url = pr_created.read_text().strip()
                if pr_url:
                    log.extend(
                        pr_body_updater.append_reset_activity(pr_url, pr_body_entries)
                    )
        except Exception:
            log.append(f"WARNING: PR body update failed for workstream '{ws_id}'")

    # Close integration PR (best-effort).
    if resolved.integration_pr_url is not None:
        try:
            gh.pr_close_by_url(resolved.integration_pr_url)
            log.append(f"Closed integration PR {resolved.integration_pr_url}")
        except subprocess.CalledProcessError:
            log.append(
                f"WARNING: Could not close integration PR "
                f"{resolved.integration_pr_url} (may already be closed)"
            )

    # Mark all tasks as RESET.
    for tid in graph.tasks_in_workstream(ws_id):
        log.extend(reset_task_state(run_dir, tid, graph_name, repo_path))

    # Mark workstream as RESET.
    log.extend(reset_workstream_state(run_dir, ws_id, graph_name, repo_path))

    log.append(
        f"Reset workstream '{ws_id}'. Target branch '{target_branch}' "
        f"rolled back to {target_sha[:12]}. All workstream state removed."
    )
    return log
