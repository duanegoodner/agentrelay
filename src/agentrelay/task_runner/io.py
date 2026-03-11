"""Per-step protocols and composed I/O boundary for task execution.

This module defines fine-grained protocol interfaces for each step of the
task lifecycle, a completion signal type, and a :class:`TaskRunnerIO`
dataclass that composes them into a single I/O boundary used by
:class:`~agentrelay.task_runner.runner.TaskRunner`.

Protocols:
    TaskPreparer: Prepare runtime prerequisites before agent launch.
    TaskLauncher: Launch and return the primary agent.
    TaskKickoff: Send kickoff instructions to the launched agent.
    TaskCompletionChecker: Wait for a terminal completion signal.
    TaskMerger: Merge the completed task PR.
    TaskTeardown: Release runtime resources after completion.

Classes:
    TaskCompletionSignal: Frozen signal payload from the execution boundary.
    TaskRunnerIO: Frozen composition of per-step protocol implementations.
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
        concerns: Semantic concerns captured during execution.
    """

    outcome: Literal["done", "failed"]
    pr_url: Optional[str] = None
    error: Optional[str] = None
    concerns: tuple[str, ...] = ()


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

    def kickoff(self, runtime: TaskRuntime) -> None:
        """Send kickoff instructions to the launched task agent.

        Args:
            runtime: Runtime envelope whose agent should be activated.
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


# ── Composed I/O boundary ──


@dataclass(frozen=True)
class TaskRunnerIO:
    """Composed I/O boundary for :class:`TaskRunner`.

    Each field holds a protocol implementation for one step of the task
    lifecycle.  This replaces the previous monolithic ``TaskRunnerIO``
    Protocol with a dataclass that allows independent composition,
    testing, and swapping of each step.

    Attributes:
        preparer: Prepare runtime prerequisites before launch.
        launcher: Launch and return the primary agent.
        kickoff_sender: Send kickoff instructions to the launched agent.
        completion_checker: Wait for a terminal completion signal.
        merger: Merge the completed task PR.
        teardown_handler: Release runtime resources after completion.
    """

    preparer: TaskPreparer
    launcher: TaskLauncher
    kickoff_sender: TaskKickoff
    completion_checker: TaskCompletionChecker
    merger: TaskMerger
    teardown_handler: TaskTeardown


__all__ = [
    "TaskCompletionChecker",
    "TaskCompletionSignal",
    "TaskKickoff",
    "TaskLauncher",
    "TaskMerger",
    "TaskPreparer",
    "TaskRunnerIO",
    "TaskTeardown",
]
