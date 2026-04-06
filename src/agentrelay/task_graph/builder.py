"""YAML and dict builders for :class:`agentrelay.task_graph.TaskGraph`.

This module defines :class:`TaskGraphBuilder`, which parses validated graph
specifications from YAML or Python mappings and constructs immutable runtime
graph objects.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

from agentrelay.environments import TmuxEnvironment
from agentrelay.sandbox import ContainerRuntime, IsolationConfig, SandboxType, TokenTier
from agentrelay.task import (
    AdrVerbosity,
    AgentConfig,
    AgentFramework,
    AgentRole,
    InputFrom,
    ReviewConfig,
    Task,
    TaskPaths,
)
from agentrelay.task_graph.graph import TaskGraph
from agentrelay.workstream import WorkstreamSpec


@dataclass(frozen=True)
class _RawIsolationConfig:
    """Parsed isolation config with all-Optional fields (None = inherit).

    Used only during parsing to represent partial isolation configuration
    at each level of the inheritance chain. Resolved to a fully-populated
    :class:`IsolationConfig` after four-level merge.
    """

    sandbox_type: Optional[SandboxType] = None
    token_tier: Optional[TokenTier] = None
    image: Optional[str] = None
    runtime: Optional[ContainerRuntime] = None


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
        isolation_raw: Task-level raw isolation config.
        primary_agent_isolation_raw: Primary agent raw isolation config.
        review_agent_isolation_raw: Review agent raw isolation config.
    """

    id: str
    role: AgentRole
    description: Optional[str]
    paths: TaskPaths
    dependency_ids: tuple[str, ...]
    inputs_from: tuple[InputFrom, ...]
    completion_gate: Optional[str]
    max_gate_attempts: Optional[int]
    primary_agent: AgentConfig
    review: Optional[ReviewConfig]
    workstream_id: str
    isolation_raw: Optional[_RawIsolationConfig] = None
    primary_agent_isolation_raw: Optional[_RawIsolationConfig] = None
    review_agent_isolation_raw: Optional[_RawIsolationConfig] = None


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
            {"name", "tasks", "workstreams", "max_workstream_depth", "isolation"},
        )
        name = _require_non_empty_string(_read_required(graph, "name", "graph"), "name")

        graph_raw_iso = _parse_raw_isolation(graph.get("isolation"), "graph.isolation")

        workstreams, ws_raw_iso = _parse_workstreams(
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
        _validate_inputs_from_are_dependencies(raw_specs, raw_by_id)
        task_ids = _topological_task_ids(raw_specs)

        # --- Resolve isolation: four-level inheritance ---

        # Resolve workstream isolation (graph → workstream)
        if workstreams:
            resolved_ws_list: list[WorkstreamSpec] = []
            for ws in workstreams:
                merged = _merge_raw_isolation(graph_raw_iso, ws_raw_iso.get(ws.id))
                ws_iso = _resolve_isolation(merged)
                resolved_ws_list.append(dataclasses.replace(ws, isolation=ws_iso))
            workstreams = tuple(resolved_ws_list)

        # Build tasks with resolved isolation
        built_tasks: dict[str, Task] = {}
        for task_id in task_ids:
            spec = raw_by_id[task_id]

            # Chain: graph → workstream → task
            ws_raw = ws_raw_iso.get(spec.workstream_id)
            task_chain = _merge_raw_isolation(
                _merge_raw_isolation(graph_raw_iso, ws_raw),
                spec.isolation_raw,
            )
            task_iso = _resolve_isolation(task_chain)

            # Primary agent: task chain → agent override
            primary_chain = _merge_raw_isolation(
                task_chain, spec.primary_agent_isolation_raw
            )
            primary_iso = _resolve_isolation(primary_chain)
            primary_agent = dataclasses.replace(
                spec.primary_agent, isolation=primary_iso
            )

            # Review agent: task chain → review agent override
            review = spec.review
            if review is not None:
                review_chain = _merge_raw_isolation(
                    task_chain, spec.review_agent_isolation_raw
                )
                review_iso = _resolve_isolation(review_chain)
                review_agent = dataclasses.replace(review.agent, isolation=review_iso)
                review = dataclasses.replace(review, agent=review_agent)

            built_tasks[task_id] = Task(
                id=spec.id,
                role=spec.role,
                description=spec.description,
                paths=spec.paths,
                dependencies=spec.dependency_ids,
                inputs_from=spec.inputs_from,
                completion_gate=spec.completion_gate,
                max_gate_attempts=spec.max_gate_attempts,
                primary_agent=primary_agent,
                review=review,
                workstream_id=spec.workstream_id,
                isolation=task_iso,
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
            "isolation",
            "inputs_from",
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
    inputs_from = _parse_inputs_from(mapping.get("inputs_from"), path + ".inputs_from")
    paths = _parse_paths(mapping.get("paths"), path + ".paths")
    completion_gate = _parse_optional_string(
        mapping.get("completion_gate"), path + ".completion_gate"
    )
    max_gate_attempts = _parse_optional_positive_int(
        mapping.get("max_gate_attempts"), path + ".max_gate_attempts"
    )
    primary_agent, primary_iso_raw = _parse_agent_config(
        mapping.get("primary_agent"), path + ".primary_agent"
    )
    review, review_iso_raw = _parse_review_config(
        mapping.get("review"), path + ".review"
    )
    workstream_id = _parse_optional_string(
        mapping.get("workstream_id"), path + ".workstream_id"
    )
    if workstream_id is None:
        workstream_id = "default"

    isolation_raw = _parse_raw_isolation(mapping.get("isolation"), path + ".isolation")

    return _RawTaskSpec(
        id=task_id,
        role=role,
        description=description,
        paths=paths,
        dependency_ids=dependencies,
        inputs_from=inputs_from,
        completion_gate=completion_gate,
        max_gate_attempts=max_gate_attempts,
        primary_agent=primary_agent,
        review=review,
        workstream_id=workstream_id,
        isolation_raw=isolation_raw,
        primary_agent_isolation_raw=primary_iso_raw,
        review_agent_isolation_raw=review_iso_raw,
    )


def _parse_workstreams(
    value: Any,
    path: str,
) -> tuple[
    Optional[tuple[WorkstreamSpec, ...]], dict[str, Optional[_RawIsolationConfig]]
]:
    if value is None:
        return None, {}
    if not isinstance(value, list):
        raise _schema_error(path, "must be a list")
    if not value:
        raise _schema_error(path, "must contain at least one workstream")

    result: list[WorkstreamSpec] = []
    ws_raw_iso: dict[str, Optional[_RawIsolationConfig]] = {}
    seen_ids: set[str] = set()
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        workstream, iso_raw = _parse_workstream(item, item_path)
        if workstream.id in seen_ids:
            raise _schema_error(
                item_path + ".id", f"duplicate workstream id '{workstream.id}'"
            )
        seen_ids.add(workstream.id)
        result.append(workstream)
        ws_raw_iso[workstream.id] = iso_raw
    return tuple(result), ws_raw_iso


def _parse_workstream(
    value: Any, path: str
) -> tuple[WorkstreamSpec, Optional[_RawIsolationConfig]]:
    mapping = _require_mapping(value, path)
    _reject_unknown_keys(
        mapping,
        path,
        {
            "id",
            "parent_workstream_id",
            "base_branch",
            "merge_target_branch",
            "auto_merge",
            "isolation",
        },
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
    raw_auto_merge = mapping.get("auto_merge", False)
    if not isinstance(raw_auto_merge, bool):
        raise _schema_error(path + ".auto_merge", "must be a boolean")

    iso_raw = _parse_raw_isolation(mapping.get("isolation"), path + ".isolation")

    ws = WorkstreamSpec(
        id=workstream_id,
        parent_workstream_id=parent_workstream_id,
        base_branch=base_branch,
        merge_target_branch=merge_target_branch,
        auto_merge=raw_auto_merge,
    )
    return ws, iso_raw


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


def _parse_inputs_from(value: Any, path: str) -> tuple[InputFrom, ...]:
    """Parse ``inputs_from``: a single mapping or list of mappings."""
    if value is None:
        return ()
    if isinstance(value, Mapping):
        value = [value]
    if not isinstance(value, list):
        raise _schema_error(path, "must be a mapping or list of mappings")
    result: list[InputFrom] = []
    for idx, item in enumerate(value):
        item_path = f"{path}[{idx}]"
        mapping = _require_mapping(item, item_path)
        _reject_unknown_keys(mapping, item_path, {"task", "category"})
        task_id = _require_non_empty_string(
            _read_required(mapping, "task", item_path), item_path + ".task"
        )
        category = _parse_optional_string(
            mapping.get("category"), item_path + ".category"
        )
        result.append(InputFrom(task=task_id, category=category))
    return tuple(result)


def _parse_paths(value: Any, path: str) -> TaskPaths:
    if value is None:
        return TaskPaths()
    mapping = _require_mapping(value, path)
    _reject_unknown_keys(mapping, path, {"src", "test", "spec"})

    src = _parse_path_list(mapping.get("src", []), path + ".src")
    test = _parse_path_list(mapping.get("test", []), path + ".test")
    spec_str = _parse_optional_string(mapping.get("spec"), path + ".spec")
    spec = Path(spec_str) if spec_str is not None else None
    return TaskPaths(src=src, test=test, spec=spec)


def _parse_path_list(value: Any, path: str) -> tuple[Path, ...]:
    if not isinstance(value, list):
        raise _schema_error(path, "must be a list of strings")
    items: list[Path] = []
    for idx, item in enumerate(value):
        item_path = f"{path}[{idx}]"
        items.append(Path(_require_non_empty_string(item, item_path)))
    return tuple(items)


def _parse_agent_config(
    value: Any, path: str
) -> tuple[AgentConfig, Optional[_RawIsolationConfig]]:
    if value is None:
        return AgentConfig(), None
    mapping = _require_mapping(value, path)
    _reject_unknown_keys(
        mapping,
        path,
        {"framework", "model", "adr_verbosity", "environment", "isolation"},
    )

    framework = _parse_framework(mapping.get("framework"), path + ".framework")
    model = _parse_optional_string(mapping.get("model"), path + ".model")
    verbosity = _parse_verbosity(mapping.get("adr_verbosity"), path + ".adr_verbosity")
    environment = _parse_environment(mapping.get("environment"), path + ".environment")
    iso_raw = _parse_raw_isolation(mapping.get("isolation"), path + ".isolation")
    return (
        AgentConfig(
            framework=framework,
            model=model,
            adr_verbosity=verbosity,
            environment=environment,
        ),
        iso_raw,
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


def _parse_verbosity(value: Any, path: str) -> AdrVerbosity:
    if value is None:
        return AdrVerbosity.NONE
    if not isinstance(value, str):
        raise _schema_error(path, "must be a string")
    normalized = value.strip()
    for verbosity in AdrVerbosity:
        if normalized.lower() == verbosity.value:
            return verbosity
        if normalized.upper() == verbosity.name:
            return verbosity
    allowed = ", ".join(verbosity.value for verbosity in AdrVerbosity)
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
    session = mapping.get("session")
    if session is not None:
        session_str = _require_non_empty_string(session, path + ".session")
        return TmuxEnvironment(session=session_str)
    return TmuxEnvironment()


def _parse_review_config(
    value: Any, path: str
) -> tuple[Optional[ReviewConfig], Optional[_RawIsolationConfig]]:
    if value is None:
        return None, None
    mapping = _require_mapping(value, path)
    _reject_unknown_keys(mapping, path, {"agent", "review_on_attempt"})
    agent_data = _read_required(mapping, "agent", path)
    agent, review_iso_raw = _parse_agent_config(agent_data, path + ".agent")
    review_on_attempt = _parse_optional_positive_int(
        mapping.get("review_on_attempt", 1),
        path + ".review_on_attempt",
    )
    assert review_on_attempt is not None
    return (
        ReviewConfig(agent=agent, review_on_attempt=review_on_attempt),
        review_iso_raw,
    )


# ── Isolation parsing and resolution ──


def _parse_raw_isolation(value: Any, path: str) -> Optional[_RawIsolationConfig]:
    """Parse a raw isolation config mapping. Returns None if absent."""
    if value is None:
        return None
    mapping = _require_mapping(value, path)
    _reject_unknown_keys(mapping, path, {"sandbox", "token_tier", "image", "runtime"})
    sandbox_type = _parse_optional_sandbox_type(
        mapping.get("sandbox"), path + ".sandbox"
    )
    token_tier = _parse_optional_token_tier(
        mapping.get("token_tier"), path + ".token_tier"
    )
    image = _parse_optional_string(mapping.get("image"), path + ".image")
    runtime = _parse_optional_container_runtime(
        mapping.get("runtime"), path + ".runtime"
    )
    return _RawIsolationConfig(
        sandbox_type=sandbox_type,
        token_tier=token_tier,
        image=image,
        runtime=runtime,
    )


def _parse_optional_sandbox_type(value: Any, path: str) -> Optional[SandboxType]:
    """Parse a sandbox type string, returning None if absent."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise _schema_error(path, "must be a string")
    normalized = value.strip()
    for st in SandboxType:
        if normalized.lower() == st.value:
            return st
        if normalized.upper() == st.name:
            return st
    allowed = ", ".join(st.value for st in SandboxType)
    raise _schema_error(path, f"invalid sandbox type '{value}'. Allowed: {allowed}")


def _parse_optional_token_tier(value: Any, path: str) -> Optional[TokenTier]:
    """Parse a token tier string, returning None if absent."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise _schema_error(path, "must be a string")
    normalized = value.strip()
    for tt in TokenTier:
        if normalized.lower() == tt.value:
            return tt
        if normalized.upper() == tt.name:
            return tt
    allowed = ", ".join(tt.value for tt in TokenTier)
    raise _schema_error(path, f"invalid token tier '{value}'. Allowed: {allowed}")


def _parse_optional_container_runtime(
    value: Any, path: str
) -> Optional[ContainerRuntime]:
    """Parse a container runtime string, returning None if absent."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise _schema_error(path, "must be a string")
    normalized = value.strip()
    for cr in ContainerRuntime:
        if normalized.lower() == cr.value:
            return cr
        if normalized.upper() == cr.name:
            return cr
    allowed = ", ".join(cr.value for cr in ContainerRuntime)
    raise _schema_error(
        path, f"invalid container runtime '{value}'. Allowed: {allowed}"
    )


def _merge_raw_isolation(
    parent: Optional[_RawIsolationConfig],
    child: Optional[_RawIsolationConfig],
) -> Optional[_RawIsolationConfig]:
    """Merge two raw isolation configs. Child overrides parent per-field."""
    if parent is None and child is None:
        return None
    if parent is None:
        return child
    if child is None:
        return parent
    return _RawIsolationConfig(
        sandbox_type=(
            child.sandbox_type
            if child.sandbox_type is not None
            else parent.sandbox_type
        ),
        token_tier=(
            child.token_tier if child.token_tier is not None else parent.token_tier
        ),
        image=child.image if child.image is not None else parent.image,
        runtime=child.runtime if child.runtime is not None else parent.runtime,
    )


def _resolve_isolation(
    raw: Optional[_RawIsolationConfig],
) -> Optional[IsolationConfig]:
    """Resolve a raw isolation config to a fully-populated IsolationConfig.

    Returns None if no isolation was configured anywhere in the chain.
    """
    if raw is None:
        return None
    return IsolationConfig(
        sandbox_type=(
            raw.sandbox_type if raw.sandbox_type is not None else SandboxType.NONE
        ),
        token_tier=raw.token_tier if raw.token_tier is not None else TokenTier.STANDARD,
        image=raw.image,
        runtime=raw.runtime,
    )


# ── Generic parsing utilities ──


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


def _validate_inputs_from_are_dependencies(
    specs: Sequence[_RawTaskSpec],
    specs_by_id: Mapping[str, _RawTaskSpec],
) -> None:
    """Validate each ``inputs_from`` target is a (transitive) dependency."""
    for task_index, spec in enumerate(specs):
        if not spec.inputs_from:
            continue
        reachable = _transitive_deps(spec.id, specs_by_id)
        for input_index, inp in enumerate(spec.inputs_from):
            if inp.task not in specs_by_id:
                raise _schema_error(
                    f"tasks[{task_index}].inputs_from[{input_index}].task",
                    f"unknown task id '{inp.task}'",
                )
            if inp.task not in reachable:
                raise _schema_error(
                    f"tasks[{task_index}].inputs_from[{input_index}].task",
                    f"task '{inp.task}' is not a dependency (direct or transitive) "
                    f"of task '{spec.id}'",
                )


def _transitive_deps(
    task_id: str,
    specs_by_id: Mapping[str, _RawTaskSpec],
) -> set[str]:
    """Compute all transitive dependencies for a task via BFS."""
    visited: set[str] = set()
    stack = list(specs_by_id[task_id].dependency_ids)
    while stack:
        dep_id = stack.pop()
        if dep_id in visited:
            continue
        visited.add(dep_id)
        if dep_id in specs_by_id:
            stack.extend(specs_by_id[dep_id].dependency_ids)
    return visited


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
