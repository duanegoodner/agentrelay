"""Task runner package — one-task lifecycle state machine and I/O protocols.

Re-exports all public names so that ``from agentrelay.task_runner import X``
continues to work.

Subpackages:
    core: Protocols, state machine, I/O boundary composition.
    implementations: Concrete protocol implementations.
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
from agentrelay.task_runner.implementations import (
    GhTaskMerger,
    SignalCompletionChecker,
    TmuxTaskKickoff,
    TmuxTaskLauncher,
    WorktreeTaskPreparer,
    WorktreeTaskTeardown,
)

__all__ = [
    "ALLOWED_TASK_TRANSITIONS",
    "GhTaskMerger",
    "SignalCompletionChecker",
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
    "TmuxTaskKickoff",
    "TmuxTaskLauncher",
    "WorktreeTaskPreparer",
    "WorktreeTaskTeardown",
]
