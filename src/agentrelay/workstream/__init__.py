"""Workstream package.

Public exports include the immutable workstream specification and runtime state
types. Runtime builders are imported from ``agentrelay.workstream.runtime_builder``
to avoid package import cycles with ``agentrelay.task_graph``.
"""

from agentrelay.workstream.runtime import (
    WorkstreamArtifacts,
    WorkstreamRuntime,
    WorkstreamState,
    WorkstreamStatus,
)
from agentrelay.workstream.workstream import WorkstreamSpec

__all__ = [
    "WorkstreamArtifacts",
    "WorkstreamRuntime",
    "WorkstreamSpec",
    "WorkstreamState",
    "WorkstreamStatus",
]
