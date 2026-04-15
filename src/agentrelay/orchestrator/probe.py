"""Filesystem probe for reconstructing runtime state from a prior run.

Reads signal files under a per-run directory
(``.workflow/<graph>/runs/<N>/``) and produces reconstructed task and
workstream runtime state plus any frozen ``resolved.json`` records.
Called during graph resumption to determine what work has already been
done before the orchestrator begins scheduling.

The probe also **normalizes stale transient states in place**.  A crashed
orchestrator may have left a task in ``RUNNING`` (with or without a
terminal signal from the agent) or ``PR_CREATED`` (with an open PR on the
hosting platform).  Before the orchestrator sees the reconstructed
runtimes, the probe inspects the attempt directory and/or hosting
platform and writes the resolved status signal to disk, so the
orchestrator's existing init path
(:meth:`~agentrelay.orchestrator.orchestrator._OrchestratorRun._initialize_attempts_used`)
sees only terminal states.

Normal happy-path task state sequences (for reference):

    Task with PR:    PENDING → RUNNING → PR_CREATED → PR_MERGED
    PR-less task:    PENDING → RUNNING → COMPLETED
    Failed task:     PENDING → RUNNING → FAILED

Only ``RUNNING`` and ``PR_CREATED`` are transient-on-crash states that
require normalization.  ``PENDING``, ``PR_MERGED``, ``COMPLETED``, and
``FAILED`` are either pre-start or terminal and need no touchup.

**Post-probe invariant:** after :func:`probe_graph_state` returns, no
task is in ``RUNNING`` or ``PR_CREATED``.  This is the contract that
``_initialize_attempts_used`` relies on — it raises ``ValueError`` on
those states as a defensive check.

Classes:
    TaskProbe: Per-task reconstructed state.
    WorkstreamProbe: Per-workstream reconstructed state.
    GraphProbe: Aggregate probe result covering a whole graph.

Functions:
    probe_graph_state: Top-level entry point.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agentrelay.agent_sdk.task_helper import NO_PR_SENTINEL
from agentrelay.ops import signals
from agentrelay.resolved import ResolvedTask, ResolvedWorkstream
from agentrelay.task_graph import TaskGraph
from agentrelay.task_runtime import TaskStatus
from agentrelay.task_runtime.runtime import _read_task_status_from_signals
from agentrelay.workstream.core.io import TaskPrProber
from agentrelay.workstream.core.runtime import (
    WorkstreamStatus,
    _read_status_from_signals,
)

# ── Probe result dataclasses ──


@dataclass(frozen=True)
class TaskProbe:
    """Reconstructed on-disk state for a single task.

    Attributes:
        task_id: Task identifier.
        status: Resolved task status after stale-state normalization.
            Guaranteed never to be ``RUNNING`` or ``PR_CREATED``.
        signal_dir: Path to the task signal directory
            (``run_dir/signals/<task_id>``).  May or may not exist on
            disk — check ``signal_dir.is_dir()`` to distinguish "never
            started" from "started then progressed".
        attempt_num: Highest attempt number found on disk (0 if no
            attempt directories exist).
        branch_name: Task feature branch name, derived from convention
            as ``agentrelay/<graph_name>/<task_id>``.
        pr_url: PR URL recovered from the latest attempt's ``.done``
            file, or ``None`` for PR-less tasks / tasks that never
            reached the ``.done`` stage.
        resolved: Frozen execution record loaded from
            ``signal_dir/resolved.json`` if present, else ``None``.
    """

    task_id: str
    status: TaskStatus
    signal_dir: Path
    attempt_num: int
    branch_name: str
    pr_url: Optional[str]
    resolved: Optional[ResolvedTask]


@dataclass(frozen=True)
class WorkstreamProbe:
    """Reconstructed on-disk state for a single workstream.

    Attributes:
        workstream_id: Workstream identifier.
        status: Current workstream status (no normalization needed —
            workstream transient states are handled by the orchestrator's
            main loop via ``_poll_integration_merges`` and
            ``_process_merge_ready_workstreams``).
        signal_dir: Path to the workstream signal directory
            (``run_dir/workstreams/<ws_id>``).
        worktree_path: Path to the workstream worktree
            (``repo_path/.worktrees/<graph_name>/<ws_id>``).  Worktrees
            are not per-run and may still exist from prior runs.
        branch_name: Workstream integration branch name, derived as
            ``agentrelay/<graph_name>/<ws_id>/integration``.
        merge_pr_url: Integration PR URL recovered from the
            ``pr_created`` signal file, or ``None`` if no PR was
            created.
        resolved: Frozen execution record loaded from
            ``signal_dir/resolved.json`` if present, else ``None``.
    """

    workstream_id: str
    status: WorkstreamStatus
    signal_dir: Path
    worktree_path: Path
    branch_name: str
    merge_pr_url: Optional[str]
    resolved: Optional[ResolvedWorkstream]


@dataclass(frozen=True)
class GraphProbe:
    """Aggregate probe result covering all tasks and workstreams in a graph.

    Attributes:
        task_probes: Reconstructed task state keyed by task ID.  Every
            task in the current graph has an entry, even tasks that
            never ran (signal dir absent).
        workstream_probes: Reconstructed workstream state keyed by
            workstream ID.  Every workstream in the current graph has
            an entry.
    """

    task_probes: dict[str, TaskProbe]
    workstream_probes: dict[str, WorkstreamProbe]


# ── Top-level entry point ──


def probe_graph_state(
    repo_path: Path,
    graph_name: str,
    graph: TaskGraph,
    run_dir: Path,
    pr_prober: TaskPrProber,
) -> GraphProbe:
    """Reconstruct runtime state from on-disk signal files.

    Normalizes stale transient states in place before returning.  A
    task that was ``RUNNING`` at orchestrator-crash time is resolved by
    inspecting the attempt directory for terminal signals (``.done`` or
    ``.failed``); a task that was ``PR_CREATED`` is resolved by probing
    the hosting platform via ``pr_prober``.

    Chained normalization path when a ``RUNNING`` task has a ``.done``
    file containing a PR URL::

        RUNNING
          └─ .done + PR URL ──► PR_CREATED
                                  ├─ is_merged=True ─────────────► PR_MERGED
                                  ├─ is_merged=F, try_merge=T ──► PR_MERGED
                                  ├─ is_merged=F, try_merge=F ──► FAILED
                                  └─ pr_url=None (malformed) ───► FAILED

    Args:
        repo_path: Path to the target repository (used to compute
            worktree paths).
        graph_name: Name of the graph being resumed.
        graph: Current graph definition, used to enumerate task and
            workstream IDs.
        run_dir: Path to the run directory being probed
            (typically ``.workflow/<graph>/runs/<N>/``).
        pr_prober: Protocol implementation for checking and merging
            stale task PRs.

    Returns:
        GraphProbe: Reconstructed task and workstream state.
    """
    task_probes = {
        task_id: _probe_task_state(run_dir, task_id, graph_name, pr_prober)
        for task_id in graph.task_ids()
    }
    workstream_probes = {
        ws_id: _probe_workstream_state(run_dir, ws_id, repo_path, graph_name)
        for ws_id in graph.workstream_ids()
    }
    return GraphProbe(
        task_probes=task_probes,
        workstream_probes=workstream_probes,
    )


# ── Per-task probe ──


def _probe_task_state(
    run_dir: Path,
    task_id: str,
    graph_name: str,
    pr_prober: TaskPrProber,
) -> TaskProbe:
    """Reconstruct on-disk state for a single task.

    Normalizes stale ``RUNNING`` and ``PR_CREATED`` states in place so
    the returned probe's ``status`` is always a terminal state or
    ``PENDING``.
    """
    signal_dir = run_dir / "signals" / task_id
    branch_name = f"agentrelay/{graph_name}/{task_id}"

    if not signal_dir.is_dir():
        return TaskProbe(
            task_id=task_id,
            status=TaskStatus.PENDING,
            signal_dir=signal_dir,
            attempt_num=0,
            branch_name=branch_name,
            pr_url=None,
            resolved=None,
        )

    status = _read_task_status_from_signals(signal_dir)
    attempt_num = _latest_attempt_num(signal_dir)
    resolved = _load_resolved_task(signal_dir)

    # Stale RUNNING → normalize by inspecting attempt dir.  May resolve
    # into PR_CREATED which then falls through to the next normalizer.
    if status == TaskStatus.RUNNING:
        status = _normalize_stale_running(signal_dir, attempt_num)

    # Stale PR_CREATED (either originally or from RUNNING chain) →
    # consult the hosting platform.
    if status == TaskStatus.PR_CREATED:
        pr_url_for_prober = _read_pr_url_from_done(signal_dir, attempt_num)
        status = _normalize_stale_pr_created(signal_dir, pr_url_for_prober, pr_prober)

    pr_url = _read_pr_url_from_done(signal_dir, attempt_num)

    return TaskProbe(
        task_id=task_id,
        status=status,
        signal_dir=signal_dir,
        attempt_num=attempt_num,
        branch_name=branch_name,
        pr_url=pr_url,
        resolved=resolved,
    )


# ── Per-workstream probe ──


def _probe_workstream_state(
    run_dir: Path,
    workstream_id: str,
    repo_path: Path,
    graph_name: str,
) -> WorkstreamProbe:
    """Reconstruct on-disk state for a single workstream.

    Unlike tasks, workstream transient states do not need normalization
    here — the orchestrator's main loop handles stale integration PRs
    via ``_poll_integration_merges`` and ``_process_merge_ready_workstreams``
    after the probe returns.
    """
    signal_dir = run_dir / "workstreams" / workstream_id
    worktree_path = repo_path / ".worktrees" / graph_name / workstream_id
    branch_name = f"agentrelay/{graph_name}/{workstream_id}/integration"

    if not signal_dir.is_dir():
        return WorkstreamProbe(
            workstream_id=workstream_id,
            status=WorkstreamStatus.PENDING,
            signal_dir=signal_dir,
            worktree_path=worktree_path,
            branch_name=branch_name,
            merge_pr_url=None,
            resolved=None,
        )

    status = _read_status_from_signals(signal_dir)

    merge_pr_url: Optional[str] = None
    pr_created_content = signals.read_signal_file(signal_dir, "pr_created")
    if pr_created_content is not None:
        merge_pr_url = pr_created_content.strip() or None

    resolved = _load_resolved_workstream(signal_dir)

    return WorkstreamProbe(
        workstream_id=workstream_id,
        status=status,
        signal_dir=signal_dir,
        worktree_path=worktree_path,
        branch_name=branch_name,
        merge_pr_url=merge_pr_url,
        resolved=resolved,
    )


# ── Normalization functions ──


def _normalize_stale_running(signal_dir: Path, attempt_num: int) -> TaskStatus:
    """Resolve a stale ``RUNNING`` task by inspecting the attempt directory.

    Writes the resolved status signal file in place and returns the new
    status.  Resolution rules:

    +-----------------------------------------+------------------+---------------------------------------+
    | Input in ``attempts/<N>/``              | Resolved status  | Reason                                |
    +=========================================+==================+=======================================+
    | ``.done`` with line 2 = PR URL          | ``PR_CREATED``   | Agent finished, created a PR          |
    +-----------------------------------------+------------------+---------------------------------------+
    | ``.done`` with line 2 = ``NO_PR``       | ``COMPLETED``    | Agent finished a PR-less task         |
    +-----------------------------------------+------------------+---------------------------------------+
    | ``.failed``                             | ``FAILED``       | Agent reported failure                |
    +-----------------------------------------+------------------+---------------------------------------+
    | ``attempts/<N>/`` missing or empty      | ``FAILED``       | Agent killed before first write       |
    +-----------------------------------------+------------------+---------------------------------------+

    The ``attempts/<N>/`` subdirectory is created lazily on first write
    by the agent (via :func:`signals.write_text` →
    :func:`signals.ensure_signal_dir`).  This means there is a real
    window where ``status/running`` exists but ``attempts/<N>/`` does
    not — the orchestrator died between ``mark_running`` and the
    agent's first write.  This case is handled correctly without
    special code because :func:`signals.read_signal_file` returns
    ``None`` when the parent directory is missing
    (``Path.is_file()`` returns ``False`` for a path whose parent
    does not exist, no exception raised).  The "neither .done nor
    .failed" branch then routes the task to ``FAILED``, which is
    correct — the agent never reached a terminal state and the
    attempt is retry-eligible.

    Missing-``attempts``, empty-``attempts``, and partial-``attempts``
    (concerns.log but no terminal signal) are intentionally
    indistinguishable — all three mean "agent did not terminate".

    ``.done`` is checked before ``.failed``, so in the unlikely case
    both exist the ``.done`` path wins.

    Args:
        signal_dir: Task signal directory (``run_dir/signals/<task_id>``).
        attempt_num: Current attempt number to inspect.

    Returns:
        The resolved :class:`TaskStatus` — never ``RUNNING``.
    """
    attempt_dir = signal_dir / "attempts" / str(attempt_num)
    done_content = signals.read_signal_file(attempt_dir, ".done")
    failed_content = signals.read_signal_file(attempt_dir, ".failed")

    if done_content is not None:
        lines = done_content.splitlines()
        payload = lines[1].strip() if len(lines) > 1 else None
        if payload == NO_PR_SENTINEL:
            _write_task_status(signal_dir, TaskStatus.COMPLETED)
            return TaskStatus.COMPLETED
        _write_task_status(signal_dir, TaskStatus.PR_CREATED)
        return TaskStatus.PR_CREATED

    if failed_content is not None:
        _write_task_status(signal_dir, TaskStatus.FAILED)
        return TaskStatus.FAILED

    # Agent killed mid-run with no terminal signal — also the case when
    # attempts/<N>/ does not exist at all (see docstring).
    _write_task_status(signal_dir, TaskStatus.FAILED)
    return TaskStatus.FAILED


def _normalize_stale_pr_created(
    signal_dir: Path,
    pr_url: Optional[str],
    pr_prober: TaskPrProber,
) -> TaskStatus:
    """Resolve a stale ``PR_CREATED`` task by probing the hosting platform.

    Writes the resolved status signal file in place and returns the new
    status.  Resolution rules:

    +------------+--------------+---------------+-------------------+
    | ``pr_url`` | ``is_merged``| ``try_merge`` | Resolved status   |
    +============+==============+===============+===================+
    | ``None``   | n/a          | n/a           | ``FAILED``        |
    +------------+--------------+---------------+-------------------+
    | present    | ``True``     | not called    | ``PR_MERGED``     |
    +------------+--------------+---------------+-------------------+
    | present    | ``False``    | ``True``      | ``PR_MERGED``     |
    +------------+--------------+---------------+-------------------+
    | present    | ``False``    | ``False``     | ``FAILED``        |
    +------------+--------------+---------------+-------------------+

    ``try_merge`` is a best-effort call and a ``False`` return is
    explicitly *not* an error — it means "leave for manual review",
    which materializes as retry-eligible ``FAILED``.

    Args:
        signal_dir: Task signal directory.
        pr_url: PR URL recovered from the attempt's ``.done`` file, or
            ``None`` if no URL could be recovered (malformed ``.done``
            or missing file).
        pr_prober: Protocol used to query and merge the PR.

    Returns:
        The resolved :class:`TaskStatus` — never ``PR_CREATED``.
    """
    if pr_url is None:
        _write_task_status(signal_dir, TaskStatus.FAILED)
        return TaskStatus.FAILED

    if pr_prober.is_merged(pr_url):
        _write_task_status(signal_dir, TaskStatus.PR_MERGED)
        return TaskStatus.PR_MERGED

    if pr_prober.try_merge(pr_url):
        _write_task_status(signal_dir, TaskStatus.PR_MERGED)
        return TaskStatus.PR_MERGED

    _write_task_status(signal_dir, TaskStatus.FAILED)
    return TaskStatus.FAILED


# ── Private helpers ──


def _latest_attempt_num(signal_dir: Path) -> int:
    """Return the highest integer attempt directory number, or 0 if none exist."""
    attempts_dir = signal_dir / "attempts"
    if not attempts_dir.is_dir():
        return 0
    nums = [
        int(p.name) for p in attempts_dir.iterdir() if p.is_dir() and p.name.isdigit()
    ]
    return max(nums, default=0)


def _read_pr_url_from_done(signal_dir: Path, attempt_num: int) -> Optional[str]:
    """Parse the PR URL from ``attempts/<N>/.done`` line 2.

    Returns ``None`` if the file does not exist, has fewer than two
    lines, or the payload equals :data:`NO_PR_SENTINEL`.
    """
    attempt_dir = signal_dir / "attempts" / str(attempt_num)
    content = signals.read_signal_file(attempt_dir, ".done")
    if content is None:
        return None
    lines = content.splitlines()
    if len(lines) < 2:
        return None
    payload = lines[1].strip()
    if not payload or payload == NO_PR_SENTINEL:
        return None
    return payload


def _load_resolved_task(signal_dir: Path) -> Optional[ResolvedTask]:
    """Load ``signal_dir/resolved.json`` as a :class:`ResolvedTask`, or ``None``."""
    path = signal_dir / "resolved.json"
    if not path.is_file():
        return None
    return ResolvedTask.from_dict(json.loads(path.read_text()))


def _load_resolved_workstream(
    signal_dir: Path,
) -> Optional[ResolvedWorkstream]:
    """Load ``signal_dir/resolved.json`` as a :class:`ResolvedWorkstream`, or ``None``."""
    path = signal_dir / "resolved.json"
    if not path.is_file():
        return None
    return ResolvedWorkstream.from_dict(json.loads(path.read_text()))


def _write_task_status(signal_dir: Path, status: TaskStatus) -> None:
    """Write an empty status signal file under ``signal_dir/status/<name>``.

    Matches the write pattern used by
    :meth:`TaskRuntime._write_status_signal` so the resulting files are
    indistinguishable from those written by the live orchestrator.
    Existing status files are not removed — the latest-wins rule in
    :func:`_read_task_status_from_signals` handles the overlap.
    """
    status_dir = signal_dir / "status"
    status_dir.mkdir(parents=True, exist_ok=True)
    (status_dir / status.value).write_text("")


__all__ = [
    "GraphProbe",
    "TaskProbe",
    "WorkstreamProbe",
    "probe_graph_state",
]
