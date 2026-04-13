"""Workstream model for lane-level execution and integration state.

This package defines immutable workstream specifications, mutable runtime
state for each workstream lane, and the workstream-level lifecycle runner
with its I/O protocols.

Subpackages:
    core: Specs, runtime state, protocols, and runner.
    implementations: Concrete protocol implementations.
"""

from agentrelay.workstream.core.io import (
    IntegrationAutoMerger,
    IntegrationMergeChecker,
    IntegrationMergeCheckResult,
    IntegrationMergeResult,
    IntegrationResult,
    WorkstreamIntegrator,
    WorkstreamPreparer,
    WorkstreamTeardown,
)
from agentrelay.workstream.core.runner import (
    StandardWorkstreamRunner,
    WorkstreamRunner,
    WorkstreamRunResult,
)
from agentrelay.workstream.core.runtime import (
    TaskSummary,
    WorkstreamArtifacts,
    WorkstreamRuntime,
    WorkstreamState,
    WorkstreamStatus,
)
from agentrelay.workstream.core.workstream import WorkstreamSpec
from agentrelay.workstream.implementations.integration_auto_merger import (
    GhIntegrationAutoMerger,
)
from agentrelay.workstream.implementations.integration_merge_checker import (
    GhIntegrationMergeChecker,
)
from agentrelay.workstream.implementations.workstream_integrator import (
    GhWorkstreamIntegrator,
)
from agentrelay.workstream.implementations.workstream_preparer import (
    GitWorkstreamPreparer,
)
from agentrelay.workstream.implementations.workstream_teardown import (
    GitWorkstreamTeardown,
)

__all__ = [
    "GhIntegrationAutoMerger",
    "GhIntegrationMergeChecker",
    "GhWorkstreamIntegrator",
    "GitWorkstreamPreparer",
    "GitWorkstreamTeardown",
    "IntegrationAutoMerger",
    "IntegrationMergeCheckResult",
    "IntegrationMergeChecker",
    "IntegrationMergeResult",
    "IntegrationResult",
    "TaskSummary",
    "WorkstreamArtifacts",
    "WorkstreamIntegrator",
    "WorkstreamPreparer",
    "WorkstreamRunResult",
    "WorkstreamRuntime",
    "WorkstreamRunner",
    "StandardWorkstreamRunner",
    "WorkstreamSpec",
    "WorkstreamState",
    "WorkstreamStatus",
    "WorkstreamTeardown",
]
