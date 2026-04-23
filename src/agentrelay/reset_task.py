"""Reset the tip task of a workstream (stack-based undo).

Usage::

    agentrelay reset-task <graph.yaml> --task <task-id>
    agentrelay reset-task <graph.yaml> --workstream <ws-id>

Peels the most recently touched task from a workstream's execution stack.
For merged tasks, the integration branch is rolled back to its pre-merge
SHA (from ``resolved.json``).  For non-merged tasks, the signal directory
and task branch are deleted.

Functions:
    reset_task: Core logic for the ``reset-task`` command.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from agentrelay.reset_ops import ResetOps
from agentrelay.reset_pr import IntegrationPrOps
from agentrelay.resolved import ResolvedTask
from agentrelay.task_graph import TaskGraph
from agentrelay.task_runtime import TaskStatus
from agentrelay.task_runtime.runtime import (
    SUCCESS_STATUSES,
    _read_task_status_from_signals,
)

_BRANCH_PREFIX = "agentrelay"


def reset_task(
    graph_name: str,
    graph: TaskGraph,
    run_dir: Path,
    reset_ops: ResetOps,
    *,
    task_id: str | None = None,
    ws_id: str | None = None,
    integration_pr_ops: IntegrationPrOps | None = None,
) -> list[str]:
    """Reset the tip task of a workstream.

    Either ``task_id`` or ``ws_id`` must be provided (not both).  When
    ``ws_id`` is given, the tip task is auto-detected.  When ``task_id``
    is given, it is validated to be the workstream tip.

    Args:
        graph_name: Graph name (for branch naming).
        graph: Current task graph.
        run_dir: Path to the per-run directory.
        reset_ops: Shared reset-layer operations bound to the target
            repository.
        task_id: Explicit task ID to reset (must be tip).
        ws_id: Workstream ID (auto-detect tip).
        integration_pr_ops: Optional integration-PR mutation provider.
            When present, reset activity is appended to the integration
            PR body.  ``None`` skips PR mutations.

    Returns:
        List of log messages describing actions taken.

    Raises:
        ValueError: If the task is not the tip, has no execution state,
            or neither ``task_id`` nor ``ws_id`` is provided.
        KeyError: If the task or workstream ID is unknown.
    """
    if task_id is None and ws_id is None:
        raise ValueError("Either task_id or ws_id must be provided")

    # Auto-detect tip from workstream.
    if task_id is None:
        assert ws_id is not None
        graph.workstream(ws_id)  # Validate workstream exists (raises KeyError).
        task_id = reset_ops.find_workstream_tip(run_dir, graph, ws_id)
        if task_id is None:
            raise ValueError(
                f"No tasks have execution state in workstream '{ws_id}'. "
                "Nothing to reset."
            )

    # Validate task exists in graph.
    task = graph.task(task_id)  # Raises KeyError if unknown.
    task_ws_id = task.workstream_id

    # Validate task is the workstream tip.
    tip = reset_ops.find_workstream_tip(run_dir, graph, task_ws_id)
    if tip is None:
        raise ValueError(f"Task '{task_id}' has no execution state. Nothing to reset.")
    if tip != task_id:
        raise ValueError(
            f"Task '{task_id}' is not the workstream tip. "
            f"Tip is '{tip}'. Reset '{tip}' first."
        )

    # Read status.
    signal_dir = run_dir / "signals" / task_id
    status = _read_task_status_from_signals(signal_dir)
    if status == TaskStatus.PENDING:
        raise ValueError(
            f"Task '{task_id}' is PENDING (no execution state). Nothing to reset."
        )

    log: list[str] = []
    integration_branch = f"{_BRANCH_PREFIX}/{graph_name}/{task_ws_id}/integration"

    if status in SUCCESS_STATUSES:
        # Merged task: roll back integration branch, then delete state.
        resolved_path = signal_dir / "resolved.json"
        if resolved_path.is_file():
            data = json.loads(resolved_path.read_text())
            resolved = ResolvedTask.from_dict(data)
            if resolved.integration_branch_before_merge is not None:
                sha_before = reset_ops.repo_ops.rev_parse(integration_branch)
                reset_ops.reset_branch(
                    integration_branch,
                    resolved.integration_branch_before_merge,
                )
                sha_after = resolved.integration_branch_before_merge
                log.append(
                    f"Reset integration branch '{integration_branch}' to "
                    f"{sha_after[:12]}"
                )

                # Write rollback log entry.
                ws_signal_dir = run_dir / "workstreams" / task_ws_id
                reset_ops.write_rollback_entry(
                    ws_signal_dir,
                    task_id,
                    status.value,
                    sha_before,
                    sha_after,
                    source="reset-task",
                )
                log.append(f"Wrote rollback log entry for task '{task_id}'")

                # Append to integration PR body (best-effort).
                if integration_pr_ops is not None:
                    try:
                        pr_created = ws_signal_dir / "pr_created"
                        if pr_created.is_file():
                            pr_url = pr_created.read_text().strip()
                            if pr_url:
                                log.extend(
                                    integration_pr_ops.append_reset_activity(
                                        pr_url, [(task_id, status.value)]
                                    )
                                )
                    except Exception:
                        log.append(
                            f"WARNING: PR body update failed for task '{task_id}'"
                        )

                # Remove stale workstream advancement signals so the
                # workstream reads as ACTIVE on the next resume.
                log.extend(reset_ops.rollback_workstream_advancement(ws_signal_dir))
        log.extend(reset_ops.reset_task_state(run_dir, task_id, graph_name))
    else:
        # Non-merged task: delete state, then switch worktree to integration branch.
        log.extend(reset_ops.reset_task_state(run_dir, task_id, graph_name))
        worktree_path = reset_ops.repo_path / ".worktrees" / graph_name / task_ws_id
        if worktree_path.is_dir():
            task_branch = f"{_BRANCH_PREFIX}/{graph_name}/{task_id}"
            current = reset_ops.repo_ops.current_branch_in(worktree_path)
            if current == task_branch:
                try:
                    reset_ops.repo_ops.checkout_in(worktree_path, integration_branch)
                    reset_ops.repo_ops.clean_in(worktree_path)
                    log.append(f"Switched worktree to '{integration_branch}'")
                except subprocess.CalledProcessError:
                    pass  # Best-effort: branch may already be gone

    # Determine new tip for confirmation message.
    tasks_in_ws = graph.tasks_in_workstream(task_ws_id)
    task_index = list(tasks_in_ws).index(task_id)
    if task_index > 0:
        new_tip = tasks_in_ws[task_index - 1]
        log.append(f"Reset task '{task_id}'. Workstream tip is now '{new_tip}'.")
    else:
        log.append(f"Reset task '{task_id}'. Workstream has no remaining tasks.")

    return log
