"""Runtime builders for workstream graph execution state.

This module defines :class:`WorkstreamRuntimeBuilder`, which creates initial
``WorkstreamRuntime`` objects for every workstream in a
:class:`agentrelay.task_graph.TaskGraph`.
"""

from __future__ import annotations

from agentrelay.task_graph import TaskGraph
from agentrelay.workstream_runtime import WorkstreamRuntime


class WorkstreamRuntimeBuilder:
    """Builder for initializing per-workstream runtime envelopes from a graph."""

    @classmethod
    def from_graph(cls, graph: TaskGraph) -> dict[str, WorkstreamRuntime]:
        """Build initial runtimes for all workstreams in a graph.

        Runtimes are returned in the graph's stable sorted workstream order.
        Each runtime starts with default mutable state/artifacts.

        Args:
            graph: Validated immutable task graph.

        Returns:
            dict[str, WorkstreamRuntime]: Workstream runtimes keyed by ID.
        """
        runtimes: dict[str, WorkstreamRuntime] = {}
        for workstream_id in graph.workstream_ids():
            runtimes[workstream_id] = WorkstreamRuntime(
                spec=graph.workstream(workstream_id)
            )
        return runtimes
