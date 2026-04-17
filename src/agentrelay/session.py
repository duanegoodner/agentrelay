"""Session resolution and validation for agent execution environments.

This module defines the ``SessionResolver`` protocol and its
``TmuxSessionResolver`` implementation for resolving and validating
tmux sessions used by agent tasks.

Protocols:
    SessionResolver: Resolve and validate agent execution sessions.

Classes:
    TmuxSessionResolver: Tmux-based session resolution.
    SessionError: Raised when session resolution or validation fails.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from agentrelay.ops import tmux
from agentrelay.task_graph import TaskGraph


class SessionError(RuntimeError):
    """Raised when the tmux session is not specified or doesn't exist."""


@runtime_checkable
class SessionResolver(Protocol):
    """Protocol for resolving and validating agent execution sessions.

    Implementations handle auto-detection and validation of the execution
    environment (e.g., tmux sessions) where agent tasks will run.

    Methods:
        resolve: Resolve CLI session override to a concrete session name.
        validate: Validate that all tasks' sessions exist.
    """

    def resolve(self, cli_session: Optional[str]) -> str:
        """Resolve a session name from CLI override or auto-detection.

        Args:
            cli_session: Explicit session name from CLI, or ``None``
                for auto-detection.

        Returns:
            Resolved session name.

        Raises:
            SessionError: If no session can be resolved.
        """
        ...

    def validate(self, graph: TaskGraph) -> None:
        """Validate that all tasks reference existing sessions.

        Args:
            graph: Validated task graph whose tasks' sessions to check.

        Raises:
            SessionError: If any session is missing or does not exist.
        """
        ...


class TmuxSessionResolver:
    """Tmux-based session resolver.

    Resolves the session by checking the CLI override, then
    auto-detecting from the current tmux session.  Validates by
    checking ``tmux has-session`` for each unique session in the graph.
    """

    def resolve(self, cli_session: Optional[str]) -> str:
        """Resolve tmux session: CLI flag > auto-detect > error.

        Args:
            cli_session: Explicit session name, or ``None``.

        Returns:
            Resolved tmux session name.

        Raises:
            SessionError: If not in tmux and no CLI override given.
        """
        if cli_session is not None:
            return cli_session
        detected = tmux.current_session()
        if detected is None:
            raise SessionError(
                "No tmux session specified and not running inside tmux.\n"
                "Either run from inside a tmux session or use --tmux-session."
            )
        return detected

    def validate(self, graph: TaskGraph) -> None:
        """Validate that all tasks' tmux sessions exist.

        Checks two things for every task in the graph:

        1. The task has a non-empty session name.
        2. The tmux session actually exists (``tmux has-session``).

        Args:
            graph: Task graph to validate.

        Raises:
            SessionError: If any task's session is empty or the tmux
                session does not exist.
        """
        sessions_seen: set[str] = set()
        for task_id in graph.task_ids():
            task = graph.task(task_id)
            session = task.primary_agent.environment.session
            if not session:
                raise SessionError(
                    f"Task '{task_id}' has no tmux session specified.\n"
                    "Use --tmux-session on the CLI or run from inside a tmux session."
                )
            sessions_seen.add(session)

        for session in sorted(sessions_seen):
            if not tmux.has_session(session):
                raise SessionError(
                    f"Tmux session '{session}' does not exist.\n"
                    f"Create it first: tmux new-session -d -s {session}"
                )
