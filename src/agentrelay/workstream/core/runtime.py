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
        MERGE_READY: All tasks completed; workstream is ready to merge integration branch.
        MERGED: Workstream integration flow is complete and merged.
        FAILED: Workstream execution failed.
    """

    PENDING = "pending"
    ACTIVE = "active"
    MERGE_READY = "merge_ready"
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
    """

    status: WorkstreamStatus = WorkstreamStatus.PENDING
    worktree_path: Optional[Path] = None
    branch_name: Optional[str] = None
    error: Optional[str] = None


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

    def mark_failed(self, error: str) -> None:
        """Transition to FAILED with an error message."""
        self.state.status = WorkstreamStatus.FAILED
        self.state.error = error

    def mark_merge_ready(self) -> None:
        """Transition to MERGE_READY."""
        self.state.status = WorkstreamStatus.MERGE_READY

    def mark_merged(self) -> None:
        """Transition to MERGED."""
        self.state.status = WorkstreamStatus.MERGED
