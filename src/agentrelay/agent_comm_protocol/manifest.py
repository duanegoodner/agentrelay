"""Task manifest schema and builder — Layer 1 of the agent communication protocol.

The manifest contains pure structured facts about a task: identity, paths,
workspace context, execution state, and dependency information.  No shell
commands, no framework-specific data.

Constants:
    MANIFEST_SCHEMA_VERSION: Current manifest schema version string.

Classes:
    DependencyInfo: Description of a single dependency task.
    TaskManifest: Frozen Layer-1 manifest dataclass.

Functions:
    build_manifest: Build a :class:`TaskManifest` from task spec and context.
    manifest_to_dict: Serialize a :class:`TaskManifest` to a JSON-compatible dict.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from agentrelay.task import AgentRole, TaggedPath, Task

MANIFEST_SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class DependencyInfo:
    """Description of a dependency task for manifest purposes.

    Attributes:
        description: Human-readable description of the dependency task,
            or ``None`` if no description is available.
    """

    description: Optional[str]


@dataclass(frozen=True)
class InputFileInfo:
    """A resolved input file from an upstream task's output manifest.

    Produced by the orchestrator at prepare time when a task has
    ``inputs_from`` declarations.  Provides the agent with concrete
    file paths, their semantic category, and the upstream task that
    produced them.

    Attributes:
        path: File path relative to the repository root.
        category: Semantic category of the file (e.g. ``"stubs"``).
        source_task: The upstream task ID that produced this file.
    """

    path: Path
    category: str
    source_task: str


@dataclass(frozen=True)
class TaskManifest:
    """Frozen Layer-1 manifest: pure facts about a task.

    Attributes:
        schema_version: Schema version string.
        task_id: Unique task identifier.
        role: Agent role for this task.
        description: Human-readable task description, or ``None``.
        tagged_paths: Category-tagged file paths for this task.
        branch_name: Feature branch for this task's work.
        integration_branch: Branch this task's PR targets.
        attempt_num: Current attempt number (0-indexed).
        graph_name: Name of the containing graph, or ``None``.
        dependencies: Mapping of dependency task IDs to :class:`DependencyInfo`.
        tools: Declared tool names from the graph YAML.
    """

    schema_version: str
    task_id: str
    role: AgentRole
    description: Optional[str]
    tagged_paths: tuple[TaggedPath, ...]
    branch_name: str
    integration_branch: str
    attempt_num: int
    graph_name: Optional[str]
    dependencies: dict[str, DependencyInfo]
    input_files: tuple[InputFileInfo, ...] = ()
    tools: tuple[str, ...] = ()


def build_manifest(
    task: Task,
    branch_name: str,
    integration_branch: str,
    graph_name: Optional[str],
    attempt_num: int,
    dependency_descriptions: dict[str, Optional[str]],
    tools: tuple[str, ...] = (),
    input_files: tuple[InputFileInfo, ...] = (),
) -> TaskManifest:
    """Build a :class:`TaskManifest` from task spec and contextual data.

    Args:
        task: Frozen task specification.
        branch_name: Git branch for this task's work.
        integration_branch: Branch this task's PR targets.
        graph_name: Name of the containing task graph.
        attempt_num: Current execution attempt (0-indexed).
        dependency_descriptions: Map of dependency task ID to description
            (``None`` if the dependency has no description).
        tools: Declared tool names from the graph YAML.

    Returns:
        Frozen manifest with all task facts.
    """
    return TaskManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        task_id=task.id,
        role=task.role,
        description=task.description,
        tagged_paths=task.tagged_paths,
        branch_name=branch_name,
        integration_branch=integration_branch,
        attempt_num=attempt_num,
        graph_name=graph_name,
        dependencies={
            dep_id: DependencyInfo(description=desc)
            for dep_id, desc in dependency_descriptions.items()
        },
        input_files=input_files,
        tools=tools,
    )


def manifest_to_dict(manifest: TaskManifest) -> dict[str, Any]:
    """Serialize a :class:`TaskManifest` to a JSON-compatible dict.

    The dict structure matches the Layer-1 schema defined in
    ``docs/AGENT_COMM_PROTOCOL.md``.

    Args:
        manifest: Frozen manifest to serialize.

    Returns:
        Nested dict with ``schema_version``, ``task``, ``paths``,
        ``workspace``, ``execution``, and ``dependencies`` sections.
    """
    return {
        "schema_version": manifest.schema_version,
        "task": {
            "id": manifest.task_id,
            "role": manifest.role.value,
            "description": manifest.description,
        },
        "paths": [
            {"path": str(tp.path), "category": tp.category}
            for tp in manifest.tagged_paths
        ],
        "workspace": {
            "branch_name": manifest.branch_name,
            "integration_branch": manifest.integration_branch,
        },
        "execution": {
            "attempt_num": manifest.attempt_num,
            "graph_name": manifest.graph_name,
        },
        "dependencies": {
            dep_id: {"description": info.description}
            for dep_id, info in manifest.dependencies.items()
        },
        "input_files": [
            {
                "path": str(f.path),
                "category": f.category,
                "source_task": f.source_task,
            }
            for f in manifest.input_files
        ],
        "tools": list(manifest.tools),
    }


__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "DependencyInfo",
    "InputFileInfo",
    "TaskManifest",
    "build_manifest",
    "manifest_to_dict",
]
