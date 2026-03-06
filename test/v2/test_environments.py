"""Tests for agentrelaysmall.v2.environments: environment types and aliases."""

import pytest

from agentrelaysmall.v2.environments import (
    AgentEnvironment,
    AgentEnvironmentT,
    TmuxEnvironment,
)

# ── Tests for TmuxEnvironment ──


class TestTmuxEnvironment:
    """Tests for TmuxEnvironment concrete type."""

    def test_default_session(self) -> None:
        """TmuxEnvironment defaults session to 'agentrelaysmall'."""
        env = TmuxEnvironment()
        assert env.session == "agentrelaysmall"

    def test_custom_session(self) -> None:
        """TmuxEnvironment can specify custom session."""
        env = TmuxEnvironment(session="custom_session")
        assert env.session == "custom_session"

    def test_is_frozen(self) -> None:
        """TmuxEnvironment is immutable."""
        env = TmuxEnvironment(session="test")
        with pytest.raises(AttributeError):
            env.session = "new_session"  # type: ignore

    def test_is_hashable(self) -> None:
        """TmuxEnvironment can be hashed."""
        env1 = TmuxEnvironment(session="agentrelay")
        env2 = TmuxEnvironment(session="agentrelay")
        assert hash(env1) == hash(env2)

    def test_equality(self) -> None:
        """TmuxEnvironments with same session are equal."""
        env1 = TmuxEnvironment(session="agentrelay")
        env2 = TmuxEnvironment(session="agentrelay")
        assert env1 == env2

    def test_inequality(self) -> None:
        """TmuxEnvironments with different sessions are not equal."""
        env1 = TmuxEnvironment(session="session1")
        env2 = TmuxEnvironment(session="session2")
        assert env1 != env2


# ── Tests for AgentEnvironment type alias ──


class TestAgentEnvironmentAlias:
    """Tests for AgentEnvironment type alias."""

    def test_alias_includes_tmux(self) -> None:
        """AgentEnvironment type alias includes TmuxEnvironment."""
        # AgentEnvironment is a TypeAlias = TmuxEnvironment
        # Currently only TmuxEnvironment is supported
        env: AgentEnvironment = TmuxEnvironment()
        assert isinstance(env, TmuxEnvironment)

    def test_alias_is_tmux_when_single_type(self) -> None:
        """AgentEnvironment alias resolves to TmuxEnvironment when it's the only type."""
        # This documents that the alias currently = TmuxEnvironment
        # When CloudEnvironment is added, this will become a union
        assert AgentEnvironment is TmuxEnvironment


# ── Tests for AgentEnvironmentT TypeVar ──


class TestAgentEnvironmentTypeVar:
    """Tests for AgentEnvironmentT TypeVar."""

    def test_typevar_is_bound(self) -> None:
        """AgentEnvironmentT TypeVar has a bound."""
        # The TypeVar should be bound to AgentEnvironment (the alias)
        # This allows generic code to preserve concrete environment types
        assert hasattr(AgentEnvironmentT, "__bound__")
        assert AgentEnvironmentT.__bound__ is TmuxEnvironment
