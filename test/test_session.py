"""Tests for SessionResolver protocol and TmuxSessionResolver."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentrelay.session import SessionError, SessionResolver, TmuxSessionResolver
from agentrelay.task_graph import TaskGraphBuilder

# --- Protocol conformance ---


def test_tmux_session_resolver_satisfies_protocol() -> None:
    assert isinstance(TmuxSessionResolver(), SessionResolver)


# --- TmuxSessionResolver.resolve ---


def test_resolve_returns_cli_session_when_provided() -> None:
    resolver = TmuxSessionResolver()
    assert resolver.resolve("my-session") == "my-session"


@patch("agentrelay.session.tmux")
def test_resolve_auto_detects_current_session(mock_tmux: MagicMock) -> None:
    mock_tmux.current_session.return_value = "detected"
    resolver = TmuxSessionResolver()
    assert resolver.resolve(None) == "detected"


@patch("agentrelay.session.tmux")
def test_resolve_raises_when_no_session(mock_tmux: MagicMock) -> None:
    mock_tmux.current_session.return_value = None
    resolver = TmuxSessionResolver()
    with pytest.raises(SessionError, match="No tmux session"):
        resolver.resolve(None)


def test_resolve_cli_overrides_auto_detect() -> None:
    """CLI session short-circuits auto-detection (no tmux mock needed)."""
    resolver = TmuxSessionResolver()
    assert resolver.resolve("explicit") == "explicit"


# --- TmuxSessionResolver.validate ---


@patch("agentrelay.session.tmux")
def test_validate_passes_with_existing_sessions(mock_tmux: MagicMock) -> None:
    mock_tmux.has_session.return_value = True
    graph = TaskGraphBuilder.from_dict(
        {
            "name": "g",
            "tasks": [
                {
                    "id": "task_a",
                    "description": "t",
                    "dependencies": [],
                    "primary_agent": {"environment": {"session": "my-session"}},
                }
            ],
        }
    )
    resolver = TmuxSessionResolver()
    resolver.validate(graph)  # Should not raise
    mock_tmux.has_session.assert_called_once_with("my-session")


@patch("agentrelay.session.tmux")
def test_validate_raises_for_missing_session(mock_tmux: MagicMock) -> None:
    mock_tmux.has_session.return_value = False
    graph = TaskGraphBuilder.from_dict(
        {
            "name": "g",
            "tasks": [
                {
                    "id": "task_a",
                    "description": "t",
                    "dependencies": [],
                    "primary_agent": {"environment": {"session": "gone"}},
                }
            ],
        }
    )
    resolver = TmuxSessionResolver()
    with pytest.raises(SessionError, match="does not exist"):
        resolver.validate(graph)


def test_validate_raises_for_empty_session() -> None:
    graph = TaskGraphBuilder.from_dict(
        {
            "name": "g",
            "tasks": [{"id": "task_a", "description": "t", "dependencies": []}],
        }
    )
    resolver = TmuxSessionResolver()
    with pytest.raises(SessionError, match="no tmux session"):
        resolver.validate(graph)


@patch("agentrelay.session.tmux")
def test_validate_deduplicates_sessions(mock_tmux: MagicMock) -> None:
    """Multiple tasks with the same session only check once."""
    mock_tmux.has_session.return_value = True
    graph = TaskGraphBuilder.from_dict(
        {
            "name": "g",
            "tasks": [
                {
                    "id": "task_a",
                    "description": "t",
                    "dependencies": [],
                    "primary_agent": {"environment": {"session": "shared"}},
                },
                {
                    "id": "task_b",
                    "description": "t",
                    "dependencies": [],
                    "primary_agent": {"environment": {"session": "shared"}},
                },
            ],
        }
    )
    resolver = TmuxSessionResolver()
    resolver.validate(graph)
    mock_tmux.has_session.assert_called_once_with("shared")
