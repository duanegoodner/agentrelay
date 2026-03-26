"""Tests for tools/d2_filters.py — composable D2 diagram filters."""

from __future__ import annotations

from pathlib import Path

from tools.d2_filters import collapse_impl_packages, filter_private_nodes

_REAL_DIAGRAM = Path("docs/diagrams/uml/diagram-detailed.d2")


def _apply(fn, text: str) -> list[str]:  # type: ignore[type-arg]
    """Apply a filter to a multi-line D2 snippet."""
    return fn(text.splitlines())


# ---------------------------------------------------------------------------
# filter_private_nodes
# ---------------------------------------------------------------------------


class TestFilterPrivateNodes:
    def test_strips_private_node_block(self) -> None:
        d2 = """\
pkg: "pkg/" {
  Public: "Public" {
    shape: class
  }
  _Private: "_Private" {
    shape: class
    +method(): void
  }
}"""
        result = _apply(filter_private_nodes, d2)
        joined = "\n".join(result)
        assert "Public" in joined
        assert "_Private" not in joined

    def test_strips_private_relationship(self) -> None:
        d2 = """\
pkg.Public -> pkg._Private: creates { class: dependency }
pkg.Public -> pkg.Other: uses { class: dependency }"""
        result = _apply(filter_private_nodes, d2)
        assert len(result) == 1
        assert "Other" in result[0]

    def test_preserves_public_nodes(self) -> None:
        d2 = """\
pkg: "pkg/" {
  TaskGraph: "TaskGraph" {
    shape: class
  }
}"""
        result = _apply(filter_private_nodes, d2)
        assert "TaskGraph" in "\n".join(result)

    def test_private_field_values_not_stripped(self) -> None:
        d2 = """\
  WorkflowPolicies: "WorkflowPolicies" {
    shape: class
    commit_policy: "_CommitPolicy | None"
  }"""
        result = _apply(filter_private_nodes, d2)
        assert "_CommitPolicy | None" in "\n".join(result)

    def test_real_diagram_removes_private_nodes(self) -> None:
        lines = _REAL_DIAGRAM.read_text().splitlines()
        result = filter_private_nodes(lines)
        joined = "\n".join(result)
        assert '_OrchestratorRun: "' not in joined
        assert '_WorkspaceIntegrationError: "' not in joined
        assert '_CommitPolicy: "' not in joined
        assert "Orchestrator" in joined
        assert "TaskGraph" in joined


# ---------------------------------------------------------------------------
# collapse_impl_packages
# ---------------------------------------------------------------------------


class TestCollapseImplPackages:
    def test_collapses_impl_contents(self) -> None:
        d2 = """\
pkg: "pkg/" {
  core_pkg: "core/" {
    Protocol: "Protocol" {
      shape: class
    }
  }
  test_impl_pkg: "implementations/" {
    ConcreteA: "ConcreteA" {
      shape: class
    }
    ConcreteB: "ConcreteB" {
      shape: class
    }
  }
}"""
        result = _apply(collapse_impl_packages, d2)
        joined = "\n".join(result)
        assert 'test_impl_pkg: "implementations/"' in joined
        assert "(2 classes hidden)" in joined
        assert "ConcreteA" not in joined
        assert "ConcreteB" not in joined
        assert "Protocol" in joined

    def test_retargets_impl_relationships(self) -> None:
        d2 = """\
pkg: "pkg/" {
  test_impl_pkg: "implementations/" {
    ConcreteA: "ConcreteA" {
      shape: class
    }
  }
}
pkg.test_impl_pkg.ConcreteA -> other.Protocol: satisfies { class: implementation }
other.Protocol -> other.Foo: uses { class: dependency }"""
        result = _apply(collapse_impl_packages, d2)
        joined = "\n".join(result)
        # Arrow retargeted to container, class name gone from arrow
        assert "pkg.test_impl_pkg -> other.Protocol" in joined
        assert "ConcreteA" not in joined
        # Unrelated arrow survives
        assert "other.Protocol -> other.Foo" in joined

    def test_deduplicates_retargeted_arrows(self) -> None:
        d2 = """\
pkg: "pkg/" {
  test_impl_pkg: "implementations/" {
    A: "A" { shape: class }
    B: "B" { shape: class }
  }
}
pkg.test_impl_pkg.A -> ops.git: uses { class: dependency }
pkg.test_impl_pkg.B -> ops.git: uses { class: dependency }"""
        result = _apply(collapse_impl_packages, d2)
        joined = "\n".join(result)
        # Only one arrow to ops.git, not two
        assert joined.count("-> ops.git") == 1
        assert "pkg.test_impl_pkg -> ops.git" in joined

    def test_drops_self_loop_arrows(self) -> None:
        d2 = """\
pkg: "pkg/" {
  test_impl_pkg: "implementations/" {
    A: "A" { shape: class }
    B: "B" { shape: class }
  }
}
pkg.test_impl_pkg.A -> pkg.test_impl_pkg.B: uses { class: dependency }"""
        result = _apply(collapse_impl_packages, d2)
        joined = "\n".join(result)
        # Self-loop (impl_pkg -> impl_pkg) is dropped
        assert "->" not in joined

    def test_preserves_core_contents(self) -> None:
        d2 = """\
pkg: "pkg/" {
  core_pkg: "core/" {
    Protocol: "Protocol" {
      shape: class
    }
  }
  test_impl_pkg: "implementations/" {
    Concrete: "Concrete" {
      shape: class
    }
  }
}"""
        result = _apply(collapse_impl_packages, d2)
        joined = "\n".join(result)
        assert "Protocol" in joined
        assert "core_pkg" in joined

    def test_single_class_uses_singular(self) -> None:
        d2 = """\
  my_test_impl_pkg: "implementations/" {
    OnlyOne: "OnlyOne" {
      shape: class
    }
  }"""
        result = _apply(collapse_impl_packages, d2)
        assert "(1 class hidden)" in "\n".join(result)

    def test_no_impl_packages_passes_through(self) -> None:
        d2 = """\
pkg: "pkg/" {
  Foo: "Foo" {
    shape: class
  }
}"""
        result = _apply(collapse_impl_packages, d2)
        assert len(result) == len(d2.splitlines())

    def test_real_diagram_collapses_all_impl_packages(self) -> None:
        lines = _REAL_DIAGRAM.read_text().splitlines()
        result = collapse_impl_packages(lines)
        joined = "\n".join(result)

        assert "(2 classes hidden)" in joined  # agent_impl_pkg
        assert "(5 classes hidden)" in joined  # workstream_impl_pkg
        assert "(7 classes hidden)" in joined  # task_runner_impl_pkg

        assert "agent_impl_pkg" in joined  # container kept
        assert "TmuxAddress" not in joined  # contents removed
        assert "WorktreeTaskPreparer" not in joined

    def test_real_diagram_retargets_impl_relationships(self) -> None:
        lines = _REAL_DIAGRAM.read_text().splitlines()
        result = collapse_impl_packages(lines)
        joined = "\n".join(result)
        # Specific class names no longer appear in arrows
        assert "task_runner_impl_pkg.WorktreeTaskPreparer" not in joined
        assert "agent_impl_pkg.TmuxAgent" not in joined
        # But retargeted container arrows exist (impl_pkg -> ops, etc.)
        assert (
            "task_runner_impl_pkg -> " in joined or "task_runner_impl_pkg ->" in joined
        )
        # ops_pkg should still have incoming arrows
        assert "ops_pkg" in joined


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------


class TestFilterComposition:
    def test_private_then_impl(self) -> None:
        d2 = """\
pkg: "pkg/" {
  _Internal: "_Internal" {
    shape: class
  }
  test_impl_pkg: "implementations/" {
    Concrete: "Concrete" {
      shape: class
    }
  }
  Public: "Public" {
    shape: class
  }
}
pkg._Internal -> pkg.Public: uses { class: dependency }
pkg.test_impl_pkg.Concrete -> pkg.Public: satisfies { class: implementation }"""
        lines = d2.splitlines()
        lines = filter_private_nodes(lines)
        lines = collapse_impl_packages(lines)
        joined = "\n".join(lines)
        assert "_Internal" not in joined
        assert "Concrete" not in joined
        assert "(1 class hidden)" in joined
        assert "Public" in joined
        # Impl arrow retargeted to container
        assert "pkg.test_impl_pkg -> pkg.Public" in joined

    def test_real_diagram_both_filters(self) -> None:
        lines = _REAL_DIAGRAM.read_text().splitlines()
        filtered = filter_private_nodes(lines)
        filtered = collapse_impl_packages(filtered)
        assert len(filtered) < len(lines)
        joined = "\n".join(filtered)
        # Private nodes gone
        assert '_OrchestratorRun: "' not in joined
        # Impl contents gone
        assert "TmuxAddress" not in joined
        # Public nodes survive
        assert "Orchestrator" in joined
        assert "TaskGraph" in joined
        # Impl containers survive
        assert "agent_impl_pkg" in joined
