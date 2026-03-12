"""Core task runner abstractions — protocols, state machine, and I/O boundary.

This subpackage defines the task lifecycle protocols, completion signal type,
composed I/O boundary, and the TaskRunner state machine.
"""

from agentrelay.task_runner.core.io import (
    TaskCompletionChecker,
    TaskCompletionSignal,
    TaskKickoff,
    TaskLauncher,
    TaskMerger,
    TaskPreparer,
    TaskRunnerIO,
    TaskTeardown,
)
from agentrelay.task_runner.core.runner import (
    ALLOWED_TASK_TRANSITIONS,
    TaskRunner,
    TaskRunResult,
    TearDownMode,
)

__all__ = [
    "ALLOWED_TASK_TRANSITIONS",
    "TaskCompletionChecker",
    "TaskCompletionSignal",
    "TaskKickoff",
    "TaskLauncher",
    "TaskMerger",
    "TaskPreparer",
    "TaskRunResult",
    "TaskRunner",
    "TaskRunnerIO",
    "TaskTeardown",
    "TearDownMode",
]
