"""Task graph model and construction surface.

This package exposes the class-based task-graph API used by orchestration code:
an immutable ``TaskGraph`` plus ``TaskGraphBuilder`` for loading and validating
graph definitions. Utility indexing/validation helpers live in submodules.
"""

from agentrelay.task_graph.builder import TaskGraphBuilder
from agentrelay.task_graph.graph import TaskGraph

__all__ = ["TaskGraph", "TaskGraphBuilder"]
