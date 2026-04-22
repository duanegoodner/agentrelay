"""Batch rollback to a specific task or workstream (``reset-to``).

Usage::

    agentrelay reset-to <graph.yaml> --after <task-or-workstream-id>

Computes the minimum set of operations to roll a graph back to the
state immediately after ``--after <id>``, displays a plan, and executes
after confirmation.  Composes the same shared utilities as the primitive
undo commands (:mod:`reset_task`, :mod:`reset_workstream`).

Classes:
    BranchReset: A single branch reset operation.
    ResetToPlan: Structured plan for a batch rollback.

Functions:
    resolve_target: Disambiguate target as task or workstream.
    build_plan: Compute a rollback plan from the graph and disk state.
    format_plan: Format a plan for human-readable display.
    execute_plan: Execute a computed rollback plan.
"""

from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from agentrelay.ops import gh, git
from agentrelay.reset_ops import (
    reset_branch,
    reset_task_state,
    reset_workstream_state,
    rollback_workstream_advancement,
    workstream_merge_order,
    write_rollback_entry,
)
from agentrelay.reset_pr import PrBodyUpdater
from agentrelay.resolved import ResolvedTask, ResolvedWorkstream
from agentrelay.task_graph import TaskGraph
from agentrelay.task_runtime import TaskStatus
from agentrelay.task_runtime.runtime import (
    SUCCESS_STATUSES,
    _read_task_status_from_signals,
)

_BRANCH_PREFIX = "agentrelay"


# ── Data classes ──


@dataclass(frozen=True)
class BranchReset:
    """A single branch reset operation.

    Attributes:
        branch: Branch name to reset (e.g. ``"main"``).
        target_sha: SHA to reset the branch to.
        description: Human-readable context (e.g. ``"before ws-2 merge"``).
    """

    branch: str
    target_sha: str
    description: str


@dataclass(frozen=True)
class ResetToPlan:
    """Structured plan for a batch rollback.

    Attributes:
        target_kind: ``"task"`` or ``"workstream"``.
        target_id: The ``--after`` value.
        target_branch_reset: Target branch rollback (e.g. main), or
            ``None`` for task targets.
        integration_branch_resets: Per-workstream integration branch
            resets.
        tasks_to_reset: Task IDs to mark RESET.
        workstreams_to_teardown: Workstreams to tear down (infra only).
        workstreams_to_unmerge: Merged workstreams to unmerge from the
            target branch.
        pr_urls_to_close: Integration PR URLs to close.
    """

    target_kind: str
    target_id: str
    target_branch_reset: BranchReset | None
    integration_branch_resets: tuple[BranchReset, ...]
    tasks_to_reset: tuple[str, ...]
    workstreams_to_teardown: tuple[str, ...]
    workstreams_to_unmerge: tuple[str, ...]
    pr_urls_to_close: tuple[str, ...]


# ── Target resolution ──


def resolve_target(
    graph: TaskGraph,
    after_id: str,
) -> tuple[str, str]:
    """Disambiguate ``--after`` as a task or workstream ID.

    Workstream IDs take precedence if the ID exists as both.

    Args:
        graph: Current task graph.
        after_id: The ``--after`` value from the CLI.

    Returns:
        Tuple of ``(kind, id)`` where kind is ``"workstream"`` or
        ``"task"``.

    Raises:
        KeyError: If the ID is not found as either a task or workstream.
    """
    if after_id in graph.workstream_ids():
        return ("workstream", after_id)
    graph.task(after_id)  # Raises KeyError if unknown.
    return ("task", after_id)


# ── Transitive dependency helpers ──


def _transitive_dependents(
    graph: TaskGraph,
    seed_ids: set[str],
) -> set[str]:
    """Compute the transitive closure of dependents via BFS.

    ``graph.dependent_ids()`` returns direct dependents only, so BFS
    is required for the full transitive closure.

    Args:
        graph: Current task graph.
        seed_ids: Starting task IDs.

    Returns:
        All transitively dependent task IDs (excluding the seeds
        themselves unless they appear as dependents of other seeds).
    """
    visited: set[str] = set()
    queue = list(seed_ids)
    while queue:
        tid = queue.pop(0)
        for dep in graph.dependent_ids(tid):
            if dep not in visited and dep not in seed_ids:
                visited.add(dep)
                queue.append(dep)
    return visited


# ── Plan computation ──


def _compute_task_target_plan(
    graph_name: str,
    graph: TaskGraph,
    run_dir: Path,
    keep_task_id: str,
) -> ResetToPlan:
    """Compute a rollback plan for a task target.

    Keeps ``keep_task_id`` and everything before it in its workstream.
    Removes later tasks in that workstream plus transitive dependents
    in other workstreams.
    """
    anchor_ws = graph.task(keep_task_id).workstream_id
    tasks_in_ws = graph.tasks_in_workstream(anchor_ws)
    idx = list(tasks_in_ws).index(keep_task_id)

    # Direct removals: everything after the anchor in the same workstream.
    direct_removals = set(tasks_in_ws[idx + 1 :])

    # Transitive dependents across all workstreams.
    transitive = _transitive_dependents(graph, direct_removals)
    all_removals = direct_removals | transitive

    # Filter to tasks that actually have execution state on disk.
    tasks_with_state: set[str] = set()
    for tid in all_removals:
        signal_dir = run_dir / "signals" / tid
        if signal_dir.is_dir():
            status = _read_task_status_from_signals(signal_dir)
            if status != TaskStatus.PENDING and status != TaskStatus.RESET:
                tasks_with_state.add(tid)

    if not tasks_with_state:
        raise ValueError(
            f"Nothing to reset after task '{keep_task_id}'. "
            "No later tasks have execution state."
        )

    # Group removed tasks by workstream.
    by_ws: dict[str, list[str]] = defaultdict(list)
    for tid in tasks_with_state:
        ws = graph.task(tid).workstream_id
        by_ws[ws].append(tid)

    # Sort each group by topo order within the workstream.
    for ws_id, tids in by_ws.items():
        ws_topo = list(graph.tasks_in_workstream(ws_id))
        tids.sort(key=lambda t: ws_topo.index(t))

    # Integration branch resets: one per affected workstream.
    integration_resets: list[BranchReset] = []
    for ws_id, tids in by_ws.items():
        first_removed = tids[0]
        resolved_path = run_dir / "signals" / first_removed / "resolved.json"
        if resolved_path.is_file():
            data = json.loads(resolved_path.read_text())
            resolved = ResolvedTask.from_dict(data)
            if resolved.integration_branch_before_merge is not None:
                branch = f"{_BRANCH_PREFIX}/{graph_name}/{ws_id}/integration"
                integration_resets.append(
                    BranchReset(
                        branch=branch,
                        target_sha=resolved.integration_branch_before_merge,
                        description=f"before {first_removed} merge",
                    )
                )

    # Determine workstreams to teardown: non-anchor workstreams where
    # ALL tasks are in the removal set.
    ws_to_teardown: list[str] = []
    for ws_id in by_ws:
        if ws_id == anchor_ws:
            continue
        all_ws_tasks = set(graph.tasks_in_workstream(ws_id))
        if all_ws_tasks <= all_removals:
            ws_to_teardown.append(ws_id)

    # Collect integration PR URLs for workstreams being torn down.
    pr_urls: list[str] = []
    for ws_id in ws_to_teardown:
        pr_created = run_dir / "workstreams" / ws_id / "pr_created"
        if pr_created.is_file():
            url = pr_created.read_text().strip()
            if url:
                pr_urls.append(url)

    # Order tasks for reset (reverse topo order — peel from tip).
    all_task_topo = list(graph.topological_order())
    ordered_tasks = sorted(tasks_with_state, key=lambda t: all_task_topo.index(t))

    return ResetToPlan(
        target_kind="task",
        target_id=keep_task_id,
        target_branch_reset=None,
        integration_branch_resets=tuple(integration_resets),
        tasks_to_reset=tuple(ordered_tasks),
        workstreams_to_teardown=tuple(sorted(ws_to_teardown)),
        workstreams_to_unmerge=(),
        pr_urls_to_close=tuple(pr_urls),
    )


def _compute_ws_target_plan(
    graph: TaskGraph,
    run_dir: Path,
    keep_ws_id: str,
) -> ResetToPlan:
    """Compute a rollback plan for a workstream target.

    Keeps ``keep_ws_id`` and everything merged before it on the target
    branch.  Removes later-merged workstreams and tears down dependent
    in-progress workstreams.
    """
    merge_order = workstream_merge_order(run_dir, graph)

    if keep_ws_id not in merge_order:
        raise ValueError(
            f"Workstream '{keep_ws_id}' is not in the merge order. "
            "Only merged workstreams can be used as --after targets."
        )

    idx = merge_order.index(keep_ws_id)
    ws_to_unmerge = merge_order[idx + 1 :]

    # Collect all task IDs from workstreams to unmerge.
    unmerge_tasks: set[str] = set()
    for ws_id in ws_to_unmerge:
        unmerge_tasks.update(graph.tasks_in_workstream(ws_id))

    # Workstreams to tear down: non-kept, non-unmerged workstreams that
    # are downstream of the target or of unmerged workstreams.  This
    # covers in-progress workstreams whose cross-workstream deps point
    # at the target or anything after it (e.g., ws_b in PR_CREATED
    # when --after ws_a, where ws_b depends on ws_a).  Truly independent
    # workstreams are untouched.
    unmerge_set = set(ws_to_unmerge)
    kept_set = set(merge_order[: idx + 1])
    # Workstreams that are being removed or are the target itself.
    affected_ws = unmerge_set | {keep_ws_id}
    ws_to_teardown: set[str] = set()

    for ws_id in graph.workstream_ids():
        if ws_id in unmerge_set or ws_id in kept_set:
            continue
        # Check if any task in this workstream has cross-workstream deps
        # on the target workstream or on any workstream being unmerged.
        for tid in graph.tasks_in_workstream(ws_id):
            upstream_ws = set(graph.upstream_workstream_ids(tid))
            if upstream_ws & affected_ws:
                ws_to_teardown.add(ws_id)
                break

    # Also add workstreams with tasks that transitively depend on tasks
    # in unmerged workstreams.
    if unmerge_tasks:
        transitive = _transitive_dependents(graph, unmerge_tasks)
        for tid in transitive:
            ws = graph.task(tid).workstream_id
            if ws not in unmerge_set and ws not in kept_set:
                ws_to_teardown.add(ws)

    # Target branch reset: use the first unmerged workstream's pre-merge SHA.
    target_branch_reset: BranchReset | None = None
    if ws_to_unmerge:
        first_ws = ws_to_unmerge[0]
        resolved_path = run_dir / "workstreams" / first_ws / "resolved.json"
        if resolved_path.is_file():
            data = json.loads(resolved_path.read_text())
            resolved = ResolvedWorkstream.from_dict(data)
            ws_spec = graph.workstream(first_ws)
            target_branch_reset = BranchReset(
                branch=ws_spec.merge_target_branch,
                target_sha=resolved.target_branch_before_any_merge,
                description=f"before {first_ws} merge",
            )

    # Collect all tasks to reset from unmerge + teardown workstreams.
    all_tasks: set[str] = set(unmerge_tasks)
    for ws_id in ws_to_teardown:
        all_tasks.update(graph.tasks_in_workstream(ws_id))

    # Filter to tasks with execution state.
    tasks_with_state: set[str] = set()
    for tid in all_tasks:
        signal_dir = run_dir / "signals" / tid
        if signal_dir.is_dir():
            status = _read_task_status_from_signals(signal_dir)
            if status != TaskStatus.PENDING and status != TaskStatus.RESET:
                tasks_with_state.add(tid)

    if not ws_to_unmerge and not ws_to_teardown:
        raise ValueError(
            f"Nothing to reset after workstream '{keep_ws_id}'. "
            "No later workstreams found."
        )

    # Collect PR URLs to close from unmerged workstreams.
    pr_urls: list[str] = []
    for ws_id in ws_to_unmerge:
        resolved_path = run_dir / "workstreams" / ws_id / "resolved.json"
        if resolved_path.is_file():
            data = json.loads(resolved_path.read_text())
            resolved = ResolvedWorkstream.from_dict(data)
            if resolved.integration_pr_url is not None:
                pr_urls.append(resolved.integration_pr_url)
    for ws_id in ws_to_teardown:
        pr_created = run_dir / "workstreams" / ws_id / "pr_created"
        if pr_created.is_file():
            url = pr_created.read_text().strip()
            if url:
                pr_urls.append(url)

    # Order tasks by topo order.
    all_task_topo = list(graph.topological_order())
    ordered_tasks = sorted(tasks_with_state, key=lambda t: all_task_topo.index(t))

    return ResetToPlan(
        target_kind="workstream",
        target_id=keep_ws_id,
        target_branch_reset=target_branch_reset,
        integration_branch_resets=(),
        tasks_to_reset=tuple(ordered_tasks),
        workstreams_to_teardown=tuple(sorted(ws_to_teardown)),
        workstreams_to_unmerge=tuple(ws_to_unmerge),
        pr_urls_to_close=tuple(pr_urls),
    )


def build_plan(
    graph_name: str,
    graph: TaskGraph,
    run_dir: Path,
    *,
    after: str,
) -> ResetToPlan:
    """Compute a rollback plan for the given target.

    Args:
        graph_name: Graph name (for branch naming).
        graph: Current task graph.
        run_dir: Path to the per-run directory.
        after: Task ID or workstream ID to keep.

    Returns:
        A :class:`ResetToPlan` describing the operations to execute.

    Raises:
        KeyError: If the target ID is unknown.
        ValueError: If there is nothing to reset.
    """
    kind, target_id = resolve_target(graph, after)
    if kind == "task":
        return _compute_task_target_plan(graph_name, graph, run_dir, target_id)
    return _compute_ws_target_plan(graph, run_dir, target_id)


# ── Plan display ──


def format_plan(plan: ResetToPlan) -> str:
    """Format a rollback plan for human-readable display.

    Args:
        plan: A computed rollback plan.

    Returns:
        Multi-line formatted string.
    """
    lines: list[str] = []
    lines.append(f"Plan: roll back to {plan.target_kind} '{plan.target_id}'")
    lines.append("")

    if plan.target_branch_reset is not None:
        br = plan.target_branch_reset
        lines.append(
            f"  Target branch reset: {br.branch} -> {br.target_sha[:12]} "
            f"({br.description})"
        )

    if plan.integration_branch_resets:
        lines.append(
            f"  Integration branch resets: {len(plan.integration_branch_resets)}"
        )
        for br in plan.integration_branch_resets:
            lines.append(f"    {br.branch} -> {br.target_sha[:12]} ({br.description})")

    if plan.tasks_to_reset:
        task_list = ", ".join(plan.tasks_to_reset)
        lines.append(f"  Tasks to reset: {len(plan.tasks_to_reset)} ({task_list})")

    if plan.workstreams_to_unmerge:
        ws_list = ", ".join(plan.workstreams_to_unmerge)
        lines.append(
            f"  Workstreams to unmerge from target: "
            f"{len(plan.workstreams_to_unmerge)} ({ws_list})"
        )

    if plan.workstreams_to_teardown:
        ws_list = ", ".join(plan.workstreams_to_teardown)
        lines.append(
            f"  Workstreams to tear down: "
            f"{len(plan.workstreams_to_teardown)} ({ws_list})"
        )

    if plan.pr_urls_to_close:
        lines.append(f"  Integration PRs to close: {len(plan.pr_urls_to_close)}")

    # Summary counts.
    lines.append("")
    force_pushes = (1 if plan.target_branch_reset else 0) + len(
        plan.integration_branch_resets
    )
    lines.append(f"  {force_pushes} force-push(es)")
    lines.append(f"  {len(plan.tasks_to_reset)} task(s) reset")
    ws_total = len(plan.workstreams_to_unmerge) + len(plan.workstreams_to_teardown)
    lines.append(f"  {ws_total} workstream(s) affected")

    return "\n".join(lines)


# ── Plan execution ──


def execute_plan(
    graph_name: str,
    graph: TaskGraph,
    run_dir: Path,
    repo_path: Path,
    plan: ResetToPlan,
    *,
    pr_body_updater: PrBodyUpdater | None = None,
) -> list[str]:
    """Execute a computed rollback plan.

    Execution order (most destructive first):

    1. Target branch reset.
    2. Integration branch resets.
    3. Worktree checkout fixup for surviving workstreams.
    4. Rollback log entries for merged tasks.
    5. PR body updates (best-effort — reads ``pr_created``).
    6. Workstream advancement rollback (remove stale ``merge_ready``/
       ``pr_created`` signals for surviving workstreams).
    7. Close integration PRs (best-effort).
    8. Task state cleanup.
    9. Workstream state cleanup.

    Args:
        graph_name: Graph name (for branch naming).
        graph: Current task graph.
        run_dir: Path to the per-run directory.
        repo_path: Path to the repository root.
        plan: A :class:`ResetToPlan` from :func:`build_plan`.
        pr_body_updater: Optional updater for integration PR bodies.

    Returns:
        List of log messages describing actions taken.
    """
    log: list[str] = []
    source = f"reset-to --after {plan.target_id}"

    # 1. Target branch reset.
    if plan.target_branch_reset is not None:
        br = plan.target_branch_reset
        reset_branch(repo_path, br.branch, br.target_sha)
        log.append(f"Reset '{br.branch}' to {br.target_sha[:12]}")

    # 2. Integration branch resets.
    for br in plan.integration_branch_resets:
        reset_branch(repo_path, br.branch, br.target_sha)
        log.append(f"Reset '{br.branch}' to {br.target_sha[:12]}")

    # 3. Worktree checkout fixup: switch surviving worktrees off
    #    task branches being deleted.
    teardown_and_unmerge = set(plan.workstreams_to_teardown) | set(
        plan.workstreams_to_unmerge
    )
    removed_task_branches = {
        f"{_BRANCH_PREFIX}/{graph_name}/{tid}" for tid in plan.tasks_to_reset
    }
    # Find workstreams that have tasks being removed but are NOT being
    # torn down or unmerged (i.e., the workstream itself survives).
    surviving_ws_with_removals: set[str] = set()
    for tid in plan.tasks_to_reset:
        ws = graph.task(tid).workstream_id
        if ws not in teardown_and_unmerge:
            surviving_ws_with_removals.add(ws)

    for ws_id in surviving_ws_with_removals:
        worktree_path = repo_path / ".worktrees" / graph_name / ws_id
        if not worktree_path.is_dir():
            continue
        try:
            current = git.current_branch(worktree_path)
            if current in removed_task_branches:
                integration_branch = (
                    f"{_BRANCH_PREFIX}/{graph_name}/{ws_id}/integration"
                )
                git.checkout(worktree_path, integration_branch)
                git.clean(worktree_path)
                log.append(f"Switched worktree for '{ws_id}' to '{integration_branch}'")
        except subprocess.CalledProcessError:
            log.append(
                f"WARNING: Could not switch worktree for '{ws_id}' "
                "to integration branch"
            )

    # 4. Rollback log entries for merged tasks.
    pr_body_by_ws: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for tid in plan.tasks_to_reset:
        signal_dir = run_dir / "signals" / tid
        if not signal_dir.is_dir():
            continue
        status = _read_task_status_from_signals(signal_dir)
        if status not in SUCCESS_STATUSES:
            continue

        resolved_path = signal_dir / "resolved.json"
        if not resolved_path.is_file():
            continue

        data = json.loads(resolved_path.read_text())
        resolved = ResolvedTask.from_dict(data)
        ws_id = resolved.workstream_id
        ws_signal_dir = run_dir / "workstreams" / ws_id

        sha_before = resolved.integration_branch_before_merge or ""
        sha_after = resolved.integration_branch_before_merge or ""
        # For batch rollback, record the actual integration branch
        # pre-merge SHA as both before and after — the branch was reset
        # in a single jump rather than sequential peels.
        write_rollback_entry(
            ws_signal_dir,
            tid,
            status.value,
            sha_before,
            sha_after,
            source=source,
        )
        log.append(f"Wrote rollback log entry for task '{tid}'")
        pr_body_by_ws[ws_id].append((tid, status.value))

    # 5. PR body updates (best-effort — reads pr_created before removal).
    if pr_body_updater is not None:
        for ws_id, entries in pr_body_by_ws.items():
            try:
                pr_created = run_dir / "workstreams" / ws_id / "pr_created"
                if pr_created.is_file():
                    pr_url = pr_created.read_text().strip()
                    if pr_url:
                        log.extend(
                            pr_body_updater.append_reset_activity(pr_url, entries)
                        )
            except Exception:
                log.append(f"WARNING: PR body update failed for workstream '{ws_id}'")

    # 6. Workstream advancement rollback: remove stale merge_ready/
    #    pr_created signals for surviving workstreams so they read as
    #    ACTIVE on the next resume.
    for ws_id in surviving_ws_with_removals:
        ws_signal_dir = run_dir / "workstreams" / ws_id
        if ws_signal_dir.is_dir():
            log.extend(rollback_workstream_advancement(ws_signal_dir))

    # 7. Close integration PRs (best-effort).
    for pr_url in plan.pr_urls_to_close:
        try:
            gh.pr_close_by_url(pr_url)
            log.append(f"Closed integration PR {pr_url}")
        except subprocess.CalledProcessError:
            log.append(
                f"WARNING: Could not close integration PR {pr_url} "
                "(may already be closed)"
            )

    # 8. Task state cleanup.
    for tid in plan.tasks_to_reset:
        log.extend(reset_task_state(run_dir, tid, graph_name, repo_path))

    # 9. Workstream state cleanup.
    for ws_id in plan.workstreams_to_unmerge:
        log.extend(reset_workstream_state(run_dir, ws_id, graph_name, repo_path))
    for ws_id in plan.workstreams_to_teardown:
        log.extend(reset_workstream_state(run_dir, ws_id, graph_name, repo_path))

    return log


__all__ = [
    "BranchReset",
    "ResetToPlan",
    "build_plan",
    "execute_plan",
    "format_plan",
    "resolve_target",
]
