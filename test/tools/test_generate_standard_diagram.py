"""Tests for tools/generate_standard_diagram.py — private node filtering."""

from __future__ import annotations

from pathlib import Path

from tools.generate_standard_diagram import filter_private_nodes

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REAL_DIAGRAM = Path("docs/diagram-detailed.d2")


def _filter(text: str) -> list[str]:
    """Filter a multi-line D2 snippet and return the result lines."""
    return filter_private_nodes(text.splitlines())


# ---------------------------------------------------------------------------
# Unit tests — filter_private_nodes
# ---------------------------------------------------------------------------


class TestFilterPrivateNodes:
    """Tests for the core filter_private_nodes function."""

    def test_strips_private_node_block(self) -> None:
        """A _-prefixed node and its nested content are removed."""
        d2 = """\
pkg: "pkg/" {
  Public: "Public" {
    shape: class
  }

  _Private: "_Private <<internal>>" {
    shape: class
    +method(): void
  }
}"""
        result = _filter(d2)
        joined = "\n".join(result)
        assert "Public" in joined
        assert "_Private" not in joined
        assert "+method" not in joined

    def test_strips_private_relationship(self) -> None:
        """Relationship lines referencing _-prefixed nodes are removed."""
        d2 = """\
pkg.Public -> pkg._Private: creates { class: dependency }
pkg.Public -> pkg.Other: uses { class: dependency }"""
        result = _filter(d2)
        assert len(result) == 1
        assert "Other" in result[0]

    def test_preserves_public_nodes(self) -> None:
        """Non-prefixed nodes survive intact."""
        d2 = """\
pkg: "pkg/" {
  TaskGraph: "TaskGraph" {
    shape: class
    +task_ids(): "tuple[str, ...]"
  }
}"""
        result = _filter(d2)
        assert len(result) == 6
        assert "TaskGraph" in "\n".join(result)

    def test_preserves_comments_and_blanks(self) -> None:
        """Comments and blank lines pass through."""
        d2 = """\
# This is a comment

# Another comment
pkg.A -> pkg.B: uses { class: dependency }"""
        result = _filter(d2)
        assert len(result) == 4

    def test_strips_deeply_nested_private_node(self) -> None:
        """A _-prefixed node nested several levels deep is removed."""
        d2 = """\
outer: "outer/" {
  inner: "inner/" {
    _Secret: "_Secret" {
      shape: class
      field: str
    }
    Public: "Public" {
      shape: class
    }
  }
}"""
        result = _filter(d2)
        joined = "\n".join(result)
        assert "_Secret" not in joined
        assert "Public" in joined

    def test_strips_single_line_private_node(self) -> None:
        """A _-prefixed node without nested braces is removed."""
        d2 = """\
pkg: "pkg/" {
  _Simple: "_Simple <<exception>>" { shape: class }
  Public: "Public" { shape: class }
}"""
        result = _filter(d2)
        joined = "\n".join(result)
        assert "_Simple" not in joined
        assert "Public" in joined

    def test_relationship_with_private_target(self) -> None:
        """A relationship where only the target is private is removed."""
        d2 = """\
pkg.Pub -> pkg._Priv: uses { class: dependency }
pkg.Pub -> pkg.Other: uses { class: dependency }"""
        result = _filter(d2)
        assert len(result) == 1
        assert "Other" in result[0]

    def test_relationship_with_private_source(self) -> None:
        """A relationship where only the source is private is removed."""
        d2 = """\
pkg._Priv -> pkg.Pub: uses { class: dependency }
pkg.Other -> pkg.Pub: uses { class: dependency }"""
        result = _filter(d2)
        assert len(result) == 1
        assert "Other" in result[0]

    def test_private_field_values_not_stripped(self) -> None:
        """Display strings containing _ names in field values survive."""
        d2 = """\
  WorkflowPolicies: "WorkflowPolicies" {
    shape: class
    commit_policy: "_CommitPolicy | None"
  }"""
        result = _filter(d2)
        assert len(result) == 4
        assert "_CommitPolicy | None" in "\n".join(result)


# ---------------------------------------------------------------------------
# End-to-end — real diagram
# ---------------------------------------------------------------------------


class TestEndToEnd:
    """Tests against the actual diagram-detailed.d2 file."""

    def test_real_diagram_filters_without_error(self) -> None:
        """The filter runs on the real diagram without raising."""
        lines = _REAL_DIAGRAM.read_text().splitlines()
        result = filter_private_nodes(lines)
        assert len(result) > 0
        assert len(result) < len(lines)

    def test_real_diagram_removes_private_nodes(self) -> None:
        """Known private nodes are absent from filtered output."""
        lines = _REAL_DIAGRAM.read_text().splitlines()
        result = filter_private_nodes(lines)
        joined = "\n".join(result)

        # These node definitions should be gone
        assert '_OrchestratorRun: "' not in joined
        assert '_WorkspaceIntegrationError: "' not in joined
        assert '_CommitPolicy: "' not in joined
        assert '_validation: "' not in joined
        assert '_indexing: "' not in joined

    def test_real_diagram_preserves_public_nodes(self) -> None:
        """Key public nodes survive filtering."""
        lines = _REAL_DIAGRAM.read_text().splitlines()
        result = filter_private_nodes(lines)
        joined = "\n".join(result)

        assert "Orchestrator" in joined
        assert "TaskGraph" in joined
        assert "TaskRuntime" in joined
        assert "WorkflowPolicies" in joined
        assert "IntegrationError" in joined

    def test_real_diagram_line_reduction(self) -> None:
        """Filtering removes a meaningful number of lines."""
        lines = _REAL_DIAGRAM.read_text().splitlines()
        result = filter_private_nodes(lines)
        removed = len(lines) - len(result)
        # We expect at least 50 lines removed (15+ nodes × ~3-5 lines each + arrows)
        assert removed >= 50, f"Only {removed} lines removed — expected >= 50"
