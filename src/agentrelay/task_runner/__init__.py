"""Task runner package — one-task lifecycle state machine, dispatch, and I/O protocols.

Re-exports all public names so that ``from agentrelay.task_runner import X``
continues to work.

Subpackages:
    core: Protocols, state machine, dispatch, I/O boundary composition.
    implementations: Concrete protocol implementations.
"""

from agentrelay.task_runner.core.dispatch import DispatchKey, StepDispatch
from agentrelay.task_runner.core.io import (
    GateCheckResult,
    TaskCompletionChecker,
    TaskCompletionSignal,
    TaskGateChecker,
    TaskKickoff,
    TaskLauncher,
    TaskLogCapture,
    TaskMerger,
    TaskPreparer,
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
    ShellGateChecker,
    SignalCompletionChecker,
    TmuxTaskKickoff,
    TmuxTaskLauncher,
    WorktreeTaskLogCapture,
    WorktreeTaskPreparer,
    WorktreeTaskTeardown,
)

__all__ = [
    "ALLOWED_TASK_TRANSITIONS",
    "DispatchKey",
    "GateCheckResult",
    "GhTaskMerger",
    "ShellGateChecker",
    "SignalCompletionChecker",
    "StandardTaskRunner",
    "StepDispatch",
    "TaskCompletionChecker",
    "TaskCompletionSignal",
    "TaskGateChecker",
    "TaskKickoff",
    "TaskLauncher",
    "TaskLogCapture",
    "TaskMerger",
    "TaskPreparer",
    "TaskRunResult",
    "TaskRunner",
    "TaskTeardown",
    "TearDownMode",
    "TmuxTaskKickoff",
    "TmuxTaskLauncher",
    "WorktreeTaskLogCapture",
    "WorktreeTaskPreparer",
    "WorktreeTaskTeardown",
]
