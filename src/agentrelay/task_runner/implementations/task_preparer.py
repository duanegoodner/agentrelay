"""Implementations of :class:`~agentrelay.task_runner.core.io.TaskPreparer`.

Classes:
    WorktreeTaskPreparer: Creates a task branch in a shared workstream worktree
    and writes protocol files.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agentrelay.agent_comm_protocol.manifest import (
    InputFileInfo,
    build_manifest,
    manifest_to_dict,
)
from agentrelay.agent_comm_protocol.policies import build_policies, policies_to_dict
from agentrelay.agent_comm_protocol.templates import resolve_instructions
from agentrelay.agent_sdk.output_manifest import (
    OUTPUT_MANIFEST_FILENAME,
    output_manifest_from_dict,
)
from agentrelay.errors import _WorkspaceIntegrationError
from agentrelay.ops import git, signals
from agentrelay.task import Task
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

    run_dir: Path
    graph_name: str
    dependency_descriptions: dict[str, Optional[str]] = field(default_factory=dict)
    context_content: Optional[str] = None
    tools: tuple[str, ...] = ()

    def prepare(self, runtime: TaskRuntime) -> None:
        """Prepare runtime execution prerequisites.

        Creates a task branch in the workstream worktree, checks it out,
        and writes protocol files to the signal directory.

        Reads ``integration_branch`` and ``workstream_worktree_path`` from
        ``runtime.state`` (set by the orchestrator before dispatch).

        Args:
            runtime: Runtime envelope to prepare (e.g. branch, signal files).

        Raises:
            ValueError: If ``runtime.state.integration_branch`` or
                ``runtime.state.workstream_worktree_path`` is None.
        """
        integration_branch = runtime.state.integration_branch
        workstream_worktree_path = runtime.state.workstream_worktree_path
        if integration_branch is None:
            raise ValueError(
                "runtime.state.integration_branch must be set before prepare()"
            )
        if workstream_worktree_path is None:
            raise ValueError(
                "runtime.state.workstream_worktree_path must be set before prepare()"
            )

        task = runtime.task
        branch_name = f"agentrelay/{self.graph_name}/{task.id}"
        signal_dir = self.run_dir / "signals" / task.id

        try:
            if git.current_branch(workstream_worktree_path) == branch_name:
                # Retry: branch already checked out from a prior attempt.
                # Keep the agent's prior commits so they can fix their code.
                pass
            else:
                git.branch_create(
                    workstream_worktree_path,
                    branch_name,
                    integration_branch,
                    force=True,
                )
                git.checkout(workstream_worktree_path, branch_name)
        except subprocess.CalledProcessError as exc:
            raise _WorkspaceIntegrationError(
                f"Failed to create branch for task {task.id!r}: {exc}",
            ) from exc

        signals.ensure_signal_dir(signal_dir)

        input_files = _resolve_input_files(task, self.run_dir)

        manifest = build_manifest(
            task=task,
            branch_name=branch_name,
            integration_branch=integration_branch,
            graph_name=self.graph_name,
            attempt_num=runtime.state.attempt_num,
            dependency_descriptions=self.dependency_descriptions,
            tools=self.tools,
            input_files=input_files,
        )
        signals.write_json(signal_dir, "manifest.json", manifest_to_dict(manifest))

        policies = build_policies(task, integration_branch)
        signals.write_json(signal_dir, "policies.json", policies_to_dict(policies))

        isolation = task.primary_agent.isolation
        instructions = resolve_instructions(
            task.role,
            manifest,
            adr_verbosity=task.primary_agent.adr_verbosity,
            sandbox_type=isolation.sandbox_type if isolation is not None else None,
            worktree_path=workstream_worktree_path,
            graph_yaml_path=self.run_dir / "graph.yaml",
            signals_base_path=self.run_dir / "signals",
        )
        signals.write_text(signal_dir, "instructions.md", instructions)

        if self.context_content is not None:
            signals.write_text(signal_dir, "context.md", self.context_content)

        runtime.state.worktree_path = workstream_worktree_path
        runtime.state.branch_name = branch_name
        runtime.state.signal_dir = signal_dir


def _resolve_input_files(
    task: Task,
    run_dir: Path,
) -> tuple[InputFileInfo, ...]:
    """Resolve ``inputs_from`` references to concrete input file entries.

    Reads each referenced upstream task's ``outputs.json`` from its signal
    directory, optionally filters by category, and returns resolved entries.

    Args:
        task: The task being prepared (provides ``inputs_from``).
        run_dir: Path to the per-run directory.

    Returns:
        Tuple of resolved input file entries.

    Raises:
        FileNotFoundError: If an upstream task's ``outputs.json`` is missing.
    """
    if not task.inputs_from:
        return ()

    result: list[InputFileInfo] = []
    for inp in task.inputs_from:
        upstream_signal_dir = run_dir / "signals" / inp.task
        raw = signals.read_signal_file(upstream_signal_dir, OUTPUT_MANIFEST_FILENAME)
        if raw is None:
            raise FileNotFoundError(
                f"Cannot resolve inputs_from for task '{task.id}': "
                f"upstream task '{inp.task}' has no {OUTPUT_MANIFEST_FILENAME} "
                f"at {upstream_signal_dir / OUTPUT_MANIFEST_FILENAME}"
            )
        output_manifest = output_manifest_from_dict(json.loads(raw))
        for entry in output_manifest.files:
            if inp.category is None or entry.category == inp.category:
                result.append(
                    InputFileInfo(
                        path=entry.path,
                        category=entry.category,
                        source_task=inp.task,
                    )
                )
    return tuple(result)
