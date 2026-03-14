"""Workstream model for lane-level execution and integration state.

This package defines immutable workstream specifications, mutable runtime
state for each workstream lane, runtime initialization helpers, and the
workstream-level lifecycle runner with its I/O protocols.

Subpackages:
    core: Specs, runtime state, protocols, and runner.
    implementations: Concrete protocol implementations.
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
from agentrelay.workstream.implementations.workstream_merger import (
    GhWorkstreamMerger,
)
from agentrelay.workstream.implementations.workstream_preparer import (
    GitWorkstreamPreparer,
)
from agentrelay.workstream.implementations.workstream_teardown import (
    GitWorkstreamTeardown,
)

__all__ = [
    "GhWorkstreamMerger",
    "GitWorkstreamPreparer",
    "GitWorkstreamTeardown",
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
