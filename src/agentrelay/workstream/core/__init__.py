"""Core workstream abstractions — specs, runtime state, protocols, and runners.

This subpackage defines the immutable workstream specifications, mutable runtime
state, lifecycle protocols, and the workstream runner state machine.
"""

from agentrelay.workstream.core.io import (
    WorkstreamMerger,
    WorkstreamPreparer,
    WorkstreamRunnerIO,
    WorkstreamTeardown,
)
from agentrelay.workstream.core.runner import WorkstreamRunner, WorkstreamRunResult
from agentrelay.workstream.core.runtime import (
    WorkstreamArtifacts,
    WorkstreamArtifactsView,
    WorkstreamRuntime,
    WorkstreamRuntimeView,
    WorkstreamState,
    WorkstreamStateView,
    WorkstreamStatus,
)
from agentrelay.workstream.core.runtime_builder import WorkstreamRuntimeBuilder
from agentrelay.workstream.core.workstream import WorkstreamSpec

__all__ = [
    "WorkstreamArtifacts",
    "WorkstreamArtifactsView",
    "WorkstreamMerger",
    "WorkstreamPreparer",
    "WorkstreamRunResult",
    "WorkstreamRuntime",
    "WorkstreamRuntimeView",
    "WorkstreamRuntimeBuilder",
    "WorkstreamRunner",
    "WorkstreamRunnerIO",
    "WorkstreamSpec",
    "WorkstreamState",
    "WorkstreamStateView",
    "WorkstreamStatus",
    "WorkstreamTeardown",
]
