"""Tests for sandbox configuration types: enums and dataclasses."""

from pathlib import Path

import pytest

from agentrelay.sandbox import (
    ContainerRuntime,
    IsolationConfig,
    SandboxContext,
    SandboxType,
    TokenTier,
)


class TestSandboxType:
    """Tests for SandboxType enum."""

    def test_all_values_exist(self) -> None:
        assert SandboxType.NONE.value == "none"
        assert SandboxType.OCI.value == "oci"

    def test_is_string_enum(self) -> None:
        assert SandboxType.NONE == "none"
        assert SandboxType.OCI == "oci"
        assert SandboxType.NONE != "oci"

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


class TestContainerRuntime:
    """Tests for ContainerRuntime enum."""

    def test_all_values_exist(self) -> None:
        assert ContainerRuntime.DOCKER.value == "docker"
        assert ContainerRuntime.PODMAN.value == "podman"

    def test_is_string_enum(self) -> None:
        assert ContainerRuntime.DOCKER == "docker"
        assert ContainerRuntime.PODMAN == "podman"
        assert ContainerRuntime.DOCKER != "podman"

    def test_all_values_are_strings(self) -> None:
        for cr in ContainerRuntime:
            assert isinstance(cr.value, str)


class TestIsolationConfig:
    """Tests for IsolationConfig frozen dataclass."""

    def test_construction_with_all_fields(self) -> None:
        config = IsolationConfig(
            sandbox_type=SandboxType.OCI,
            token_tier=TokenTier.ELEVATED,
            image="agentrelay-agent:latest",
            runtime=ContainerRuntime.PODMAN,
        )
        assert config.sandbox_type == SandboxType.OCI
        assert config.token_tier == TokenTier.ELEVATED
        assert config.image == "agentrelay-agent:latest"
        assert config.runtime == ContainerRuntime.PODMAN

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
            config.sandbox_type = SandboxType.OCI  # type: ignore[misc]

    def test_is_hashable(self) -> None:
        config = IsolationConfig(
            sandbox_type=SandboxType.OCI,
            token_tier=TokenTier.STANDARD,
        )
        assert hash(config) == hash(config)

    def test_equality(self) -> None:
        a = IsolationConfig(
            sandbox_type=SandboxType.OCI,
            token_tier=TokenTier.READ_ONLY,
        )
        b = IsolationConfig(
            sandbox_type=SandboxType.OCI,
            token_tier=TokenTier.READ_ONLY,
        )
        assert a == b

    def test_inequality(self) -> None:
        a = IsolationConfig(
            sandbox_type=SandboxType.OCI,
            token_tier=TokenTier.READ_ONLY,
        )
        b = IsolationConfig(
            sandbox_type=SandboxType.OCI,
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
