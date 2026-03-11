"""Task runner package — one-task lifecycle state machine and I/O protocols.

Re-exports all public names so that ``from agentrelay.task_runner import X``
continues to work after promotion from a single module to a package.
"""

from agentrelay.task_runner.io import (
    TaskCompletionChecker,
    TaskCompletionSignal,
    TaskKickoff,
    TaskLauncher,
    TaskMerger,
    TaskPreparer,
    TaskRunnerIO,
    TaskTeardown,
)
from agentrelay.task_runner.runner import (
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
