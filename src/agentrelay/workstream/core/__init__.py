"""Core workstream abstractions — specs, runtime state, protocols, and runners.

This subpackage defines the immutable workstream specifications, mutable runtime
state, lifecycle protocols, and the workstream runner state machine.
"""

from agentrelay.workstream.core.io import (
    WorkstreamMerger,
    WorkstreamPreparer,
    WorkstreamTeardown,
)
from agentrelay.workstream.core.runner import WorkstreamRunner, WorkstreamRunResult
from agentrelay.workstream.core.runtime import (
    WorkstreamArtifacts,
    WorkstreamRuntime,
    WorkstreamState,
    WorkstreamStatus,
)
from agentrelay.workstream.core.workstream import WorkstreamSpec

__all__ = [
    "WorkstreamArtifacts",
    "WorkstreamMerger",
    "WorkstreamPreparer",
    "WorkstreamRunResult",
    "WorkstreamRuntime",
    "WorkstreamRunner",
    "WorkstreamSpec",
    "WorkstreamState",
    "WorkstreamStatus",
    "WorkstreamTeardown",
]
