"""Runtime state, artifacts, and addressing types for task execution.

This module defines mutable types for tracking task execution state,
accumulating work artifacts, and addressing running agents.

Classes:
    TaskState: Mutable operational state of a running task.
    TaskArtifacts: Outputs produced by a task's agent.
    AgentAddress: Abstract base for addressing running agents.
    TmuxAddress: Concrete address for agents in tmux panes.
    TaskRuntime: Mutable runtime envelope grouping Task spec and state.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from agentrelaysmall.task import Task, TaskStatus

if TYPE_CHECKING:
    from agentrelaysmall.agent import Agent


# ── Agent addressing ──


class AgentAddress(ABC):
    """Abstract base for addressing a running agent instance.

    This protocol defines the interface for different ways of addressing
    agents, enabling extensibility to various execution environments
    (tmux panes, cloud endpoints, subprocess IDs, etc.).

    Attributes:
        label: A human-readable string identifier for the agent's location.
    """

    @property
    @abstractmethod
    def label(self) -> str:
        """Return a human-readable identifier for this agent's location.

        Returns:
            String representation of the agent's address/location.
        """
        ...


@dataclass(frozen=True)
class TmuxAddress(AgentAddress):
    """Address of an agent running in a tmux pane.

    Attributes:
        session: The name of the tmux session.
        pane_id: The identifier of the tmux pane (e.g., "%1", "%2").
    """

    session: str
    pane_id: str

    @property
    def label(self) -> str:
        """Return a human-readable identifier combining session and pane.

        Returns:
            String in format "session:pane_id" (e.g., "agentrelay:%1").
        """
        return f"{self.session}:{self.pane_id}"


# ── Runtime state and artifacts ──


@dataclass
class TaskState:
    """Mutable operational state of a running task.

    This tracks the execution progress and infrastructure of a task
    as managed by the orchestrator.

    Attributes:
        status: Current execution state (TaskStatus enum).
        worktree_path: Path to the git worktree where the agent works,
            or None if not yet created.
        branch_name: Name of the feature branch in the worktree,
            or None if not yet created.
        error: Error message if the task failed, or None if no error.
        attempt_num: The current attempt number (0-indexed). Used to track
            retries and conditional logic like when to start self-review.
    """

    status: TaskStatus = TaskStatus.PENDING
    worktree_path: Optional[str] = None
    branch_name: Optional[str] = None
    error: Optional[str] = None
    attempt_num: int = 0


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
    """

    pr_url: Optional[str] = None
    concerns: list[str] = field(default_factory=list)


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
        artifacts: Work outputs and observations (PR URL, concerns).
            Defaults to a new TaskArtifacts (no PR, no concerns).
        agent: The live running agent instance, or None until the orchestrator
            spawns the agent.
    """

    task: Task
    state: TaskState = field(default_factory=TaskState)
    artifacts: TaskArtifacts = field(default_factory=TaskArtifacts)
    agent: Optional[Agent] = None
