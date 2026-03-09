"""Task graph package.

Backward-compatible public exports are provided here so existing imports like
``from agentrelay.task_graph import TaskGraph, TaskGraphBuilder`` continue to
work after the module-to-package refactor.
"""

from agentrelay.task_graph.builder import TaskGraphBuilder
from agentrelay.task_graph.graph import TaskGraph

__all__ = ["TaskGraph", "TaskGraphBuilder"]
