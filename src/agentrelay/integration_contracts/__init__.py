"""Integration boundary contracts for non-prototype side effects.

This package defines protocol interfaces for external systems used by task
execution. These contracts intentionally describe semantic behavior only and do
not define concrete file names or directory layouts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional, Protocol, runtime_checkable

from agentrelay.agent import Agent
from agentrelay.task_runtime import TaskRuntime
from agentrelay.workstream import WorkstreamRuntime


@dataclass(frozen=True)
class LocalWorkspaceRef:
    """Resolved local workspace details for one task execution attempt.

    Attributes:
        worktree_path: Filesystem path where task work should run.
        branch_name: Branch name used for this task attempt.
        kind: Discriminator for local workspace refs.
    """

    worktree_path: Path
    branch_name: str
    kind: Literal["local"] = field(default="local", init=False)


@dataclass(frozen=True)
class RemoteWorkspaceRef:
    """Resolved remote workspace details for one task execution attempt.

    Attributes:
        workspace_id: Opaque workspace identifier from remote execution backend.
        branch_name: Branch name used for this task attempt.
        workspace_uri: Optional backend URI for this workspace.
        repo_ref: Optional repository/revision reference used by this workspace.
        execution_target: Optional run/job/pod identifier for active execution.
        artifacts_uri: Optional URI where task artifacts/signals are written.
        kind: Discriminator for remote workspace refs.
    """

    workspace_id: str
    branch_name: str
    workspace_uri: Optional[str] = None
    repo_ref: Optional[str] = None
    execution_target: Optional[str] = None
    artifacts_uri: Optional[str] = None
    kind: Literal["remote"] = field(default="remote", init=False)


WorkspaceRef = LocalWorkspaceRef | RemoteWorkspaceRef


@dataclass(frozen=True)
class CompletionSignal:
    """Semantic completion payload observed from a signal boundary.

    Attributes:
        outcome: Terminal outcome marker from external task execution.
            ``"done"`` means task work finished and should have a mergeable PR.
            ``"failed"`` means task work failed before successful completion.
        pr_url: Pull request URL for a successful completion path, if available.
        error: Failure detail for a failed completion path, if available.
        concerns: Optional semantic concerns captured during execution.
    """

    outcome: Literal["done", "failed"]
    pr_url: Optional[str] = None
    error: Optional[str] = None
    concerns: tuple[str, ...] = ()


@runtime_checkable
class WorkspaceAdapter(Protocol):
    """Boundary for workspace provisioning and cleanup."""

    def ensure_workspace(
        self,
        runtime: TaskRuntime,
        workstream: WorkstreamRuntime,
    ) -> WorkspaceRef:
        """Provision (or resolve) workspace infrastructure for a task.

        Args:
            runtime: Task runtime being prepared.
            workstream: Workstream runtime providing lane-level context.

        Returns:
            WorkspaceRef: Resolved workspace reference and branch context.
        """
        ...

    def cleanup_workspace(
        self,
        runtime: TaskRuntime,
        workstream: WorkstreamRuntime,
    ) -> None:
        """Tear down task workspace infrastructure when requested.

        Args:
            runtime: Task runtime being cleaned up.
            workstream: Workstream runtime providing lane-level context.
        """
        ...


@runtime_checkable
class SignalAdapter(Protocol):
    """Boundary for instruction publication and completion signaling."""

    def write_instructions(self, runtime: TaskRuntime, instructions_text: str) -> Path:
        """Publish instructions for a task and return the instruction path.

        Args:
            runtime: Task runtime associated with this instruction write.
            instructions_text: Rendered instruction content to publish.

        Returns:
            Path: Location that agents should read for kickoff.
        """
        ...

    async def wait_for_completion(
        self,
        runtime: TaskRuntime,
        timeout_seconds: Optional[float] = None,
    ) -> CompletionSignal:
        """Wait for a terminal completion signal for a task.

        Args:
            runtime: Task runtime being observed.
            timeout_seconds: Optional wait timeout. ``None`` means adapter default.

        Returns:
            CompletionSignal: Terminal completion payload.
        """
        ...


@runtime_checkable
class PullRequestAdapter(Protocol):
    """Boundary for pull-request operations used in task lifecycle."""

    def merge_task_pr(self, runtime: TaskRuntime, pr_url: str) -> None:
        """Merge a task pull request into its integration target.

        Args:
            runtime: Task runtime whose pull request is being merged.
            pr_url: Pull request URL to merge.
        """
        ...


@runtime_checkable
class AgentLauncher(Protocol):
    """Boundary for launching and activating a live coding agent."""

    def launch_task_agent(self, runtime: TaskRuntime) -> Agent:
        """Launch and return the live agent for a task runtime.

        Args:
            runtime: Task runtime whose primary agent should be launched.

        Returns:
            Agent: Live agent handle.
        """
        ...

    def send_kickoff(self, agent: Agent, instructions_path: Path) -> None:
        """Activate a launched agent with task instructions.

        Args:
            agent: Live agent handle returned by :meth:`launch_task_agent`.
            instructions_path: Path to instructions the agent should read.
        """
        ...


@dataclass(frozen=True)
class IntegrationAdapters:
    """Grouped integration boundaries used by concrete runner composition.

    Attributes:
        workspace: Workspace provisioning boundary.
        signals: Signal publish/poll boundary.
        pull_requests: Pull-request operations boundary.
        agent_launcher: Agent launch/kickoff boundary.
    """

    workspace: WorkspaceAdapter
    signals: SignalAdapter
    pull_requests: PullRequestAdapter
    agent_launcher: AgentLauncher


__all__ = [
    "AgentLauncher",
    "CompletionSignal",
    "IntegrationAdapters",
    "LocalWorkspaceRef",
    "PullRequestAdapter",
    "RemoteWorkspaceRef",
    "SignalAdapter",
    "WorkspaceAdapter",
    "WorkspaceRef",
]
