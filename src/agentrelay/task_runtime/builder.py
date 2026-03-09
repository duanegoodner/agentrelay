"""Runtime builders for task graph execution state.

This module defines :class:`TaskRuntimeBuilder`, which creates initial
``TaskRuntime`` objects for every task in a :class:`agentrelay.task_graph.TaskGraph`.
"""

from __future__ import annotations

from agentrelay.task_graph import TaskGraph
from agentrelay.task_runtime.runtime import TaskRuntime


class TaskRuntimeBuilder:
    """Builder for initializing per-task runtime envelopes from a task graph."""

    @classmethod
    def from_graph(cls, graph: TaskGraph) -> dict[str, TaskRuntime]:
        """Build initial runtimes for all tasks in a graph.

        Runtimes are returned in the graph's stable topological task order.
        Each runtime starts with default mutable state/artifacts and no agent.

        Args:
            graph: Validated immutable task graph.

        Returns:
            dict[str, TaskRuntime]: Task runtimes keyed by task ID.
        """
        runtimes: dict[str, TaskRuntime] = {}
        for task_id in graph.task_ids():
            runtimes[task_id] = TaskRuntime(task=graph.task(task_id))
        return runtimes
