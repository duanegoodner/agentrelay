"""Workstream specifications for grouping related task execution.

This module defines :class:`WorkstreamSpec`, an immutable configuration object
for a logical stream of related tasks that typically share a worktree and
integration branch strategy.
"""

from dataclasses import dataclass
from typing import Optional

from agentrelay.sandbox import IsolationConfig


@dataclass(frozen=True)
class WorkstreamSpec:
    """Immutable specification for a task workstream.

    A workstream models a branch/worktree execution lane that one or more tasks
    can target. Parent/child workstream relationships are defined at the spec
    level and validated by graph-building layers.

    Attributes:
        id: Unique workstream identifier within a task graph.
        parent_workstream_id: Optional parent workstream ID for hierarchical
            stream topologies (for example ``A`` -> ``A.1`` and ``A.2``).
        base_branch: Branch name used as the base when creating workstream
            integration branches or worktrees. Defaults to ``"main"``.
        merge_target_branch: Branch name the workstream ultimately merges into.
            Defaults to ``"main"``.
        auto_merge: When ``True``, the orchestrator merges the integration PR
            automatically after creation — provided no task in the workstream
            recorded a design concern.  Defaults to ``False``.
    """

    id: str
    parent_workstream_id: Optional[str] = None
    base_branch: str = "main"
    merge_target_branch: str = "main"
    auto_merge: bool = False
    isolation: Optional[IsolationConfig] = None
