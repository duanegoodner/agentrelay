"""Tests for workstream specifications."""

import pytest

from agentrelay.workstream import WorkstreamSpec


class TestWorkstreamSpec:
    """Tests for WorkstreamSpec."""

    def test_minimal_workstream_defaults(self) -> None:
        """WorkstreamSpec defaults base and merge target to main."""
        spec = WorkstreamSpec(id="default")
        assert spec.id == "default"
        assert spec.parent_workstream_id is None
        assert spec.base_branch == "main"
        assert spec.merge_target_branch == "main"

    def test_workstream_with_parent_and_custom_branches(self) -> None:
        """WorkstreamSpec supports parent linkage and branch overrides."""
        spec = WorkstreamSpec(
            id="feature_a.1",
            parent_workstream_id="feature_a",
            base_branch="feature_a",
            merge_target_branch="feature_a",
        )
        assert spec.id == "feature_a.1"
        assert spec.parent_workstream_id == "feature_a"
        assert spec.base_branch == "feature_a"
        assert spec.merge_target_branch == "feature_a"

    def test_is_frozen(self) -> None:
        """WorkstreamSpec is immutable."""
        spec = WorkstreamSpec(id="default")
        with pytest.raises(AttributeError):
            spec.base_branch = "develop"  # type: ignore

    def test_is_hashable(self) -> None:
        """WorkstreamSpec can be hashed."""
        spec1 = WorkstreamSpec(id="default")
        spec2 = WorkstreamSpec(id="default")
        assert hash(spec1) == hash(spec2)

    def test_equality(self) -> None:
        """WorkstreamSpec equality is value-based."""
        spec1 = WorkstreamSpec(id="feature_a", base_branch="main")
        spec2 = WorkstreamSpec(id="feature_a", base_branch="main")
        assert spec1 == spec2
