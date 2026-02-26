from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from agentrelaysmall.agent_task import AgentTask, TaskStatus


@dataclass
class AgentTaskGraph:
    name: str
    tasks: dict[str, AgentTask]
    target_repo_root: Path
    worktrees_root: Path
    tmux_session: str = "agentrelaysmall"
    keep_panes: bool = False

    # ── Path authority — single source of truth ────────────────────────────

    def signal_dir(self, task_id: str) -> Path:
        return self.target_repo_root / ".workflow" / self.name / "signals" / task_id

    def worktree_path(self, task_id: str) -> Path:
        return self.worktrees_root / self.name / task_id

    def branch_name(self, task_id: str) -> str:
        return f"task/{self.name}/{task_id}"

    # ── State management ────────────────────────────────────────────────────

    def _refresh_ready(self) -> None:
        """Promote PENDING tasks to READY when all their dependencies are DONE."""
        for task in self.tasks.values():
            if task.state.status == TaskStatus.PENDING:
                if all(
                    self.tasks[dep_id].state.status == TaskStatus.DONE
                    for dep_id in task.dependencies
                ):
                    task.state.status = TaskStatus.READY

    def ready_tasks(self) -> list[AgentTask]:
        return [t for t in self.tasks.values() if t.state.status == TaskStatus.READY]

    def running_tasks(self) -> list[AgentTask]:
        return [t for t in self.tasks.values() if t.state.status == TaskStatus.RUNNING]

    def is_complete(self) -> bool:
        return all(
            t.state.status in (TaskStatus.DONE, TaskStatus.FAILED)
            for t in self.tasks.values()
        )

    def hydrate_from_signals(self) -> None:
        """Set task statuses from existing signal files (enables resume)."""
        for task_id, task in self.tasks.items():
            sig_dir = self.signal_dir(task_id)
            if (sig_dir / ".merged").exists():
                task.state.status = TaskStatus.DONE
            elif (sig_dir / ".failed").exists():
                task.state.status = TaskStatus.FAILED


class AgentTaskGraphBuilder:
    @classmethod
    def from_yaml(
        cls,
        path: Path,
        repo_root: Path,
        worktrees_root: Path,
    ) -> AgentTaskGraph:
        data: Any = yaml.safe_load(path.read_text())
        name: str = data["name"]
        # YAML may override the default target repo with an absolute path
        target_repo_root = (
            Path(data["target_repo"]) if "target_repo" in data else repo_root
        )
        tmux_session: str = data.get("tmux_session", "agentrelaysmall")
        keep_panes: bool = bool(data.get("keep_panes", False))
        tasks: dict[str, AgentTask] = {}
        for t in data["tasks"]:
            task_id: str = t["id"]
            tasks[task_id] = AgentTask(
                id=task_id,
                description=t["description"],
                dependencies=tuple(t.get("dependencies", [])),
            )
        return AgentTaskGraph(
            name=name,
            tasks=tasks,
            target_repo_root=target_repo_root,
            worktrees_root=worktrees_root,
            tmux_session=tmux_session,
            keep_panes=keep_panes,
        )
