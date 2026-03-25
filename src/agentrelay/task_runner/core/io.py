"""Per-step protocols for task execution.

This module defines fine-grained protocol interfaces for each step of the
task lifecycle, a completion signal type, and a gate check result type.

Protocols:
    TaskPreparer: Prepare runtime prerequisites before agent launch.
    TaskLauncher: Launch and return the primary agent.
    TaskKickoff: Send kickoff instructions to the launched agent.
    TaskCompletionChecker: Wait for a terminal completion signal.
    TaskGateChecker: Run a completion gate command and return the result.
    TaskMerger: Merge the completed task PR.
    TaskTeardown: Release runtime resources after completion.

Classes:
    TaskCompletionSignal: Frozen signal payload from the execution boundary.
    GateCheckResult: Frozen result of a single gate check attempt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Protocol, runtime_checkable

from agentrelay.agent import Agent
from agentrelay.task_runtime import TaskRuntime


@dataclass(frozen=True)
class TaskCompletionSignal:
    """Signal payload returned by the completion checker.

    Attributes:
        outcome: Terminal completion signal from external execution.
            ``"done"`` indicates the task finished and produced a PR.
            ``"failed"`` indicates the task failed before successful completion.
        pr_url: Pull request URL for a ``"done"`` outcome, if available.
        error: Failure detail for a ``"failed"`` outcome, if available.
        concerns: Design concerns captured during execution.
        ops_concerns: Operational concerns (build errors, tooling friction)
            captured during execution.
    """

    outcome: Literal["done", "failed"]
    pr_url: Optional[str] = None
    error: Optional[str] = None
    concerns: tuple[str, ...] = ()
    ops_concerns: tuple[str, ...] = ()


# ── Per-step protocols ──


@runtime_checkable
class TaskPreparer(Protocol):
    """Prepare runtime execution prerequisites before agent launch."""

    def prepare(self, runtime: TaskRuntime) -> None:
        """Prepare runtime execution prerequisites.

        Args:
            runtime: Runtime envelope to prepare (e.g. branch, signal files).
        """
        ...


@runtime_checkable
class TaskLauncher(Protocol):
    """Launch and return the primary agent for a task."""

    def launch(self, runtime: TaskRuntime) -> Agent:
        """Launch and return the primary agent for this task runtime.

        Args:
            runtime: Runtime envelope to launch against.

        Returns:
            Agent: Live agent handle bound to this task.
        """
        ...


@runtime_checkable
class TaskKickoff(Protocol):
    """Send kickoff instructions to a launched agent."""

    def kickoff(self, runtime: TaskRuntime, agent: Agent) -> None:
        """Send kickoff instructions to the launched task agent.

        Args:
            runtime: Runtime envelope for the task being kicked off.
            agent: Live agent handle to send instructions to.
        """
        ...


@runtime_checkable
class TaskCompletionChecker(Protocol):
    """Wait for a terminal task completion signal."""

    async def wait_for_completion(self, runtime: TaskRuntime) -> TaskCompletionSignal:
        """Wait for terminal task signal from the execution boundary.

        Args:
            runtime: Runtime envelope being observed.

        Returns:
            TaskCompletionSignal: Terminal signal payload with outcome data.
        """
        ...


@dataclass(frozen=True)
class GateCheckResult:
    """Result of a single completion gate check attempt.

    Attributes:
        passed: Whether the gate command exited successfully (exit code 0).
        output: Combined stdout and stderr from the gate command.
    """

    passed: bool
    output: str


@runtime_checkable
class TaskGateChecker(Protocol):
    """Run a completion gate command and return the result."""

    def check_gate(self, runtime: TaskRuntime) -> GateCheckResult:
        """Execute the completion gate command for a task.

        Args:
            runtime: Runtime envelope with gate command and worktree path.

        Returns:
            GateCheckResult: Pass/fail outcome and captured output.
        """
        ...


@runtime_checkable
class TaskMerger(Protocol):
    """Merge the completed task PR into the integration target."""

    def merge_pr(self, runtime: TaskRuntime, pr_url: str) -> None:
        """Merge the completed task PR.

        Args:
            runtime: Runtime envelope being merged.
            pr_url: Pull request URL to merge.
        """
        ...


@runtime_checkable
class TaskTeardown(Protocol):
    """Release runtime resources after terminal completion."""

    def teardown(self, runtime: TaskRuntime) -> None:
        """Release runtime resources after terminal completion.

        Args:
            runtime: Runtime envelope whose resources should be cleaned up.
        """
        ...


__all__ = [
    "GateCheckResult",
    "TaskCompletionChecker",
    "TaskCompletionSignal",
    "TaskGateChecker",
    "TaskKickoff",
    "TaskLauncher",
    "TaskMerger",
    "TaskPreparer",
    "TaskTeardown",
]
