"""Core task runner abstractions — protocols, state machine, dispatch, and I/O boundary.

This subpackage defines the task lifecycle protocols, completion signal type,
composed I/O boundary, the :class:`TaskRunner` protocol, the
:class:`StandardTaskRunner` state machine, and the :class:`StepDispatch`
generic dispatch table.
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

__all__ = [
    "ALLOWED_TASK_TRANSITIONS",
    "DispatchKey",
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
]
