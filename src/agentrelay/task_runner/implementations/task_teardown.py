"""Implementations of :class:`~agentrelay.task_runner.core.io.TaskTeardown`.

Classes:
    WorktreeTaskTeardown: Captures agent logs and cleans up task branch.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from agentrelay.agent.implementations.tmux_address import TmuxAddress
from agentrelay.ops import git, signals, tmux
from agentrelay.task_runtime import TaskRuntime


@dataclass
class WorktreeTaskTeardown:
    """Capture agent logs, kill tmux windows, and delete the task branch.

    Performs best-effort cleanup: captures pane scrollback, optionally kills
    the tmux window, and deletes the task branch. The workstream worktree is
    owned by the workstream teardown handler and is not touched here.
    Errors during teardown are caught and not propagated.
    """

    repo_path: Path
    keep_panes: bool = False

    def teardown(self, runtime: TaskRuntime) -> None:
        """Release runtime resources after terminal completion.

        Args:
            runtime: Runtime envelope whose resources should be cleaned up.
        """
        agent_address = runtime.artifacts.agent_address

        if isinstance(agent_address, TmuxAddress):
            pane_id = agent_address.pane_id
            try:
                log = tmux.capture_pane(pane_id, full_history=True)
                if runtime.state.signal_dir is not None:
                    signals.write_text(runtime.state.signal_dir, "agent.log", log)
            except subprocess.CalledProcessError:
                pass  # Best-effort: pane may already be gone

            if not self.keep_panes:
                try:
                    tmux.kill_window(pane_id)
                except subprocess.CalledProcessError:
                    pass  # Best-effort

        if runtime.state.branch_name is not None:
            try:
                git.branch_delete(self.repo_path, runtime.state.branch_name)
            except subprocess.CalledProcessError:
                pass  # Best-effort: branch may have been deleted by GitHub
