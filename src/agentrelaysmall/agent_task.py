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


@dataclass(frozen=True)
class AgentTask:
    id: str
    description: str
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    role: AgentRole = AgentRole.GENERIC
    tdd_group_id: str | None = None
    state: TaskState = field(default_factory=TaskState)
