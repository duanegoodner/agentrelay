"""Implementations of :class:`~agentrelay.task_runner.core.io.TaskLauncher`.

Classes:
    TmuxTaskLauncher: Launches a Claude Code agent in a tmux pane.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentrelay.agent import Agent, TmuxAgent
from agentrelay.task_runtime import TaskRuntime


@dataclass
class TmuxTaskLauncher:
    """Launch a Claude Code agent in a tmux pane.

    Delegates to :meth:`TmuxAgent.from_config` to create a tmux window,
    launch the Claude Code process, and return a live agent handle.
    """

    def launch(self, runtime: TaskRuntime) -> Agent:
        """Launch and return the primary agent for this task runtime.

        Args:
            runtime: Runtime envelope to launch against.  Must have
                ``state.worktree_path`` and ``state.signal_dir`` set
                (typically by a prior :class:`TaskPreparer` step).

        Returns:
            Agent: Live agent handle bound to this task.

        Raises:
            ValueError: If ``worktree_path`` or ``signal_dir`` are not set.
        """
        if runtime.state.worktree_path is None:
            raise ValueError("runtime.state.worktree_path must be set before launch")
        if runtime.state.signal_dir is None:
            raise ValueError("runtime.state.signal_dir must be set before launch")

        return TmuxAgent.from_config(
            config=runtime.task.primary_agent,
            task_id=runtime.task.id,
            worktree_path=runtime.state.worktree_path,
            signal_dir=runtime.state.signal_dir,
        )
