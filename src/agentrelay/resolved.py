"""Frozen records for completed tasks and workstreams.

Written as ``resolved.json`` to the signal directory when a task or workstream
reaches terminal success.  Used for resumption validation — comparing the frozen
definition against the current graph to detect structural drift.

Classes:
    InputFromSpec: Serializable form of InputFrom for resolved records.
    TaggedPathSpec: Serializable form of TaggedPath for resolved records.
    ResolvedTask: Frozen execution record for a completed task.
    ResolvedWorkstream: Frozen execution record for a merged workstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from agentrelay.task_runtime import TaskRuntime
from agentrelay.workstream.core.runtime import WorkstreamRuntime

# ── Serializable helper types ──


@dataclass(frozen=True)
class InputFromSpec:
    """Serializable form of :class:`~agentrelay.task.InputFrom`.

    Uses plain strings instead of domain types for JSON portability.

    Attributes:
        task: Upstream task ID.
        category: Optional category filter.
    """

    task: str
    category: Optional[str] = None


@dataclass(frozen=True)
class TaggedPathSpec:
    """Serializable form of :class:`~agentrelay.task.TaggedPath`.

    Uses ``str`` for the path instead of :class:`~pathlib.Path` for JSON
    portability.

    Attributes:
        path: File path relative to the repository root.
        category: Semantic role of the file.
    """

    path: str
    category: str


# ── Frozen record types ──


@dataclass(frozen=True)
class ResolvedTask:
    """Frozen execution record for a completed task.

    Written to ``signal_dir/resolved.json`` when a task reaches
    ``PR_MERGED`` or ``COMPLETED``.  Captures the task definition as it
    was actually executed, plus the pre-merge SHA needed for rollback.

    Attributes:
        task_id: Task identifier.
        workstream_id: Workstream this task belongs to.
        dependencies: Upstream task IDs.
        inputs_from: Upstream output references.
        role: Agent role (``AgentRole.value`` string).
        model: Model identifier, or ``None`` for framework default.
        tagged_paths: Category-tagged file paths.
        branch_name: Task feature branch name.
        integration_branch: Workstream integration branch name.
        integration_branch_before_merge: SHA of the integration branch
            immediately before the task PR was merged.  ``None`` for
            ``COMPLETED`` tasks (no PR).
        completed_at_attempt: Zero-indexed attempt number at completion.
        pr_url: Merged task PR URL, or ``None`` for PR-less tasks.
    """

    task_id: str
    workstream_id: str
    dependencies: tuple[str, ...]
    inputs_from: tuple[InputFromSpec, ...]
    role: str
    model: Optional[str]
    tagged_paths: tuple[TaggedPathSpec, ...]
    branch_name: str
    integration_branch: str
    integration_branch_before_merge: Optional[str]
    completed_at_attempt: int
    pr_url: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "task_id": self.task_id,
            "workstream_id": self.workstream_id,
            "dependencies": list(self.dependencies),
            "inputs_from": [
                {"task": i.task, "category": i.category} for i in self.inputs_from
            ],
            "role": self.role,
            "model": self.model,
            "tagged_paths": [
                {"path": tp.path, "category": tp.category} for tp in self.tagged_paths
            ],
            "branch_name": self.branch_name,
            "integration_branch": self.integration_branch,
            "integration_branch_before_merge": self.integration_branch_before_merge,
            "completed_at_attempt": self.completed_at_attempt,
            "pr_url": self.pr_url,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ResolvedTask:
        """Deserialize from a JSON-safe dict."""
        return cls(
            task_id=d["task_id"],
            workstream_id=d["workstream_id"],
            dependencies=tuple(d["dependencies"]),
            inputs_from=tuple(
                InputFromSpec(task=i["task"], category=i.get("category"))
                for i in d["inputs_from"]
            ),
            role=d["role"],
            model=d.get("model"),
            tagged_paths=tuple(
                TaggedPathSpec(path=tp["path"], category=tp["category"])
                for tp in d["tagged_paths"]
            ),
            branch_name=d["branch_name"],
            integration_branch=d["integration_branch"],
            integration_branch_before_merge=d.get("integration_branch_before_merge"),
            completed_at_attempt=d["completed_at_attempt"],
            pr_url=d.get("pr_url"),
        )


@dataclass(frozen=True)
class ResolvedWorkstream:
    """Frozen execution record for a merged workstream.

    Written to ``signal_dir/resolved.json`` when a workstream reaches
    ``MERGED``.

    Attributes:
        workstream_id: Workstream identifier.
        integration_pr_url: Integration PR URL, or ``None`` if skipped.
        target_branch: Merge target branch (e.g., ``"main"``).
        target_branch_before_any_merge: SHA of the target branch before
            any merge related to this workstream.  Always populated,
            from whichever authority path detected the merge.
        merge_occurred: Whether an actual merge into the target branch
            occurred.  ``False`` for skipped workstreams (no commits
            ahead).
        merged_at: ISO timestamp of the merge detection, or ``None`` if
            ``merge_occurred`` is ``False``.
    """

    workstream_id: str
    integration_pr_url: Optional[str]
    target_branch: str
    target_branch_before_any_merge: str
    merge_occurred: bool
    merged_at: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "workstream_id": self.workstream_id,
            "integration_pr_url": self.integration_pr_url,
            "target_branch": self.target_branch,
            "target_branch_before_any_merge": self.target_branch_before_any_merge,
            "merge_occurred": self.merge_occurred,
            "merged_at": self.merged_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ResolvedWorkstream:
        """Deserialize from a JSON-safe dict."""
        return cls(
            workstream_id=d["workstream_id"],
            integration_pr_url=d.get("integration_pr_url"),
            target_branch=d["target_branch"],
            target_branch_before_any_merge=d["target_branch_before_any_merge"],
            merge_occurred=d["merge_occurred"],
            merged_at=d.get("merged_at"),
        )


# ── Builder functions ──


def build_resolved_task(
    runtime: TaskRuntime,
    integration_branch_before_merge: Optional[str],
) -> ResolvedTask:
    """Build a :class:`ResolvedTask` from runtime state at terminal success.

    Args:
        runtime: Task runtime at ``PR_MERGED`` or ``COMPLETED`` status.
        integration_branch_before_merge: Pre-merge SHA of the integration
            branch, or ``None`` for PR-less tasks.

    Returns:
        ResolvedTask: Frozen execution record.
    """
    task = runtime.task
    return ResolvedTask(
        task_id=task.id,
        workstream_id=task.workstream_id,
        dependencies=task.dependencies,
        inputs_from=tuple(
            InputFromSpec(task=inp.task, category=inp.category)
            for inp in task.inputs_from
        ),
        role=task.role.value,
        model=task.primary_agent.model,
        tagged_paths=tuple(
            TaggedPathSpec(path=str(tp.path), category=tp.category)
            for tp in task.tagged_paths
        ),
        branch_name=runtime.state.branch_name or "",
        integration_branch=runtime.state.integration_branch or "",
        integration_branch_before_merge=integration_branch_before_merge,
        completed_at_attempt=runtime.state.attempt_num,
        pr_url=runtime.artifacts.pr_url,
    )


def build_resolved_workstream(ws_runtime: WorkstreamRuntime) -> ResolvedWorkstream:
    """Build a :class:`ResolvedWorkstream` from runtime state at ``MERGED``.

    Reads ``target_branch_before_any_merge`` from the runtime's artifacts,
    where it was deposited by the merger, checker, or integrator.

    Args:
        ws_runtime: Workstream runtime at ``MERGED`` status.

    Returns:
        ResolvedWorkstream: Frozen execution record.
    """
    merge_pr_url = ws_runtime.artifacts.merge_pr_url
    merge_occurred = merge_pr_url is not None
    return ResolvedWorkstream(
        workstream_id=ws_runtime.spec.id,
        integration_pr_url=merge_pr_url,
        target_branch=ws_runtime.spec.merge_target_branch,
        target_branch_before_any_merge=(
            ws_runtime.artifacts.target_branch_before_any_merge or ""
        ),
        merge_occurred=merge_occurred,
        merged_at=(datetime.now(timezone.utc).isoformat() if merge_occurred else None),
    )


__all__ = [
    "InputFromSpec",
    "ResolvedTask",
    "ResolvedWorkstream",
    "TaggedPathSpec",
    "build_resolved_task",
    "build_resolved_workstream",
]
