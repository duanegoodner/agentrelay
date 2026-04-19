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

from agentrelay.ops import git
from agentrelay.reset_ops import delete_task_state, find_workstream_tip, reset_branch
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
    repo_path: Path,
    *,
    task_id: str | None = None,
    ws_id: str | None = None,
) -> list[str]:
    """Reset the tip task of a workstream.

    Either ``task_id`` or ``ws_id`` must be provided (not both).  When
    ``ws_id`` is given, the tip task is auto-detected.  When ``task_id``
    is given, it is validated to be the workstream tip.

    Args:
        graph_name: Graph name (for branch naming).
        graph: Current task graph.
        run_dir: Path to the per-run directory.
        repo_path: Path to the repository root.
        task_id: Explicit task ID to reset (must be tip).
        ws_id: Workstream ID (auto-detect tip).

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
        task_id = find_workstream_tip(run_dir, graph, ws_id)
        if task_id is None:
            raise ValueError(
                f"No tasks have execution state in workstream '{ws_id}'. "
                "Nothing to reset."
            )

    # Validate task exists in graph.
    task = graph.task(task_id)  # Raises KeyError if unknown.
    task_ws_id = task.workstream_id

    # Validate task is the workstream tip.
    tip = find_workstream_tip(run_dir, graph, task_ws_id)
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
                reset_branch(
                    repo_path,
                    integration_branch,
                    resolved.integration_branch_before_merge,
                )
                log.append(
                    f"Reset integration branch '{integration_branch}' to "
                    f"{resolved.integration_branch_before_merge[:12]}"
                )
        log.extend(delete_task_state(run_dir, task_id, graph_name, repo_path))
    else:
        # Non-merged task: delete state, then switch worktree to integration branch.
        log.extend(delete_task_state(run_dir, task_id, graph_name, repo_path))
        worktree_path = repo_path / ".worktrees" / graph_name / task_ws_id
        if worktree_path.is_dir():
            task_branch = f"{_BRANCH_PREFIX}/{graph_name}/{task_id}"
            current = git.current_branch(worktree_path)
            if current == task_branch:
                try:
                    git.checkout(worktree_path, integration_branch)
                    git.clean(worktree_path)
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
