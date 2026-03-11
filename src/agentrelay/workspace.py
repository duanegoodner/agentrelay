"""Workspace reference types for resolved task and workstream execution contexts.

These types describe the resolved workspace details (paths, branches, identifiers)
produced when workspace infrastructure is provisioned for execution.

Classes:
    LocalWorkspaceRef: Resolved local workspace (worktree path + branch).
    RemoteWorkspaceRef: Resolved remote workspace (opaque ID + branch + URIs).

Type aliases:
    WorkspaceRef: Union of local and remote workspace references.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional


@dataclass(frozen=True)
class LocalWorkspaceRef:
    """Resolved local workspace details for one execution attempt.

    Attributes:
        worktree_path: Filesystem path where task work should run.
        branch_name: Branch name used for this attempt.
        kind: Discriminator for local workspace refs.
    """

    worktree_path: Path
    branch_name: str
    kind: Literal["local"] = field(default="local", init=False)


@dataclass(frozen=True)
class RemoteWorkspaceRef:
    """Resolved remote workspace details for one execution attempt.

    Attributes:
        workspace_id: Opaque workspace identifier from remote execution backend.
        branch_name: Branch name used for this attempt.
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
"""Union of all supported workspace reference types."""


__all__ = [
    "LocalWorkspaceRef",
    "RemoteWorkspaceRef",
    "WorkspaceRef",
]
