"""Implementations of :class:`~agentrelay.task_runner.core.io.TaskPreparer`.

Classes:
    WorktreeTaskPreparer: Creates a task branch in a shared workstream worktree
    and writes protocol files.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agentrelay.agent_comm_protocol.manifest import build_manifest, manifest_to_dict
from agentrelay.agent_comm_protocol.policies import build_policies, policies_to_dict
from agentrelay.agent_comm_protocol.templates import resolve_instructions
from agentrelay.errors import WorkspaceIntegrationError
from agentrelay.ops import git, signals
from agentrelay.task_runtime import TaskRuntime


@dataclass
class WorktreeTaskPreparer:
    """Create a task branch in a shared workstream worktree and write protocol files.

    Creates a task-specific branch off the integration branch, checks it out
    in the workstream worktree, writes ``manifest.json``, ``policies.json``,
    and ``instructions.md`` into the signal directory, and updates the runtime
    state with computed paths.

    The worktree itself is owned by the workstream preparer — this class only
    creates and checks out branches within it.
    """

    repo_path: Path
    graph_name: str
    integration_branch: str
    workstream_worktree_path: Path
    dependency_descriptions: dict[str, Optional[str]] = field(default_factory=dict)
    context_content: Optional[str] = None

    def prepare(self, runtime: TaskRuntime) -> None:
        """Prepare runtime execution prerequisites.

        Creates a task branch in the workstream worktree, checks it out,
        and writes protocol files to the signal directory.

        Args:
            runtime: Runtime envelope to prepare (e.g. branch, signal files).
        """
        task = runtime.task
        branch_name = f"agentrelay/{self.graph_name}/{task.id}"
        signal_dir = self.repo_path / f".workflow/{self.graph_name}/signals/{task.id}"

        try:
            git.branch_create(
                self.workstream_worktree_path,
                branch_name,
                self.integration_branch,
            )
            git.checkout(self.workstream_worktree_path, branch_name)
        except subprocess.CalledProcessError as exc:
            raise WorkspaceIntegrationError(
                f"Failed to create branch for task {task.id!r}: {exc}",
            ) from exc

        signals.ensure_signal_dir(signal_dir)

        manifest = build_manifest(
            task=task,
            branch_name=branch_name,
            integration_branch=self.integration_branch,
            graph_name=self.graph_name,
            attempt_num=runtime.state.attempt_num,
            dependency_descriptions=self.dependency_descriptions,
        )
        signals.write_json(signal_dir, "manifest.json", manifest_to_dict(manifest))

        policies = build_policies(task, self.integration_branch)
        signals.write_json(signal_dir, "policies.json", policies_to_dict(policies))

        instructions = resolve_instructions(task.role, manifest)
        signals.write_text(signal_dir, "instructions.md", instructions)

        if self.context_content is not None:
            signals.write_text(signal_dir, "context.md", self.context_content)

        runtime.state.worktree_path = self.workstream_worktree_path
        runtime.state.branch_name = branch_name
        runtime.state.signal_dir = signal_dir
