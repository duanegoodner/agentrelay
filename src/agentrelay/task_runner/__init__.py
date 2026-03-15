"""Task runner package — one-task lifecycle state machine, dispatch, and I/O protocols.

Re-exports all public names so that ``from agentrelay.task_runner import X``
continues to work.

Subpackages:
    core: Protocols, state machine, dispatch, I/O boundary composition.
    implementations: Concrete protocol implementations and builder.
"""

from agentrelay.task_runner.core.dispatch import DispatchKey, StepDispatch
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
    StandardTaskRunner,
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
    build_standard_runner,
)

__all__ = [
    "ALLOWED_TASK_TRANSITIONS",
    "DispatchKey",
    "GhTaskMerger",
    "SignalCompletionChecker",
    "StandardTaskRunner",
    "StepDispatch",
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
    "build_standard_runner",
]
