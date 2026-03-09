"""YAML and dict builders for :class:`agentrelay.task_graph.TaskGraph`.

This module defines :class:`TaskGraphBuilder`, which parses validated graph
specifications from YAML or Python mappings and constructs immutable runtime
graph objects.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

from agentrelay.environments import TmuxEnvironment
from agentrelay.task import (
    AgentConfig,
    AgentFramework,
    AgentRole,
    AgentVerbosity,
    ReviewConfig,
    Task,
    TaskPaths,
)
from agentrelay.task_graph.graph import TaskGraph
from agentrelay.workstream import WorkstreamSpec


@dataclass(frozen=True)
class _RawTaskSpec:
    """Parsed task spec data before task object construction.

    Attributes:
        id: Task identifier.
        role: Agent role for this task.
        description: Optional task description.
        paths: Task path configuration.
        dependency_ids: Upstream dependency task IDs.
        completion_gate: Optional completion gate command.
        max_gate_attempts: Optional task-specific gate attempts.
        primary_agent: Primary agent configuration.
        review: Optional review configuration.
        workstream_id: Workstream ID for this task.
    """

    id: str
    role: AgentRole
    description: Optional[str]
    paths: TaskPaths
    dependency_ids: tuple[str, ...]
    completion_gate: Optional[str]
    max_gate_attempts: Optional[int]
    primary_agent: AgentConfig
    review: Optional[ReviewConfig]
    workstream_id: str


class TaskGraphBuilder:
    """Builder for constructing :class:`TaskGraph` from validated input specs."""

    @classmethod
    def from_yaml(cls, path: Path) -> TaskGraph:
        """Parse YAML and build a validated :class:`TaskGraph`.

        Args:
            path: Path to a graph YAML file.

        Raises:
            ValueError: If YAML cannot be parsed or schema validation fails.

        Returns:
            TaskGraph: Validated immutable task graph.
        """
        try:
            raw = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML in {path}: {exc}") from exc
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | Any) -> TaskGraph:
        """Build a validated :class:`TaskGraph` from mapping data.

        Args:
            data: Parsed graph data mapping.

        Raises:
            ValueError: If the graph schema is invalid.

        Returns:
            TaskGraph: Validated immutable task graph.
        """
        graph = _require_mapping(data, "graph")
        _reject_unknown_keys(
            graph,
            "graph",
            {"name", "tasks", "workstreams", "max_workstream_depth"},
        )
        name = _require_non_empty_string(_read_required(graph, "name", "graph"), "name")
        workstreams = _parse_workstreams(
            graph.get("workstreams"),
            "graph.workstreams",
        )
        max_workstream_depth = _parse_optional_positive_int(
            graph.get("max_workstream_depth"),
            "graph.max_workstream_depth",
        )
        if max_workstream_depth is None:
            max_workstream_depth = 1

        task_items = _read_required(graph, "tasks", "graph")
        if not isinstance(task_items, list):
            raise _schema_error("tasks", "must be a list")
        if not task_items:
            raise _schema_error("tasks", "must contain at least one task")

        raw_specs: list[_RawTaskSpec] = []
        seen_ids: set[str] = set()
        for index, task_item in enumerate(task_items):
            path = f"tasks[{index}]"
            raw = _parse_task(task_item, path)
            if raw.id in seen_ids:
                raise _schema_error(path + ".id", f"duplicate task id '{raw.id}'")
            seen_ids.add(raw.id)
            raw_specs.append(raw)

        raw_by_id = {spec.id: spec for spec in raw_specs}
        _validate_dependencies_exist(raw_specs, raw_by_id)
        task_ids = _topological_task_ids(raw_specs)

        built_tasks: dict[str, Task] = {}
        for task_id in task_ids:
            spec = raw_by_id[task_id]
            deps = tuple(built_tasks[dep_id] for dep_id in spec.dependency_ids)
            built_tasks[task_id] = Task(
                id=spec.id,
                role=spec.role,
                description=spec.description,
                paths=spec.paths,
                dependencies=deps,
                completion_gate=spec.completion_gate,
                max_gate_attempts=spec.max_gate_attempts,
                primary_agent=spec.primary_agent,
                review=spec.review,
                workstream_id=spec.workstream_id,
            )

        return TaskGraph.from_tasks(
            (built_tasks[task_id] for task_id in task_ids),
            name=name,
            workstreams=workstreams,
            max_workstream_depth=max_workstream_depth,
        )


def _parse_task(task_data: Any, path: str) -> _RawTaskSpec:
    mapping = _require_mapping(task_data, path)
    _reject_unknown_keys(
        mapping,
        path,
        {
            "id",
            "role",
            "description",
            "dependencies",
            "paths",
            "completion_gate",
            "max_gate_attempts",
            "primary_agent",
            "review",
            "workstream_id",
        },
    )

    task_id = _require_non_empty_string(
        _read_required(mapping, "id", path), path + ".id"
    )
    role = _parse_role(mapping.get("role"), path + ".role")

    description_val = mapping.get("description")
    if description_val is not None and not isinstance(description_val, str):
        raise _schema_error(path + ".description", "must be a string or null")
    description = description_val

    dependencies = _parse_dependencies(
        mapping.get("dependencies", []), path + ".dependencies"
    )
    paths = _parse_paths(mapping.get("paths"), path + ".paths")
    completion_gate = _parse_optional_string(
        mapping.get("completion_gate"), path + ".completion_gate"
    )
    max_gate_attempts = _parse_optional_positive_int(
        mapping.get("max_gate_attempts"), path + ".max_gate_attempts"
    )
    primary_agent = _parse_agent_config(
        mapping.get("primary_agent"), path + ".primary_agent"
    )
    review = _parse_review_config(mapping.get("review"), path + ".review")
    workstream_id = _parse_optional_string(
        mapping.get("workstream_id"), path + ".workstream_id"
    )
    if workstream_id is None:
        workstream_id = "default"

    return _RawTaskSpec(
        id=task_id,
        role=role,
        description=description,
        paths=paths,
        dependency_ids=dependencies,
        completion_gate=completion_gate,
        max_gate_attempts=max_gate_attempts,
        primary_agent=primary_agent,
        review=review,
        workstream_id=workstream_id,
    )


def _parse_workstreams(
    value: Any,
    path: str,
) -> Optional[tuple[WorkstreamSpec, ...]]:
    if value is None:
        return None
    if not isinstance(value, list):
        raise _schema_error(path, "must be a list")
    if not value:
        raise _schema_error(path, "must contain at least one workstream")

    result: list[WorkstreamSpec] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        workstream = _parse_workstream(item, item_path)
        if workstream.id in seen_ids:
            raise _schema_error(
                item_path + ".id", f"duplicate workstream id '{workstream.id}'"
            )
        seen_ids.add(workstream.id)
        result.append(workstream)
    return tuple(result)


def _parse_workstream(value: Any, path: str) -> WorkstreamSpec:
    mapping = _require_mapping(value, path)
    _reject_unknown_keys(
        mapping,
        path,
        {"id", "parent_workstream_id", "base_branch", "merge_target_branch"},
    )

    workstream_id = _require_non_empty_string(
        _read_required(mapping, "id", path), path + ".id"
    )
    parent_workstream_id = _parse_optional_string(
        mapping.get("parent_workstream_id"),
        path + ".parent_workstream_id",
    )
    base_branch = _require_non_empty_string(
        mapping.get("base_branch", "main"),
        path + ".base_branch",
    )
    merge_target_branch = _require_non_empty_string(
        mapping.get("merge_target_branch", "main"),
        path + ".merge_target_branch",
    )
    return WorkstreamSpec(
        id=workstream_id,
        parent_workstream_id=parent_workstream_id,
        base_branch=base_branch,
        merge_target_branch=merge_target_branch,
    )


def _parse_role(value: Any, path: str) -> AgentRole:
    if value is None:
        return AgentRole.GENERIC
    if not isinstance(value, str):
        raise _schema_error(path, "must be a string")
    normalized = value.strip()
    for role in AgentRole:
        if normalized.lower() == role.value:
            return role
        if normalized.upper() == role.name:
            return role
    allowed = ", ".join(role.value for role in AgentRole)
    raise _schema_error(path, f"invalid role '{value}'. Allowed: {allowed}")


def _parse_dependencies(value: Any, path: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise _schema_error(path, "must be a list of task IDs")
    result: list[str] = []
    for idx, item in enumerate(value):
        item_path = f"{path}[{idx}]"
        dep_id = _require_non_empty_string(item, item_path)
        if dep_id in result:
            raise _schema_error(item_path, f"duplicate dependency id '{dep_id}'")
        result.append(dep_id)
    return tuple(result)


def _parse_paths(value: Any, path: str) -> TaskPaths:
    if value is None:
        return TaskPaths()
    mapping = _require_mapping(value, path)
    _reject_unknown_keys(mapping, path, {"src", "test", "spec"})

    src = _parse_path_list(mapping.get("src", []), path + ".src")
    test = _parse_path_list(mapping.get("test", []), path + ".test")
    spec = _parse_optional_string(mapping.get("spec"), path + ".spec")
    return TaskPaths(src=src, test=test, spec=spec)


def _parse_path_list(value: Any, path: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise _schema_error(path, "must be a list of strings")
    items: list[str] = []
    for idx, item in enumerate(value):
        item_path = f"{path}[{idx}]"
        items.append(_require_non_empty_string(item, item_path))
    return tuple(items)


def _parse_agent_config(value: Any, path: str) -> AgentConfig:
    if value is None:
        return AgentConfig()
    mapping = _require_mapping(value, path)
    _reject_unknown_keys(
        mapping,
        path,
        {"framework", "model", "adr_verbosity", "environment"},
    )

    framework = _parse_framework(mapping.get("framework"), path + ".framework")
    model = _parse_optional_string(mapping.get("model"), path + ".model")
    verbosity = _parse_verbosity(mapping.get("adr_verbosity"), path + ".adr_verbosity")
    environment = _parse_environment(mapping.get("environment"), path + ".environment")
    return AgentConfig(
        framework=framework,
        model=model,
        adr_verbosity=verbosity,
        environment=environment,
    )


def _parse_framework(value: Any, path: str) -> AgentFramework:
    if value is None:
        return AgentFramework.CLAUDE_CODE
    if not isinstance(value, str):
        raise _schema_error(path, "must be a string")
    normalized = value.strip()
    for framework in AgentFramework:
        if normalized.lower() == framework.value:
            return framework
        if normalized.upper() == framework.name:
            return framework
    allowed = ", ".join(framework.value for framework in AgentFramework)
    raise _schema_error(path, f"invalid framework '{value}'. Allowed: {allowed}")


def _parse_verbosity(value: Any, path: str) -> AgentVerbosity:
    if value is None:
        return AgentVerbosity.NONE
    if not isinstance(value, str):
        raise _schema_error(path, "must be a string")
    normalized = value.strip()
    for verbosity in AgentVerbosity:
        if normalized.lower() == verbosity.value:
            return verbosity
        if normalized.upper() == verbosity.name:
            return verbosity
    allowed = ", ".join(verbosity.value for verbosity in AgentVerbosity)
    raise _schema_error(path, f"invalid adr_verbosity '{value}'. Allowed: {allowed}")


def _parse_environment(value: Any, path: str) -> TmuxEnvironment:
    if value is None:
        return TmuxEnvironment()
    mapping = _require_mapping(value, path)
    _reject_unknown_keys(mapping, path, {"type", "session"})
    env_type = mapping.get("type")
    if env_type is not None:
        if not isinstance(env_type, str):
            raise _schema_error(path + ".type", "must be a string")
        if env_type.strip().lower() != "tmux":
            raise _schema_error(path + ".type", "must be 'tmux'")
    session = mapping.get("session", "agentrelay")
    session_str = _require_non_empty_string(session, path + ".session")
    return TmuxEnvironment(session=session_str)


def _parse_review_config(value: Any, path: str) -> Optional[ReviewConfig]:
    if value is None:
        return None
    mapping = _require_mapping(value, path)
    _reject_unknown_keys(mapping, path, {"agent", "review_on_attempt"})
    agent_data = _read_required(mapping, "agent", path)
    agent = _parse_agent_config(agent_data, path + ".agent")
    review_on_attempt = _parse_optional_positive_int(
        mapping.get("review_on_attempt", 1),
        path + ".review_on_attempt",
    )
    assert review_on_attempt is not None
    return ReviewConfig(agent=agent, review_on_attempt=review_on_attempt)


def _parse_optional_string(value: Any, path: str) -> Optional[str]:
    if value is None:
        return None
    return _require_non_empty_string(value, path)


def _parse_optional_positive_int(value: Any, path: str) -> Optional[int]:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise _schema_error(path, "must be an integer or null")
    if value <= 0:
        raise _schema_error(path, "must be greater than 0")
    return value


def _validate_dependencies_exist(
    specs: Sequence[_RawTaskSpec],
    specs_by_id: Mapping[str, _RawTaskSpec],
) -> None:
    for task_index, spec in enumerate(specs):
        for dep_index, dep_id in enumerate(spec.dependency_ids):
            if dep_id not in specs_by_id:
                raise _schema_error(
                    f"tasks[{task_index}].dependencies[{dep_index}]",
                    f"unknown dependency id '{dep_id}'",
                )


def _topological_task_ids(specs: Sequence[_RawTaskSpec]) -> tuple[str, ...]:
    in_degree = {spec.id: len(spec.dependency_ids) for spec in specs}
    dependents: dict[str, list[str]] = {spec.id: [] for spec in specs}
    for spec in specs:
        for dep_id in spec.dependency_ids:
            dependents[dep_id].append(spec.id)

    ordered_by_input = [spec.id for spec in specs]
    queue = [task_id for task_id in ordered_by_input if in_degree[task_id] == 0]
    result: list[str] = []

    while queue:
        task_id = queue.pop(0)
        result.append(task_id)
        for dep_id in dependents[task_id]:
            in_degree[dep_id] -= 1
            if in_degree[dep_id] == 0:
                queue.append(dep_id)

    if len(result) == len(specs):
        return tuple(result)

    cycle = _find_cycle({spec.id: spec.dependency_ids for spec in specs})
    if cycle:
        raise _schema_error(
            "tasks", f"contains a dependency cycle: {' -> '.join(cycle)}"
        )
    raise _schema_error("tasks", "contains one or more dependency cycles")


def _find_cycle(
    dependency_ids: Mapping[str, tuple[str, ...]],
) -> tuple[str, ...] | None:
    unvisited = 0
    visiting = 1
    done = 2

    state: dict[str, int] = {task_id: unvisited for task_id in dependency_ids}
    stack: list[str] = []
    stack_index: dict[str, int] = {}

    def dfs(task_id: str) -> tuple[str, ...] | None:
        state[task_id] = visiting
        stack_index[task_id] = len(stack)
        stack.append(task_id)

        for dep_id in dependency_ids[task_id]:
            dep_state = state[dep_id]
            if dep_state == unvisited:
                cycle = dfs(dep_id)
                if cycle is not None:
                    return cycle
            elif dep_state == visiting:
                start = stack_index[dep_id]
                return tuple(stack[start:] + [dep_id])

        stack.pop()
        del stack_index[task_id]
        state[task_id] = done
        return None

    for task_id in dependency_ids:
        if state[task_id] == unvisited:
            cycle = dfs(task_id)
            if cycle is not None:
                return cycle
    return None


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _schema_error(path, "must be a mapping/object")
    return value


def _read_required(mapping: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in mapping:
        raise _schema_error(path + "." + key, "is required")
    return mapping[key]


def _require_non_empty_string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise _schema_error(path, "must be a string")
    stripped = value.strip()
    if not stripped:
        raise _schema_error(path, "must be a non-empty string")
    return stripped


def _reject_unknown_keys(
    mapping: Mapping[str, Any],
    path: str,
    allowed: set[str],
) -> None:
    unknown = sorted(key for key in mapping if key not in allowed)
    if unknown:
        unknown_str = ", ".join(unknown)
        raise _schema_error(path, f"contains unknown key(s): {unknown_str}")


def _schema_error(path: str, message: str) -> ValueError:
    return ValueError(f"Invalid graph schema at '{path}': {message}")
