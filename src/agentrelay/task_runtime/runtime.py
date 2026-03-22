"""Runtime state and artifacts for task execution.

This module defines the execution state enum and mutable types for tracking
task execution state and accumulating work artifacts.

Enums:
    TaskStatus: Execution state of a task (PENDING, RUNNING, PR_CREATED, PR_MERGED, FAILED).

Classes:
    TaskState: Mutable operational state of a running task.
    TaskArtifacts: Outputs produced by a task's agent.
    TaskRuntime: Mutable runtime envelope grouping Task spec and state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from agentrelay.agent import AgentAddress
from agentrelay.task import Task

# ── Enums ──


class TaskStatus(str, Enum):
    """Execution state of a task during orchestration.

    Attributes:
        PENDING: Task is waiting to be executed.
        RUNNING: Task is currently being executed by an agent.
        PR_CREATED: Agent completed work; pull request exists against worktree branch.
        PR_MERGED: Pull request has been merged into the worktree primary branch.
        FAILED: Task execution failed.
    """

    PENDING = "pending"
    RUNNING = "running"
    PR_CREATED = "pr_created"  # Agent done; PR exists against worktree branch
    PR_MERGED = "pr_merged"  # PR merged into worktree primary branch
    FAILED = "failed"


# Ordered sequence of non-failure statuses for determining current state
# from signal files.  The latest file in this sequence wins.
_TASK_STATUS_SEQUENCE: tuple[TaskStatus, ...] = (
    TaskStatus.PENDING,
    TaskStatus.RUNNING,
    TaskStatus.PR_CREATED,
    TaskStatus.PR_MERGED,
)


def _read_task_status_from_signals(signal_dir: Path) -> TaskStatus:
    """Determine task status from signal files on disk.

    ``FAILED`` takes priority if present.  Otherwise, the latest status in
    the known sequence whose signal file exists is returned.

    Args:
        signal_dir: Path to the task signal directory.  Status files are
            read from the ``status/`` subdirectory.

    Returns:
        The current task status.
    """
    status_dir = signal_dir / "status"
    if (status_dir / "failed").exists():
        return TaskStatus.FAILED
    result = TaskStatus.PENDING
    for status in _TASK_STATUS_SEQUENCE:
        if (status_dir / status.value).exists():
            result = status
    return result


# ── Runtime state and artifacts ──


@dataclass
class TaskState:
    """Mutable operational state of a running task.

    This tracks the execution progress and infrastructure of a task
    as managed by the orchestrator.

    Attributes:
        worktree_path: Filesystem path to the git worktree where the agent works,
            or None if not yet created.
        branch_name: Name of the feature branch in the worktree,
            or None if not yet created.
        signal_dir: Path to the task signal directory for signal and status
            files, or None if not yet provisioned.
        error: Error message if the task failed, or None if no error.
        attempt_num: The current attempt number (0-indexed). Used to track
            retries and conditional logic like when to start self-review.
        integration_branch: Name of the workstream integration branch this task
            targets. Set by the orchestrator before dispatch from the workstream
            runtime. None until set.
        workstream_worktree_path: Filesystem path to the shared workstream worktree.
            Set by the orchestrator before dispatch from the workstream runtime.
            None until set.
    """

    worktree_path: Optional[Path] = None
    branch_name: Optional[str] = None
    signal_dir: Optional[Path] = None
    error: Optional[str] = None
    attempt_num: int = 0
    integration_branch: Optional[str] = None
    workstream_worktree_path: Optional[Path] = None


@dataclass
class TaskArtifacts:
    """Outputs and observations produced by a task's agent.

    These are accumulated as the agent works, representing the external
    artifacts and notable observations from task execution.

    Attributes:
        pr_url: URL of the pull request created by the agent,
            or None if no PR has been created yet.
        concerns: List of design concerns or observations noted by the agent
            during execution. Defaults to empty list.
        ops_concerns: List of operational concerns (build errors, missing deps,
            tooling friction) noted by the agent. Defaults to empty list.
        agent_address: Address of the agent that executed this task (e.g. tmux
            session + pane), or None if no agent has been launched yet. Stored
            as an immutable audit trail after agent teardown.
    """

    pr_url: Optional[str] = None
    concerns: list[str] = field(default_factory=list)
    ops_concerns: list[str] = field(default_factory=list)
    agent_address: Optional[AgentAddress] = None


@dataclass
class TaskRuntime:
    """Mutable runtime envelope for a Task.

    Groups a frozen Task specification with all mutable state accumulated
    during execution. The Task spec itself never changes; TaskRuntime tracks
    how that spec is being executed.

    Attributes:
        task: The immutable Task specification being executed.
        state: Operational state (worktree, branch, signal_dir, error, attempts).
            Defaults to a new TaskState (no paths, no error, attempt 0).
        artifacts: Work outputs and observations (PR URL, concerns, agent address).
            Defaults to a new TaskArtifacts (no PR, no concerns, no agent address).
    """

    task: Task
    state: TaskState = field(default_factory=TaskState)
    artifacts: TaskArtifacts = field(default_factory=TaskArtifacts)

    @property
    def status(self) -> TaskStatus:
        """Current task status, derived from signal files on disk.

        Falls back to ``PENDING`` if no signal directory has been set,
        unless an error has been recorded (indicating failure before
        provisioning), in which case ``FAILED`` is returned.
        """
        if self.state.signal_dir is None:
            if self.state.error is not None:
                return TaskStatus.FAILED
            return TaskStatus.PENDING
        return _read_task_status_from_signals(self.state.signal_dir)

    def _write_status_signal(self, name: str, content: str = "") -> None:
        """Write a status signal file to the task signal directory."""
        assert self.state.signal_dir is not None, "signal_dir must be set"
        status_dir = self.state.signal_dir / "status"
        status_dir.mkdir(parents=True, exist_ok=True)
        (status_dir / name).write_text(content)

    def _clear_status_signals(self) -> None:
        """Remove all status signal files (used before retry)."""
        if self.state.signal_dir is None:
            return
        status_dir = self.state.signal_dir / "status"
        if status_dir.is_dir():
            for f in status_dir.iterdir():
                f.unlink()

    def mark_pending(self) -> None:
        """Write the ``pending`` status signal file."""
        self._write_status_signal("pending")

    def mark_running(self) -> None:
        """Write the ``running`` status signal file."""
        self._write_status_signal("running")

    def mark_pr_created(self) -> None:
        """Write the ``pr_created`` status signal file."""
        self._write_status_signal("pr_created")

    def mark_pr_merged(self) -> None:
        """Write the ``pr_merged`` status signal file."""
        self._write_status_signal("pr_merged")

    def mark_failed(self, error: str) -> None:
        """Write the ``failed`` status signal file with the error message.

        If ``signal_dir`` is not set (task was never prepared),
        only the in-memory error is recorded without writing to disk.
        """
        if self.state.signal_dir is not None:
            self._write_status_signal("failed", error)
        self.state.error = error

    def prepare_for_attempt(self, attempt_num: int) -> None:
        """Reset error and set attempt number before a task attempt."""
        self.state.attempt_num = attempt_num
        self.state.error = None

    def reset_for_retry(self) -> None:
        """Archive current error to concerns and reset to PENDING for retry."""
        if self.state.error:
            self.artifacts.concerns.append(
                f"attempt_{self.state.attempt_num}_error: {self.state.error}"
            )
        self._clear_status_signals()
        if self.state.signal_dir is not None:
            self.mark_pending()
        self.state.error = None
