"""Instruction context dataclass and context content builder.

:class:`InstructionContext` captures all inputs needed by instruction builders,
decoupled from runtime and graph types. The convenience factory
:func:`instruction_context_from_runtime` constructs one from live runtime objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agentrelay.task import Task

DEFAULT_GATE_ATTEMPTS = 5


@dataclass(frozen=True)
class InstructionContext:
    """All inputs needed by instruction builders.

    Instruction builders are pure functions ``InstructionContext -> str``.
    The caller (typically a :class:`TaskPreparer` implementation) constructs
    this from whatever sources it has.

    Attributes:
        task: The frozen task specification.
        graph_branch: Integration branch the agent pushes to (e.g. ``"graph/demo"``).
        graph_name: Optional graph name, used in ADR metadata.
        dependency_descriptions: Mapping of dependency task IDs to their
            descriptions. Empty dict if the task has no dependencies.
        effective_gate_attempts: Maximum gate attempts before failure.
        attempt_num: Current attempt number (0-indexed), for conditional
            review logic.
        agent_api_module: Python module path that agents import
            ``WorktreeTaskRunner`` from. Used to generate signal commands
            in instruction text.
    """

    task: Task
    graph_branch: str
    graph_name: Optional[str] = None
    dependency_descriptions: dict[str, Optional[str]] = field(default_factory=dict)
    effective_gate_attempts: int = DEFAULT_GATE_ATTEMPTS
    attempt_num: int = 0
    agent_api_module: str = "agentrelay"


def instruction_context_from_runtime(
    runtime: "TaskRuntime",
    graph: "TaskGraph",
    graph_branch: str,
    effective_gate_attempts: int = DEFAULT_GATE_ATTEMPTS,
    agent_api_module: str = "agentrelay",
) -> InstructionContext:
    """Build an :class:`InstructionContext` from live runtime objects.

    Args:
        runtime: Mutable runtime envelope for the task.
        graph: Immutable task graph (used to look up dependency descriptions).
        graph_branch: Integration branch name.
        effective_gate_attempts: Maximum gate attempts.
        agent_api_module: Python import path for agent-side API.

    Returns:
        A frozen :class:`InstructionContext` ready for instruction builders.
    """
    dep_descriptions: dict[str, Optional[str]] = {
        dep_id: graph.task(dep_id).description for dep_id in runtime.task.dependencies
    }
    return InstructionContext(
        task=runtime.task,
        graph_branch=graph_branch,
        graph_name=graph.name,
        dependency_descriptions=dep_descriptions,
        effective_gate_attempts=effective_gate_attempts,
        attempt_num=runtime.state.attempt_num,
        agent_api_module=agent_api_module,
    )


def build_context_content(context: InstructionContext) -> Optional[str]:
    """Build ``context.md`` content from dependency descriptions.

    Returns:
        Markdown text describing prerequisite tasks, or ``None`` if the
        task has no dependencies.
    """
    if not context.dependency_descriptions:
        return None
    lines = ["# Context from prerequisite tasks\n"]
    for dep_id, description in context.dependency_descriptions.items():
        lines.append(f"## {dep_id}\n")
        lines.append(f"Description: {description}\n")
        lines.append(
            "The files produced by this task are available in your worktree "
            "(already merged into main before your branch was created).\n"
        )
    return "\n".join(lines)


# Deferred imports for type checking only — avoids circular imports.
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentrelay.task_graph import TaskGraph
    from agentrelay.task_runtime import TaskRuntime
