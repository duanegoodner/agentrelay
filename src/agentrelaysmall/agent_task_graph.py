from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agentrelaysmall.agent_task import AgentRole, AgentTask, TaskPaths, TaskStatus


@dataclass
class AgentTaskGraph:
    name: str
    tasks: dict[str, AgentTask]
    target_repo_root: Path
    worktrees_root: Path
    tmux_session: str = "agentrelaysmall"
    keep_panes: bool = False
    model: str | None = None
    max_gate_attempts: int | None = None
    verbosity: str = "standard"
    _agent_counter: int = field(default=0, init=False, repr=False, compare=False)

    def next_agent_index(self) -> int:
        """Return a monotonically increasing index for each agent launched this run."""
        idx = self._agent_counter
        self._agent_counter += 1
        return idx

    # ── Path authority — single source of truth ────────────────────────────

    def signal_dir(self, task_id: str) -> Path:
        return self.target_repo_root / ".workflow" / self.name / "signals" / task_id

    def worktree_path(self, task_id: str) -> Path:
        return self.worktrees_root / self.name / task_id

    def branch_name(self, task_id: str) -> str:
        return f"task/{self.name}/{task_id}"

    def graph_branch(self) -> str:
        return f"graph/{self.name}"

    # ── State management ────────────────────────────────────────────────────

    def _refresh_ready(self) -> None:
        """Promote PENDING tasks to READY when all their dependencies are DONE."""
        for task in self.tasks.values():
            if task.state.status == TaskStatus.PENDING:
                if all(
                    dep.state.status == TaskStatus.DONE for dep in task.dependencies
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


def _topo_sort(node_ids: list[str], deps: dict[str, list[str]]) -> list[str]:
    """Return node_ids in dependency-first topological order (Kahn's algorithm)."""
    in_degree = {n: 0 for n in node_ids}
    dependents: dict[str, list[str]] = {n: [] for n in node_ids}
    for node, node_deps in deps.items():
        for dep in node_deps:
            in_degree[node] += 1
            dependents[dep].append(node)
    queue = [n for n in node_ids if in_degree[n] == 0]
    result: list[str] = []
    while queue:
        n = queue.pop(0)
        result.append(n)
        for dependent in dependents[n]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)
    return result


class AgentTaskGraphBuilder:
    @classmethod
    def from_yaml(
        cls,
        path: Path,
        repo_root: Path,
    ) -> AgentTaskGraph:
        data: Any = yaml.safe_load(path.read_text())
        name: str = data["name"]
        target_repo_root = (
            Path(data["target_repo"]) if "target_repo" in data else repo_root
        )
        worktrees_root = (
            Path(data["worktrees_root"])
            if "worktrees_root" in data
            else target_repo_root.parent / "worktrees"
        )
        tmux_session: str = data.get("tmux_session", "agentrelaysmall")
        keep_panes: bool = bool(data.get("keep_panes", False))
        graph_model: str | None = data.get("model")
        graph_max_gate_attempts: int | None = data.get("max_gate_attempts")
        graph_verbosity: str = data.get("verbosity", "standard")

        # Collect raw task specs keyed by ID
        raw_tasks: dict[str, Any] = {t["id"]: t for t in data.get("tasks", [])}

        # Build dep graph for topo sort
        node_deps: dict[str, list[str]] = {
            nid: list(raw_tasks[nid].get("dependencies", [])) for nid in raw_tasks
        }
        sorted_nodes = _topo_sort(list(raw_tasks.keys()), node_deps)

        built_tasks: dict[str, AgentTask] = {}
        for node_id in sorted_nodes:
            raw = raw_tasks[node_id]
            raw_dep_ids: list[str] = raw.get("dependencies", [])
            deps = tuple(built_tasks[d] for d in raw_dep_ids)
            role_str: str = raw.get("role", "GENERIC").upper()
            built_tasks[node_id] = AgentTask(
                id=node_id,
                description=raw.get("description", ""),
                dependencies=deps,
                role=AgentRole[role_str],
                model=raw.get("model"),
                completion_gate=raw.get("completion_gate"),
                review_model=raw.get("review_model"),
                review_on_attempt=raw.get("review_on_attempt", 1),
                max_gate_attempts=raw.get("max_gate_attempts"),
                task_params=raw.get("task_params", {}),
                paths=TaskPaths(
                    src=tuple((raw.get("paths") or {}).get("src", [])),
                    test=tuple((raw.get("paths") or {}).get("test", [])),
                    spec=(raw.get("paths") or {}).get("spec"),
                ),
                verbosity=raw.get("verbosity"),
            )

        return AgentTaskGraph(
            name=name,
            tasks=built_tasks,
            target_repo_root=target_repo_root,
            worktrees_root=worktrees_root,
            tmux_session=tmux_session,
            keep_panes=keep_panes,
            model=graph_model,
            max_gate_attempts=graph_max_gate_attempts,
            verbosity=graph_verbosity,
        )
