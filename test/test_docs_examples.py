"""Tests that docs examples stay valid against the current TaskGraph schema."""

from pathlib import Path

from agentrelay.task_graph import TaskGraphBuilder

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "docs" / "examples"


def test_schema_example_files_parse() -> None:
    expected = {
        "minimal.yaml",
        "workstreams.yaml",
        "mixed-default-and-explicit-workstreams.yaml",
    }

    actual = {path.name for path in EXAMPLES_DIR.glob("*.yaml")}
    assert expected.issubset(actual)

    for name in sorted(expected):
        graph = TaskGraphBuilder.from_yaml(EXAMPLES_DIR / name)
        assert graph.name is not None
        assert len(graph.task_ids()) > 0


def test_workstreams_example_has_expected_hierarchy() -> None:
    graph = TaskGraphBuilder.from_yaml(EXAMPLES_DIR / "workstreams.yaml")

    assert graph.max_workstream_depth == 2
    assert graph.workstream("feature_a_spec").parent_workstream_id == "feature_a"
    assert graph.workstream("feature_a_impl").parent_workstream_id == "feature_a"
    assert graph.task("write_spec").workstream_id == "feature_a_spec"
    assert graph.task("implement").workstream_id == "feature_a_impl"


def test_mixed_example_keeps_default_workstream_valid() -> None:
    graph = TaskGraphBuilder.from_yaml(
        EXAMPLES_DIR / "mixed-default-and-explicit-workstreams.yaml"
    )

    assert graph.task("prep_repo").workstream_id == "default"
    assert "default" in graph.workstream_ids()
    assert graph.task("implement_feature_b").workstream_id == "feature_b"
