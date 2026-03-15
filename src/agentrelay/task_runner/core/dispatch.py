"""Per-step dispatch table for lifecycle step implementation selection.

This module defines the generic :class:`StepDispatch` type used by
:class:`~agentrelay.task_runner.core.runner.StandardTaskRunner` to select
the right protocol implementation for each lifecycle step.

Classes:
    StepDispatch: Frozen dispatch table mapping (framework, env_type) keys
        to per-step protocol implementation factories.

Type aliases:
    DispatchKey: Tuple of (AgentFramework, type) used as dispatch lookup key.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Generic, TypeAlias, TypeVar

from agentrelay.task import AgentFramework
from agentrelay.task_runtime import TaskRuntime

T = TypeVar("T")

DispatchKey: TypeAlias = tuple[AgentFramework, type]


@dataclass(frozen=True)
class StepDispatch(Generic[T]):
    """Per-step dispatch table for one lifecycle step.

    Selects the right protocol implementation based on the task's
    :class:`~agentrelay.task.AgentFramework` and
    :class:`~agentrelay.environments.AgentEnvironment` type. Each entry
    maps a ``(framework, env_type)`` key to a factory callable that
    receives the :class:`TaskRuntime` and returns a protocol implementation.
    The ``default`` fallback handles steps that don't vary by
    framework/environment.

    Callable — use as ``self._preparer(runtime)`` directly via
    :meth:`__call__`.

    Dispatch resolution order:
      1. Exact match in ``entries`` for ``(framework, type(environment))``
      2. ``default`` fallback
      3. ``KeyError`` if neither matches

    Extension guide:
      To add support for a new ``AgentFramework`` or ``AgentEnvironment``,
      add an entry to the ``entries`` dict for each step that has a
      distinct implementation for that combo. Steps that don't vary
      (e.g. preparer, merger) can continue using ``default``.

    Attributes:
        entries: Mapping of ``(AgentFramework, type)`` dispatch keys to
            factory callables returning protocol implementations.
        default: Fallback factory used when no exact key match exists.
    """

    entries: dict[DispatchKey, Callable[[TaskRuntime], T]] = field(default_factory=dict)
    default: Callable[[TaskRuntime], T] | None = None

    def __call__(self, runtime: TaskRuntime) -> T:
        """Resolve and return the protocol implementation for this runtime.

        Args:
            runtime: Task runtime used to extract the dispatch key from
                ``runtime.task.primary_agent``.

        Returns:
            The resolved protocol implementation instance.

        Raises:
            KeyError: If no entry matches and no default is provided.
        """
        key = (
            runtime.task.primary_agent.framework,
            type(runtime.task.primary_agent.environment),
        )
        factory = self.entries.get(key)
        if factory is not None:
            return factory(runtime)
        if self.default is not None:
            return self.default(runtime)
        raise KeyError(
            f"No implementation registered for {key} and no default provided"
        )


__all__ = [
    "DispatchKey",
    "StepDispatch",
]
