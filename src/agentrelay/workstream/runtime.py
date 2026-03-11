"""Runtime state and artifacts for workstream execution.

This module defines mutable runtime types for tracking the execution lifecycle
of a workstream lane (worktree/branch context) during orchestration.

Enums:
    WorkstreamStatus: Execution state of a workstream lane.

Classes:
    WorkstreamState: Mutable operational state of a workstream lane.
    WorkstreamArtifacts: Outputs produced while advancing a workstream lane.
    WorkstreamRuntime: Mutable runtime envelope grouping workstream spec and state.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from agentrelay.workstream.workstream import WorkstreamSpec


class WorkstreamStatus(str, Enum):
    """Execution state of a workstream during orchestration.

    Attributes:
        PENDING: Workstream has not started provisioning/execution.
        ACTIVE: Workstream is currently active (for example has running tasks).
        MERGED: Workstream integration flow is complete and merged.
        FAILED: Workstream execution failed.
    """

    PENDING = "pending"
    ACTIVE = "active"
    MERGED = "merged"
    FAILED = "failed"


@dataclass
class WorkstreamState:
    """Mutable operational state of a workstream lane.

    Attributes:
        status: Current lane lifecycle status.
        worktree_path: Filesystem path to the worktree used for this lane, or
            ``None`` if not provisioned yet.
        branch_name: Primary branch name used for this lane, or ``None`` until set.
        error: Error message if lane execution failed, else ``None``.
        active_task_id: Task ID currently active in this lane, else ``None``.
    """

    status: WorkstreamStatus = WorkstreamStatus.PENDING
    worktree_path: Optional[Path] = None
    branch_name: Optional[str] = None
    error: Optional[str] = None
    active_task_id: Optional[str] = None


@dataclass
class WorkstreamArtifacts:
    """Outputs and observations produced while advancing a workstream.

    Attributes:
        merge_pr_url: URL of the workstream integration PR, or ``None`` if absent.
        concerns: List of notable observations or concerns for this lane.
    """

    merge_pr_url: Optional[str] = None
    concerns: list[str] = field(default_factory=list)


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


# ── Read-only view protocols ──


@runtime_checkable
class WorkstreamStateView(Protocol):
    """Read-only view of WorkstreamState.

    A Protocol satisfied structurally by WorkstreamState. Exposes all fields
    as read-only properties so that holders of a WorkstreamStateView reference
    cannot mutate the underlying state.
    """

    @property
    def status(self) -> WorkstreamStatus: ...

    @property
    def worktree_path(self) -> Optional[Path]: ...

    @property
    def branch_name(self) -> Optional[str]: ...

    @property
    def error(self) -> Optional[str]: ...

    @property
    def active_task_id(self) -> Optional[str]: ...


@runtime_checkable
class WorkstreamArtifactsView(Protocol):
    """Read-only view of WorkstreamArtifacts.

    A Protocol satisfied structurally by WorkstreamArtifacts. The ``concerns``
    property returns ``Sequence[str]`` (not ``list[str]``) so that callers
    cannot mutate the list through the view.
    """

    @property
    def merge_pr_url(self) -> Optional[str]: ...

    @property
    def concerns(self) -> Sequence[str]: ...


@runtime_checkable
class WorkstreamRuntimeView(Protocol):
    """Read-only view of WorkstreamRuntime.

    A Protocol satisfied structurally by WorkstreamRuntime. Nested state and
    artifacts are exposed as their respective view protocols, ensuring
    read-only enforcement propagates through the object graph.
    """

    @property
    def spec(self) -> WorkstreamSpec: ...

    @property
    def state(self) -> WorkstreamStateView: ...

    @property
    def artifacts(self) -> WorkstreamArtifactsView: ...
