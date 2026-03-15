"""Concrete task runner protocol implementations.

This subpackage contains environment-specific implementations of the
per-step protocols defined in ``task_runner.core.io``. Each module is named
after the protocol it implements (e.g. ``task_preparer.py`` contains
implementations of :class:`~agentrelay.task_runner.core.io.TaskPreparer`).
"""

from agentrelay.task_runner.implementations.standard_runner_builder import (
    build_standard_runner,
)
from agentrelay.task_runner.implementations.task_completion_checker import (
    SignalCompletionChecker,
)
from agentrelay.task_runner.implementations.task_kickoff import TmuxTaskKickoff
from agentrelay.task_runner.implementations.task_launcher import TmuxTaskLauncher
from agentrelay.task_runner.implementations.task_merger import GhTaskMerger
from agentrelay.task_runner.implementations.task_preparer import (
    WorktreeTaskPreparer,
)
from agentrelay.task_runner.implementations.task_teardown import (
    WorktreeTaskTeardown,
)

__all__ = [
    "GhTaskMerger",
    "SignalCompletionChecker",
    "TmuxTaskKickoff",
    "TmuxTaskLauncher",
    "WorktreeTaskPreparer",
    "WorktreeTaskTeardown",
    "build_standard_runner",
]
