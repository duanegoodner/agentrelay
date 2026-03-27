"""Tests for sandbox configuration types: enums and dataclasses."""

from pathlib import Path

import pytest

from agentrelay.sandbox import (
    IsolationConfig,
    SandboxContext,
    SandboxType,
    TokenTier,
)


class TestSandboxType:
    """Tests for SandboxType enum."""

    def test_all_values_exist(self) -> None:
        assert SandboxType.NONE.value == "none"
        assert SandboxType.CONTAINER.value == "container"

    def test_is_string_enum(self) -> None:
        assert SandboxType.NONE == "none"
        assert SandboxType.CONTAINER == "container"
        assert SandboxType.NONE != "container"

    def test_all_values_are_strings(self) -> None:
        for st in SandboxType:
            assert isinstance(st.value, str)


class TestTokenTier:
    """Tests for TokenTier enum."""

    def test_all_values_exist(self) -> None:
        assert TokenTier.READ_ONLY.value == "read_only"
        assert TokenTier.STANDARD.value == "standard"
        assert TokenTier.ELEVATED.value == "elevated"

    def test_is_string_enum(self) -> None:
        assert TokenTier.STANDARD == "standard"
        assert TokenTier.READ_ONLY != "standard"

    def test_all_values_are_strings(self) -> None:
        for tt in TokenTier:
            assert isinstance(tt.value, str)


class TestIsolationConfig:
    """Tests for IsolationConfig frozen dataclass."""

    def test_construction_with_all_fields(self) -> None:
        config = IsolationConfig(
            sandbox_type=SandboxType.CONTAINER,
            token_tier=TokenTier.ELEVATED,
            image="agentrelay-agent:latest",
            runtime="podman",
        )
        assert config.sandbox_type == SandboxType.CONTAINER
        assert config.token_tier == TokenTier.ELEVATED
        assert config.image == "agentrelay-agent:latest"
        assert config.runtime == "podman"

    def test_optional_fields_default_to_none(self) -> None:
        config = IsolationConfig(
            sandbox_type=SandboxType.NONE,
            token_tier=TokenTier.STANDARD,
        )
        assert config.image is None
        assert config.runtime is None

    def test_is_frozen(self) -> None:
        config = IsolationConfig(
            sandbox_type=SandboxType.NONE,
            token_tier=TokenTier.STANDARD,
        )
        with pytest.raises(AttributeError):
            config.sandbox_type = SandboxType.CONTAINER  # type: ignore[misc]

    def test_is_hashable(self) -> None:
        config = IsolationConfig(
            sandbox_type=SandboxType.CONTAINER,
            token_tier=TokenTier.STANDARD,
        )
        assert hash(config) == hash(config)

    def test_equality(self) -> None:
        a = IsolationConfig(
            sandbox_type=SandboxType.CONTAINER,
            token_tier=TokenTier.READ_ONLY,
        )
        b = IsolationConfig(
            sandbox_type=SandboxType.CONTAINER,
            token_tier=TokenTier.READ_ONLY,
        )
        assert a == b

    def test_inequality(self) -> None:
        a = IsolationConfig(
            sandbox_type=SandboxType.CONTAINER,
            token_tier=TokenTier.READ_ONLY,
        )
        b = IsolationConfig(
            sandbox_type=SandboxType.CONTAINER,
            token_tier=TokenTier.ELEVATED,
        )
        assert a != b


class TestSandboxContext:
    """Tests for SandboxContext frozen dataclass."""

    def test_construction(self) -> None:
        ctx = SandboxContext(
            worktree_path=Path("/tmp/wt"),
            signal_dir=Path("/tmp/signals"),
            repo_path=Path("/repo"),
            task_id="task_a",
            graph_name="my-graph",
            env_vars={"GH_TOKEN": "ghp_xxx"},
        )
        assert ctx.worktree_path == Path("/tmp/wt")
        assert ctx.signal_dir == Path("/tmp/signals")
        assert ctx.repo_path == Path("/repo")
        assert ctx.task_id == "task_a"
        assert ctx.graph_name == "my-graph"
        assert ctx.env_vars == {"GH_TOKEN": "ghp_xxx"}

    def test_default_env_vars(self) -> None:
        ctx = SandboxContext(
            worktree_path=Path("/tmp/wt"),
            signal_dir=Path("/tmp/signals"),
            repo_path=Path("/repo"),
            task_id="task_a",
            graph_name="my-graph",
        )
        assert ctx.env_vars == {}

    def test_is_frozen(self) -> None:
        ctx = SandboxContext(
            worktree_path=Path("/tmp/wt"),
            signal_dir=Path("/tmp/signals"),
            repo_path=Path("/repo"),
            task_id="task_a",
            graph_name="my-graph",
        )
        with pytest.raises(AttributeError):
            ctx.task_id = "other"  # type: ignore[misc]
