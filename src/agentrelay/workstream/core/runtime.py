"""Runtime state and artifacts for workstream execution.

This module defines mutable runtime types for tracking the execution lifecycle
of a workstream lane (worktree/branch context) during orchestration.

Enums:
    WorkstreamStatus: Execution state of a workstream lane.

Classes:
    TaskSummary: Per-task summary for integration PR body.
    WorkstreamState: Mutable operational state of a workstream lane.
    WorkstreamArtifacts: Outputs produced while advancing a workstream lane.
    WorkstreamRuntime: Mutable runtime envelope grouping workstream spec and state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from agentrelay.workstream.core.workstream import WorkstreamSpec


class WorkstreamStatus(str, Enum):
    """Execution state of a workstream during orchestration.

    Attributes:
        PENDING: Workstream has not started provisioning/execution.
        ACTIVE: Workstream is currently active (for example has running tasks).
        MERGE_READY: All tasks completed; workstream is ready for integration.
        PR_CREATED: Integration PR has been created, awaiting merge.
        MERGED: Integration PR has been merged into the target branch.
        FAILED: Workstream execution failed.
        RESET: Workstream was reset via ``reset-workstream`` or
            ``teardown-workstream``.  Signal directory is preserved for
            history; workstream is logically available for re-execution.
    """

    PENDING = "pending"
    ACTIVE = "active"
    MERGE_READY = "merge_ready"
    PR_CREATED = "pr_created"
    MERGED = "merged"
    FAILED = "failed"
    RESET = "reset"


# Ordered sequence of non-failure statuses for determining current state
# from signal files. The latest file in this sequence wins.
_STATUS_SEQUENCE: tuple[WorkstreamStatus, ...] = (
    WorkstreamStatus.PENDING,
    WorkstreamStatus.ACTIVE,
    WorkstreamStatus.MERGE_READY,
    WorkstreamStatus.PR_CREATED,
    WorkstreamStatus.MERGED,
)


def _read_status_from_signals(signal_dir: Path) -> WorkstreamStatus:
    """Determine workstream status from signal files on disk.

    ``RESET`` takes absolute priority (deliberate user action).
    ``FAILED`` takes priority next.  Otherwise, the latest status in
    the known sequence whose signal file exists is returned.

    Args:
        signal_dir: Path to the workstream signal directory.

    Returns:
        The current workstream status.
    """
    if (signal_dir / "reset").exists():
        return WorkstreamStatus.RESET
    if (signal_dir / "failed").exists():
        return WorkstreamStatus.FAILED
    result = WorkstreamStatus.PENDING
    for status in _STATUS_SEQUENCE:
        if (signal_dir / status.value).exists():
            result = status
    return result


@dataclass(frozen=True)
class TaskSummary:
    """Per-task summary included in integration PR body.

    Attributes:
        task_id: Unique task identifier.
        description: Human-readable task description, or ``None``.
        role: Agent role value string (e.g. ``"spec_writer"``), or ``None``.
        pr_url: URL of the task's pull request, or ``None``.
        concerns: Design concerns recorded by the agent.
        ops_concerns: Operational concerns recorded by the agent.
        summary_text: Content of the agent's ``summary.md``, or ``None``.
    """

    task_id: str
    description: Optional[str] = None
    role: Optional[str] = None
    pr_url: Optional[str] = None
    concerns: tuple[str, ...] = ()
    ops_concerns: tuple[str, ...] = ()
    summary_text: Optional[str] = None


@dataclass
class WorkstreamState:
    """Mutable operational state of a workstream lane.

    Attributes:
        signal_dir: Path to the workstream signal directory for status files,
            or ``None`` if not provisioned yet.
        worktree_path: Filesystem path to the worktree used for this lane, or
            ``None`` if not provisioned yet.
        branch_name: Primary branch name used for this lane, or ``None`` until set.
        error: Error message if lane execution failed, else ``None``.
    """

    signal_dir: Optional[Path] = None
    worktree_path: Optional[Path] = None
    branch_name: Optional[str] = None
    error: Optional[str] = None


@dataclass
class WorkstreamArtifacts:
    """Outputs and observations produced while advancing a workstream.

    Attributes:
        merge_pr_url: URL of the workstream integration PR, or ``None`` if absent.
        concerns: List of notable observations or concerns for this lane.
        task_summaries: Per-task summaries for integration PR body.
        target_branch_before_any_merge: SHA of the target branch before any
            merge related to this workstream.  Populated from whichever
            authority path detected the merge (integrator for skipped
            workstreams, auto-merger, or polled merge checker).
    """

    merge_pr_url: Optional[str] = None
    concerns: list[str] = field(default_factory=list)
    task_summaries: list[TaskSummary] = field(default_factory=list)
    target_branch_before_any_merge: Optional[str] = None


@dataclass
class WorkstreamRuntime:
    """Mutable runtime envelope for a :class:`WorkstreamSpec`.

    Attributes:
        spec: Immutable workstream specification for this lane.
        state: Mutable lane operational state.
        artifacts: Mutable lane output artifacts.
    """

    spec: WorkstreamSpec
    state: WorkstreamState = field(default_factory=WorkstreamState)
    artifacts: WorkstreamArtifacts = field(default_factory=WorkstreamArtifacts)

    @property
    def status(self) -> WorkstreamStatus:
        """Current workstream status, derived from signal files on disk.

        Falls back to ``PENDING`` if no signal directory has been set,
        unless an error has been recorded (indicating failure before
        provisioning), in which case ``FAILED`` is returned.
        """
        if self.state.signal_dir is None:
            if self.state.error is not None:
                return WorkstreamStatus.FAILED
            return WorkstreamStatus.PENDING
        return _read_status_from_signals(self.state.signal_dir)

    def _write_signal(self, name: str, content: str = "") -> None:
        """Write a signal file to the workstream signal directory."""
        assert self.state.signal_dir is not None, "signal_dir must be set"
        self.state.signal_dir.mkdir(parents=True, exist_ok=True)
        (self.state.signal_dir / name).write_text(content)

    def mark_pending(self) -> None:
        """Write the ``pending`` signal file."""
        self._write_signal("pending")

    def mark_active(self) -> None:
        """Write the ``active`` signal file."""
        self._write_signal("active")

    def mark_merge_ready(self) -> None:
        """Write the ``merge_ready`` signal file."""
        self._write_signal("merge_ready")

    def mark_pr_created(self, pr_url: str) -> None:
        """Write the ``pr_created`` signal file with the PR URL."""
        self._write_signal("pr_created", pr_url)
        self.artifacts.merge_pr_url = pr_url

    def mark_merged(self) -> None:
        """Write the ``merged`` signal file."""
        self._write_signal("merged")

    def mark_failed(self, error: str) -> None:
        """Write the ``failed`` signal file with the error message.

        If ``signal_dir`` is not set (workstream was never prepared),
        only the in-memory error is recorded without writing to disk.
        """
        if self.state.signal_dir is not None:
            self._write_signal("failed", error)
        self.state.error = error

    def mark_reset(self) -> None:
        """Write the ``reset`` signal file."""
        self._write_signal("reset")
