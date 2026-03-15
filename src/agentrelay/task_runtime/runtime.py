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

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

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


# ── Runtime state and artifacts ──


@dataclass
class TaskState:
    """Mutable operational state of a running task.

    This tracks the execution progress and infrastructure of a task
    as managed by the orchestrator.

    Attributes:
        status: Current execution state (TaskStatus enum).
        worktree_path: Filesystem path to the git worktree where the agent works,
            or None if not yet created.
        branch_name: Name of the feature branch in the worktree,
            or None if not yet created.
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

    status: TaskStatus = TaskStatus.PENDING
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
        agent_address: Address of the agent that executed this task (e.g. tmux
            session + pane), or None if no agent has been launched yet. Stored
            as an immutable audit trail after agent teardown.
    """

    pr_url: Optional[str] = None
    concerns: list[str] = field(default_factory=list)
    agent_address: Optional[AgentAddress] = None


@dataclass
class TaskRuntime:
    """Mutable runtime envelope for a Task.

    Groups a frozen Task specification with all mutable state accumulated
    during execution. The Task spec itself never changes; TaskRuntime tracks
    how that spec is being executed.

    Attributes:
        task: The immutable Task specification being executed.
        state: Operational state (status, worktree, branch, error, attempts).
            Defaults to a new TaskState (PENDING, no paths, no error, attempt 0).
        artifacts: Work outputs and observations (PR URL, concerns, agent address).
            Defaults to a new TaskArtifacts (no PR, no concerns, no agent address).
    """

    task: Task
    state: TaskState = field(default_factory=TaskState)
    artifacts: TaskArtifacts = field(default_factory=TaskArtifacts)

    def prepare_for_attempt(self, attempt_num: int) -> None:
        """Reset error and set attempt number before a task attempt."""
        self.state.attempt_num = attempt_num
        self.state.error = None

    def mark_failed(self, error: str) -> None:
        """Transition to FAILED with an error message."""
        self.state.status = TaskStatus.FAILED
        self.state.error = error

    def reset_for_retry(self) -> None:
        """Archive current error to concerns and reset to PENDING for retry."""
        if self.state.error:
            self.artifacts.concerns.append(
                f"attempt_{self.state.attempt_num}_error: {self.state.error}"
            )
        self.state.status = TaskStatus.PENDING
        self.state.error = None

    def mark_pending(self) -> None:
        """Set status to PENDING (used for retry normalization)."""
        self.state.status = TaskStatus.PENDING


# ── Read-only view protocols ──


@runtime_checkable
class TaskStateView(Protocol):
    """Read-only view of TaskState.

    A Protocol satisfied structurally by TaskState. Exposes all fields as
    read-only properties so that holders of a TaskStateView reference cannot
    mutate the underlying state.
    """

    @property
    def status(self) -> TaskStatus: ...

    @property
    def worktree_path(self) -> Optional[Path]: ...

    @property
    def branch_name(self) -> Optional[str]: ...

    @property
    def signal_dir(self) -> Optional[Path]: ...

    @property
    def error(self) -> Optional[str]: ...

    @property
    def attempt_num(self) -> int: ...

    @property
    def integration_branch(self) -> Optional[str]: ...

    @property
    def workstream_worktree_path(self) -> Optional[Path]: ...


@runtime_checkable
class TaskArtifactsView(Protocol):
    """Read-only view of TaskArtifacts.

    A Protocol satisfied structurally by TaskArtifacts. The ``concerns``
    property returns ``Sequence[str]`` (not ``list[str]``) so that callers
    cannot mutate the list through the view.
    """

    @property
    def pr_url(self) -> Optional[str]: ...

    @property
    def concerns(self) -> Sequence[str]: ...

    @property
    def agent_address(self) -> Optional[AgentAddress]: ...


@runtime_checkable
class TaskRuntimeView(Protocol):
    """Read-only view of TaskRuntime.

    A Protocol satisfied structurally by TaskRuntime. Nested state and
    artifacts are exposed as their respective view protocols, ensuring
    read-only enforcement propagates through the object graph.
    """

    @property
    def task(self) -> Task: ...

    @property
    def state(self) -> TaskStateView: ...

    @property
    def artifacts(self) -> TaskArtifactsView: ...
