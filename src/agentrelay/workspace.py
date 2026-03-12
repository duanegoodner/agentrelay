"""Workspace reference types for resolved task and workstream execution contexts.

These types describe the resolved workspace details (paths, branches, identifiers)
produced when workspace infrastructure is provisioned for execution.

Classes:
    LocalWorkspaceRef: Resolved local workspace (worktree path + branch).

Type aliases:
    WorkspaceRef: Currently ``LocalWorkspaceRef``; extend to a union when additional
        workspace backends (e.g. cloud/remote execution) are supported.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LocalWorkspaceRef:
    """Resolved local workspace details for one execution attempt.

    Attributes:
        worktree_path: Filesystem path where task work should run.
        branch_name: Branch name used for this attempt.
    """

    worktree_path: Path
    branch_name: str


WorkspaceRef = LocalWorkspaceRef
"""Workspace reference type alias.

Currently only ``LocalWorkspaceRef`` is supported. When additional workspace
backends are needed (e.g. cloud/remote execution), extend this to a union::

    WorkspaceRef = LocalWorkspaceRef | CloudWorkspaceRef
"""


__all__ = [
    "LocalWorkspaceRef",
    "WorkspaceRef",
]
