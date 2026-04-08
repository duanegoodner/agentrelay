"""Tests for the graph index module."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentrelay.graph_index import (
    DuplicateGraphNameError,
    GraphEntry,
    GraphIndex,
    _extract_category,
    _is_path_reference,
    _read_graph_name,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_graph(path: Path, name: str) -> Path:
    """Write a minimal graph YAML with the given name."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"name: {name}\ntasks: []\n")
    return path


# ---------------------------------------------------------------------------
# _read_graph_name
# ---------------------------------------------------------------------------


def test_read_graph_name_returns_name(tmp_path: Path) -> None:
    f = tmp_path / "g.yaml"
    f.write_text("name: my-graph\ntasks: []\n")
    assert _read_graph_name(f) == "my-graph"


def test_read_graph_name_returns_none_for_missing_name(tmp_path: Path) -> None:
    f = tmp_path / "g.yaml"
    f.write_text("tasks: []\n")
    assert _read_graph_name(f) is None


def test_read_graph_name_returns_none_for_invalid_yaml(tmp_path: Path) -> None:
    f = tmp_path / "g.yaml"
    f.write_text(":::\n")
    assert _read_graph_name(f) is None


def test_read_graph_name_returns_none_for_non_dict_yaml(tmp_path: Path) -> None:
    f = tmp_path / "g.yaml"
    f.write_text("- item1\n- item2\n")
    assert _read_graph_name(f) is None


# ---------------------------------------------------------------------------
# _extract_category
# ---------------------------------------------------------------------------


def test_extract_category_single_level(tmp_path: Path) -> None:
    yaml_path = tmp_path / "smoke" / "g.yaml"
    yaml_path.parent.mkdir()
    yaml_path.touch()
    assert _extract_category(tmp_path, yaml_path) == "smoke"


def test_extract_category_nested(tmp_path: Path) -> None:
    yaml_path = tmp_path / "roles" / "experiments" / "g.yaml"
    yaml_path.parent.mkdir(parents=True)
    yaml_path.touch()
    assert _extract_category(tmp_path, yaml_path) == "roles/experiments"


def test_extract_category_root_level(tmp_path: Path) -> None:
    yaml_path = tmp_path / "g.yaml"
    yaml_path.touch()
    assert _extract_category(tmp_path, yaml_path) == ""


# ---------------------------------------------------------------------------
# _is_path_reference
# ---------------------------------------------------------------------------


def test_is_path_reference_with_slash() -> None:
    assert _is_path_reference("graphs/smoke/quick_chained.yaml") is True


def test_is_path_reference_with_yaml_extension() -> None:
    assert _is_path_reference("quick_chained.yaml") is True


def test_is_path_reference_plain_name() -> None:
    assert _is_path_reference("quick-chained") is False


# ---------------------------------------------------------------------------
# GraphIndex.__init__ + entries
# ---------------------------------------------------------------------------


def test_index_scans_directory(tmp_path: Path) -> None:
    _write_graph(tmp_path / "smoke" / "a.yaml", "alpha")
    _write_graph(tmp_path / "work" / "b.yaml", "beta")

    index = GraphIndex(tmp_path)
    entries = index.entries

    assert len(entries) == 2
    assert entries[0].name == "alpha"
    assert entries[0].category == "smoke"
    assert entries[1].name == "beta"
    assert entries[1].category == "work"


def test_index_raises_on_nonexistent_directory(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Graph directory not found"):
        GraphIndex(tmp_path / "nope")


def test_index_raises_on_duplicate_names(tmp_path: Path) -> None:
    _write_graph(tmp_path / "a" / "one.yaml", "dup")
    _write_graph(tmp_path / "b" / "two.yaml", "dup")

    with pytest.raises(DuplicateGraphNameError, match="'dup'"):
        GraphIndex(tmp_path)


def test_index_duplicate_error_lists_all_paths(tmp_path: Path) -> None:
    path_a = _write_graph(tmp_path / "a" / "one.yaml", "dup")
    path_b = _write_graph(tmp_path / "b" / "two.yaml", "dup")

    with pytest.raises(DuplicateGraphNameError) as exc_info:
        GraphIndex(tmp_path)

    msg = str(exc_info.value)
    assert str(path_a.resolve()) in msg
    assert str(path_b.resolve()) in msg


def test_index_skips_files_without_name(tmp_path: Path) -> None:
    _write_graph(tmp_path / "good.yaml", "good")
    bad = tmp_path / "bad.yaml"
    bad.write_text("tasks: []\n")

    index = GraphIndex(tmp_path)
    assert len(index.entries) == 1
    assert index.entries[0].name == "good"


def test_index_skips_invalid_yaml(tmp_path: Path) -> None:
    _write_graph(tmp_path / "good.yaml", "good")
    broken = tmp_path / "broken.yaml"
    broken.write_text(":::\n")

    index = GraphIndex(tmp_path)
    assert len(index.entries) == 1


def test_index_empty_directory(tmp_path: Path) -> None:
    index = GraphIndex(tmp_path)
    assert index.entries == ()


# ---------------------------------------------------------------------------
# GraphIndex.resolve
# ---------------------------------------------------------------------------


def test_resolve_by_name(tmp_path: Path) -> None:
    target = _write_graph(tmp_path / "smoke" / "quick.yaml", "quick-chained")
    index = GraphIndex(tmp_path)
    assert index.resolve("quick-chained") == target.resolve()


def test_resolve_by_name_not_found(tmp_path: Path) -> None:
    _write_graph(tmp_path / "g.yaml", "existing")
    index = GraphIndex(tmp_path)

    with pytest.raises(KeyError, match="nonexistent"):
        index.resolve("nonexistent")


def test_resolve_by_name_not_found_lists_available(tmp_path: Path) -> None:
    _write_graph(tmp_path / "a.yaml", "alpha")
    _write_graph(tmp_path / "b.yaml", "beta")
    index = GraphIndex(tmp_path)

    with pytest.raises(KeyError, match="alpha") as exc_info:
        index.resolve("missing")
    assert "beta" in str(exc_info.value)


def test_resolve_by_absolute_path(tmp_path: Path) -> None:
    target = _write_graph(tmp_path / "smoke" / "quick.yaml", "quick-chained")
    index = GraphIndex(tmp_path)
    assert index.resolve(str(target.resolve())) == target.resolve()


def test_resolve_by_relative_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _write_graph(tmp_path / "smoke" / "quick.yaml", "quick-chained")
    monkeypatch.chdir(tmp_path)
    index = GraphIndex(tmp_path)
    assert index.resolve("smoke/quick.yaml") == target.resolve()


def test_resolve_by_path_not_in_index(tmp_path: Path) -> None:
    _write_graph(tmp_path / "g.yaml", "existing")
    index = GraphIndex(tmp_path)

    outside = tmp_path / "other" / "missing.yaml"
    outside.parent.mkdir(parents=True)
    outside.write_text("name: other\ntasks: []\n")

    with pytest.raises(ValueError, match="not found in index"):
        index.resolve(str(outside))


def test_resolve_path_with_yaml_extension_only(tmp_path: Path) -> None:
    target = _write_graph(tmp_path / "quick.yaml", "quick-chained")
    index = GraphIndex(tmp_path)
    assert index.resolve(str(target.resolve())) == target.resolve()
