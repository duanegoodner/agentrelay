"""Builder for :class:`StandardTaskRunner` with default implementations.

Functions:
    build_standard_runner: Build a StandardTaskRunner wired for worktree + tmux
        + Claude Code.

.. module:: agentrelay.task_runner.implementations.standard_runner_builder
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from agentrelay.task_graph import TaskGraph
from agentrelay.task_runner.core.dispatch import StepDispatch
from agentrelay.task_runner.core.io import (
    TaskCompletionChecker,
    TaskMerger,
    TaskPreparer,
    TaskTeardown,
)
from agentrelay.task_runner.core.runner import StandardTaskRunner
from agentrelay.task_runner.implementations.task_completion_checker import (
    SignalCompletionChecker,
)
from agentrelay.task_runner.implementations.task_kickoff import TmuxTaskKickoff
from agentrelay.task_runner.implementations.task_launcher import TmuxTaskLauncher
from agentrelay.task_runner.implementations.task_merger import GhTaskMerger
from agentrelay.task_runner.implementations.task_preparer import WorktreeTaskPreparer
from agentrelay.task_runner.implementations.task_teardown import WorktreeTaskTeardown
from agentrelay.task_runtime import TaskRuntime


def build_standard_runner(
    repo_path: Path,
    graph_name: str,
    graph: TaskGraph,
    keep_panes: bool = False,
    poll_interval: float = 2.0,
    context_content: Optional[str] = None,
) -> StandardTaskRunner:
    """Build the standard runner for worktree + tmux + Claude Code.

    All steps use ``StepDispatch`` ``default`` since only one
    framework/environment combo currently exists.

    When adding a new ``AgentFramework`` or ``AgentEnvironment``, add keyed
    entries to the ``StepDispatch`` tables for steps that have distinct
    implementations. Refer to the sensitivity table in
    :class:`StandardTaskRunner`'s docstring.

    Dispatch table (current):

    +-----------------------+----------------------------+-----------------------+
    | Step                  | Implementation             | Notes                 |
    +=======================+============================+=======================+
    | preparer              | WorktreeTaskPreparer       | env/fw agnostic       |
    +-----------------------+----------------------------+-----------------------+
    | launcher              | TmuxTaskLauncher           | will need entries     |
    +-----------------------+----------------------------+-----------------------+
    | kickoff               | TmuxTaskKickoff            | will need entries     |
    +-----------------------+----------------------------+-----------------------+
    | completion_checker    | SignalCompletionChecker     | may need entries      |
    +-----------------------+----------------------------+-----------------------+
    | merger                | GhTaskMerger               | env/fw agnostic       |
    +-----------------------+----------------------------+-----------------------+
    | teardown              | WorktreeTaskTeardown       | will need entries     |
    +-----------------------+----------------------------+-----------------------+

    Args:
        repo_path: Path to the bare/main repository.
        graph_name: Name of the task graph being executed.
        graph: The task graph (used to compute dependency descriptions).
        keep_panes: Whether to keep tmux panes after teardown.
        poll_interval: Seconds between completion signal polls.
        context_content: Optional context content to write to the signal dir.

    Returns:
        A fully wired :class:`StandardTaskRunner`.
    """
    tmux_launcher = TmuxTaskLauncher()
    tmux_kickoff = TmuxTaskKickoff()

    def _make_preparer(runtime: TaskRuntime) -> TaskPreparer:
        dep_ids = graph.dependency_ids(runtime.task.id)
        dep_descs = {did: graph.task(did).description for did in dep_ids}
        return WorktreeTaskPreparer(
            repo_path=repo_path,
            graph_name=graph_name,
            dependency_descriptions=dep_descs,
            context_content=context_content,
        )

    def _make_merger(runtime: TaskRuntime) -> TaskMerger:
        return GhTaskMerger(repo_path=repo_path)

    def _make_completion_checker(runtime: TaskRuntime) -> TaskCompletionChecker:
        return SignalCompletionChecker(poll_interval=poll_interval)

    def _make_teardown(runtime: TaskRuntime) -> TaskTeardown:
        return WorktreeTaskTeardown(repo_path=repo_path, keep_panes=keep_panes)

    return StandardTaskRunner(
        _preparer=StepDispatch(default=_make_preparer),
        _launcher=StepDispatch(default=lambda rt: tmux_launcher),
        _kickoff=StepDispatch(default=lambda rt: tmux_kickoff),
        _completion_checker=StepDispatch(default=_make_completion_checker),
        _merger=StepDispatch(default=_make_merger),
        _teardown=StepDispatch(default=_make_teardown),
    )
