"""Task runtime model for mutable per-task execution state.

This package contains runtime envelopes and lifecycle state for tasks derived
from immutable task specs, plus initialization helpers used to create runtime
objects from a validated task graph.
"""

from agentrelay.task_runtime.builder import TaskRuntimeBuilder
from agentrelay.task_runtime.runtime import (
    TaskArtifacts,
    TaskRuntime,
    TaskState,
    TaskStatus,
)

__all__ = [
    "TaskArtifacts",
    "TaskRuntimeBuilder",
    "TaskRuntime",
    "TaskState",
    "TaskStatus",
]
