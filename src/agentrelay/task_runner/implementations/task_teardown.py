"""Implementations of :class:`~agentrelay.task_runner.core.io.TaskTeardown`.

Classes:
    WorktreeTaskTeardown: Delegates agent cleanup and deletes the task branch.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from agentrelay.ops import git
from agentrelay.task_runtime import TaskRuntime


@dataclass
class WorktreeTaskTeardown:
    """Delegate agent-address cleanup and delete the task branch.

    Performs best-effort cleanup: delegates log capture and environment
    teardown to the agent address, then deletes the task branch.
    The workstream worktree is owned by the workstream teardown handler
    and is not touched here. Errors during teardown are caught and not
    propagated.
    """

    repo_path: Path
    keep_panes: bool = False

    def teardown(self, runtime: TaskRuntime) -> None:
        """Release runtime resources after terminal completion.

        Args:
            runtime: Runtime envelope whose resources should be cleaned up.
        """
        agent_address = runtime.artifacts.agent_address

        if agent_address is not None:
            agent_address.teardown(
                signal_dir=runtime.state.signal_dir,
                keep_panes=self.keep_panes,
            )

        sandbox = runtime.artifacts.sandbox
        if sandbox is not None and runtime.artifacts.sandbox_context is not None:
            try:
                sandbox.teardown(runtime.artifacts.sandbox_context)
            except Exception:
                pass  # Best-effort: container may already be gone

        if runtime.state.branch_name is not None:
            try:
                git.branch_delete(self.repo_path, runtime.state.branch_name)
            except subprocess.CalledProcessError:
                pass  # Best-effort: branch may have been deleted by GitHub
