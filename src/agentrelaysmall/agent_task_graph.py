from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agentrelaysmall.agent_task import AgentRole, AgentTask, TaskGroup, TaskStatus


@dataclass(frozen=True)
class TDDTaskGroup(TaskGroup):
    dependencies_single_task: tuple[AgentTask, ...] = field(default_factory=tuple)
    dependencies_task_group: tuple[TaskGroup, ...] = field(default_factory=tuple)

    @property
    def dependency_ids(self) -> tuple[str, ...]:
        return tuple(t.id for t in self.dependencies_single_task) + tuple(
            g.id for g in self.dependencies_task_group
        )


@dataclass
class AgentTaskGraph:
    name: str
    tasks: dict[str, AgentTask]
    target_repo_root: Path
    worktrees_root: Path
    tmux_session: str = "agentrelaysmall"
    keep_panes: bool = False
    model: str | None = None

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

        # Collect raw specs keyed by ID
        raw_plain: dict[str, Any] = {t["id"]: t for t in data.get("tasks", [])}
        raw_groups: dict[str, Any] = {g["id"]: g for g in data.get("tdd_groups", [])}
        group_ids: set[str] = set(raw_groups.keys())

        # Build dep graph for topo sort (nodes = plain task IDs + group IDs)
        all_node_ids = list(raw_plain.keys()) + list(raw_groups.keys())
        node_deps: dict[str, list[str]] = {
            nid: list(raw_plain[nid].get("dependencies", [])) for nid in raw_plain
        }
        for gid, g in raw_groups.items():
            node_deps[gid] = list(g.get("dependencies", []))

        sorted_nodes = _topo_sort(all_node_ids, node_deps)

        built_tasks: dict[str, AgentTask] = {}
        built_groups: dict[str, TDDTaskGroup] = {}

        for node_id in sorted_nodes:
            if node_id in raw_plain:
                raw = raw_plain[node_id]
                raw_dep_ids: list[str] = raw.get("dependencies", [])
                deps = tuple(built_tasks[d] for d in raw_dep_ids)
                built_tasks[node_id] = AgentTask(
                    id=node_id,
                    description=raw["description"],
                    dependencies=deps,
                    model=raw.get("model"),
                )
            else:
                raw = raw_groups[node_id]
                description: str = raw["description"]
                raw_dep_ids = raw.get("dependencies", [])

                plain_dep_ids = [d for d in raw_dep_ids if d not in group_ids]
                group_dep_ids = [d for d in raw_dep_ids if d in group_ids]

                task_deps = tuple(built_tasks[d] for d in plain_dep_ids)
                group_deps = tuple(built_groups[d] for d in group_dep_ids)

                # External deps for the _tests task: plain deps + each group's _impl
                resolved = task_deps + tuple(
                    built_tasks[f"{g.id}_impl"] for g in group_deps
                )

                built_groups[node_id] = TDDTaskGroup(
                    id=node_id,
                    description=description,
                    dependencies_single_task=task_deps,
                    dependencies_task_group=group_deps,
                )

                group_model: str | None = raw.get("model")
                role_models: dict[str, str] = raw.get("models", {})
                tests_model = role_models.get("tests") or group_model
                review_model = role_models.get("review") or group_model
                impl_model = role_models.get("impl") or group_model

                tests = AgentTask(
                    id=f"{node_id}_tests",
                    description=description,
                    dependencies=resolved,
                    role=AgentRole.TEST_WRITER,
                    tdd_group_id=node_id,
                    model=tests_model,
                )
                review = AgentTask(
                    id=f"{node_id}_review",
                    description=description,
                    dependencies=(tests,),
                    role=AgentRole.TEST_REVIEWER,
                    tdd_group_id=node_id,
                    model=review_model,
                )
                impl = AgentTask(
                    id=f"{node_id}_impl",
                    description=description,
                    dependencies=(review,),
                    role=AgentRole.IMPLEMENTER,
                    tdd_group_id=node_id,
                    model=impl_model,
                )
                built_tasks[f"{node_id}_tests"] = tests
                built_tasks[f"{node_id}_review"] = review
                built_tasks[f"{node_id}_impl"] = impl

        return AgentTaskGraph(
            name=name,
            tasks=built_tasks,
            target_repo_root=target_repo_root,
            worktrees_root=worktrees_root,
            tmux_session=tmux_session,
            keep_panes=keep_panes,
            model=graph_model,
        )
