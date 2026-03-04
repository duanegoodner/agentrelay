from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class TaskStatus(Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    NEEDS_REVIEW = "needs_review"
    DONE = "done"
    FAILED = "failed"


class AgentRole(Enum):
    GENERIC = "generic"
    TEST_WRITER = "test_writer"
    TEST_REVIEWER = "test_reviewer"
    IMPLEMENTER = "implementer"
    SPEC_WRITER = "spec_writer"
    MERGER = "merger"


@dataclass(frozen=True)
class TaskPaths:
    src: tuple[str, ...] = field(default_factory=tuple)
    test: tuple[str, ...] = field(default_factory=tuple)
    spec: str | None = None


@dataclass
class TaskState:
    status: TaskStatus = TaskStatus.PENDING
    worktree_path: Path | None = None
    branch_name: str | None = None
    tmux_session: str | None = None
    pane_id: str | None = None
    pr_url: str | None = None
    result: Any = None
    error: str | None = None
    retries: int = 0
    agent_index: int | None = None


@dataclass(frozen=True)
class AgentTask:
    id: str
    description: str = ""
    dependencies: tuple[AgentTask, ...] = field(default_factory=tuple)
    role: AgentRole = AgentRole.GENERIC
    model: str | None = None
    completion_gate: str | None = None
    review_model: str | None = None
    review_on_attempt: int = 1
    max_gate_attempts: int | None = None
    task_params: dict[str, Any] = field(default_factory=dict)
    paths: TaskPaths = field(default_factory=TaskPaths)
    verbosity: str | None = None
    state: TaskState = field(default_factory=TaskState)

    @property
    def dependency_ids(self) -> tuple[str, ...]:
        return tuple(dep.id for dep in self.dependencies)
