"""Tests for tools/generate_overview.py — package-level overview diagram generator."""

from __future__ import annotations

# The script lives outside the installed package, so import via importlib.
import importlib.util
import sys
from pathlib import Path
from textwrap import dedent

import pytest

_TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
_SPEC = importlib.util.spec_from_file_location(
    "generate_overview", _TOOLS_DIR / "generate_overview.py"
)
assert _SPEC is not None and _SPEC.loader is not None
generate_overview_mod = importlib.util.module_from_spec(_SPEC)
sys.modules["generate_overview"] = generate_overview_mod
_SPEC.loader.exec_module(generate_overview_mod)

parse_packages = generate_overview_mod.parse_packages
parse_relationships = generate_overview_mod.parse_relationships
resolve_package = generate_overview_mod.resolve_package
build_overview_arrows = generate_overview_mod.build_overview_arrows
generate_overview_d2 = generate_overview_mod.generate_overview_d2
generate_overview_html = generate_overview_mod.generate_overview_html
Package = generate_overview_mod.Package
Relationship = generate_overview_mod.Relationship


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_D2 = dedent("""\
    direction: down

    classes: {
      composition: {
        style.stroke: "#333333"
      }
    }

    pkg_a: "package_a/" {
      ClassA: "ClassA <<dataclass>>" {
        shape: class
        field1: str
      }

      ClassB: "ClassB <<enum>>" {
        shape: class
        VAL1
        VAL2
      }
    }

    pkg_b: "package_b/" {
      sub_pkg: "core/" {
        ClassC: "ClassC <<protocol>>" {
          shape: class
          +method(): void
        }
      }

      impl_pkg: "implementations/" {
        ClassD: "ClassD <<dataclass>>" {
          shape: class
          +run(): void
        }
      }
    }

    pkg_c: "package_c/" {
      ClassE: "ClassE <<dataclass>>" {
        shape: class
      }
    }

    # ═════════════════════════════════════════════
    #  Relationships
    # ═════════════════════════════════════════════

    # --- internal ---
    pkg_a.ClassA -> pkg_a.ClassB: role { class: composition }

    # --- cross-package ---
    pkg_b.sub_pkg.ClassC -> pkg_a.ClassA: reads { class: dependency }
    pkg_b.impl_pkg.ClassD -> pkg_a.ClassB: uses { class: dependency }
    pkg_b.impl_pkg.ClassD -> pkg_c.ClassE: creates { class: composition }
    pkg_c.ClassE -> pkg_a.ClassA: ref { class: composition }
""")


# ---------------------------------------------------------------------------
# parse_packages
# ---------------------------------------------------------------------------


class TestParsePackages:
    def test_finds_all_top_level_containers(self) -> None:
        packages = parse_packages(SAMPLE_D2.splitlines())
        ids = [p.id for p in packages]
        assert ids == ["pkg_a", "pkg_b", "pkg_c"]

    def test_extracts_labels(self) -> None:
        packages = parse_packages(SAMPLE_D2.splitlines())
        labels = {p.id: p.label for p in packages}
        assert labels["pkg_a"] == "package_a/"
        assert labels["pkg_b"] == "package_b/"

    def test_collects_member_names(self) -> None:
        packages = parse_packages(SAMPLE_D2.splitlines())
        pkg_a = next(p for p in packages if p.id == "pkg_a")
        assert pkg_a.members == ["ClassA", "ClassB"]

    def test_collects_nested_members(self) -> None:
        packages = parse_packages(SAMPLE_D2.splitlines())
        pkg_b = next(p for p in packages if p.id == "pkg_b")
        # sub_pkg and impl_pkg are sub-containers ending in _pkg — filtered out.
        # ClassC and ClassD are the actual members.
        assert "ClassC" in pkg_b.members
        assert "ClassD" in pkg_b.members

    def test_filters_sub_packages(self) -> None:
        packages = parse_packages(SAMPLE_D2.splitlines())
        pkg_b = next(p for p in packages if p.id == "pkg_b")
        assert "sub_pkg" not in pkg_b.members
        assert "impl_pkg" not in pkg_b.members

    def test_empty_input(self) -> None:
        assert parse_packages([]) == []


# ---------------------------------------------------------------------------
# parse_relationships
# ---------------------------------------------------------------------------


class TestParseRelationships:
    def test_finds_all_relationships(self) -> None:
        rels = parse_relationships(SAMPLE_D2.splitlines())
        assert len(rels) == 5

    def test_extracts_labels_and_classes(self) -> None:
        rels = parse_relationships(SAMPLE_D2.splitlines())
        first = rels[0]
        assert first.source == "pkg_a.ClassA"
        assert first.target == "pkg_a.ClassB"
        assert first.label == "role"
        assert first.style_class == "composition"

    def test_only_parses_after_relationships_header(self) -> None:
        # Lines before the Relationships header should not be parsed
        d2 = dedent("""\
            pkg_a.X -> pkg_b.Y: before_header { class: composition }

            # Relationships

            pkg_a.X -> pkg_b.Y: after_header { class: composition }
        """)
        rels = parse_relationships(d2.splitlines())
        assert len(rels) == 1
        assert rels[0].label == "after_header"

    def test_empty_input(self) -> None:
        assert parse_relationships([]) == []


# ---------------------------------------------------------------------------
# resolve_package
# ---------------------------------------------------------------------------


class TestResolvePackage:
    def test_resolves_first_segment(self) -> None:
        pkg_ids = {"pkg_a", "pkg_b"}
        assert resolve_package("pkg_a.ClassA", pkg_ids) == "pkg_a"

    def test_resolves_deeply_nested(self) -> None:
        pkg_ids = {"pkg_b"}
        assert resolve_package("pkg_b.sub_pkg.ClassC", pkg_ids) == "pkg_b"

    def test_returns_none_for_unknown(self) -> None:
        pkg_ids = {"pkg_a"}
        assert resolve_package("unknown.ClassX", pkg_ids) is None


# ---------------------------------------------------------------------------
# build_overview_arrows
# ---------------------------------------------------------------------------


class TestBuildOverviewArrows:
    def test_excludes_intra_package(self) -> None:
        rels = parse_relationships(SAMPLE_D2.splitlines())
        pkg_ids = {"pkg_a", "pkg_b", "pkg_c"}
        arrows = build_overview_arrows(rels, pkg_ids)
        # pkg_a.ClassA -> pkg_a.ClassB is intra-package, should be excluded
        sources_targets = [(a.source_pkg, a.target_pkg) for a in arrows]
        assert ("pkg_a", "pkg_a") not in sources_targets

    def test_deduplicates_same_package_pair(self) -> None:
        rels = parse_relationships(SAMPLE_D2.splitlines())
        pkg_ids = {"pkg_a", "pkg_b", "pkg_c"}
        arrows = build_overview_arrows(rels, pkg_ids)
        # pkg_b -> pkg_a has two underlying relationships (ClassC->ClassA, ClassD->ClassB)
        pkg_b_to_a = [
            a for a in arrows if a.source_pkg == "pkg_b" and a.target_pkg == "pkg_a"
        ]
        assert len(pkg_b_to_a) == 1

    def test_collects_labels(self) -> None:
        rels = parse_relationships(SAMPLE_D2.splitlines())
        pkg_ids = {"pkg_a", "pkg_b", "pkg_c"}
        arrows = build_overview_arrows(rels, pkg_ids)
        pkg_b_to_a = next(
            a for a in arrows if a.source_pkg == "pkg_b" and a.target_pkg == "pkg_a"
        )
        assert "reads" in pkg_b_to_a.labels
        assert "uses" in pkg_b_to_a.labels

    def test_arrow_count(self) -> None:
        rels = parse_relationships(SAMPLE_D2.splitlines())
        pkg_ids = {"pkg_a", "pkg_b", "pkg_c"}
        arrows = build_overview_arrows(rels, pkg_ids)
        # Expected: pkg_b->pkg_a, pkg_b->pkg_c, pkg_c->pkg_a = 3 arrows
        assert len(arrows) == 3

    def test_sorted_output(self) -> None:
        rels = parse_relationships(SAMPLE_D2.splitlines())
        pkg_ids = {"pkg_a", "pkg_b", "pkg_c"}
        arrows = build_overview_arrows(rels, pkg_ids)
        keys = [(a.source_pkg, a.target_pkg) for a in arrows]
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# generate_overview_d2
# ---------------------------------------------------------------------------


class TestGenerateOverviewD2:
    def test_contains_direction(self) -> None:
        packages = parse_packages(SAMPLE_D2.splitlines())
        rels = parse_relationships(SAMPLE_D2.splitlines())
        pkg_ids = {p.id for p in packages}
        arrows = build_overview_arrows(rels, pkg_ids)
        output = generate_overview_d2(packages, arrows)
        assert "direction: down" in output

    def test_contains_all_packages(self) -> None:
        packages = parse_packages(SAMPLE_D2.splitlines())
        rels = parse_relationships(SAMPLE_D2.splitlines())
        pkg_ids = {p.id for p in packages}
        arrows = build_overview_arrows(rels, pkg_ids)
        output = generate_overview_d2(packages, arrows)
        for pkg in packages:
            assert f'{pkg.id}: "{pkg.label}"' in output

    def test_contains_tooltips(self) -> None:
        packages = parse_packages(SAMPLE_D2.splitlines())
        rels = parse_relationships(SAMPLE_D2.splitlines())
        pkg_ids = {p.id for p in packages}
        arrows = build_overview_arrows(rels, pkg_ids)
        output = generate_overview_d2(packages, arrows)
        assert "ClassA, ClassB" in output

    def test_contains_arrows(self) -> None:
        packages = parse_packages(SAMPLE_D2.splitlines())
        rels = parse_relationships(SAMPLE_D2.splitlines())
        pkg_ids = {p.id for p in packages}
        arrows = build_overview_arrows(rels, pkg_ids)
        output = generate_overview_d2(packages, arrows)
        assert "pkg_b -> pkg_a" in output
        assert "pkg_b -> pkg_c" in output

    def test_contains_link(self) -> None:
        packages = parse_packages(SAMPLE_D2.splitlines())
        rels = parse_relationships(SAMPLE_D2.splitlines())
        pkg_ids = {p.id for p in packages}
        arrows = build_overview_arrows(rels, pkg_ids)
        output = generate_overview_d2(packages, arrows)
        assert 'link: "diagram.svg"' in output


# ---------------------------------------------------------------------------
# End-to-end with real diagram.d2
# ---------------------------------------------------------------------------

_REAL_DIAGRAM = Path(__file__).resolve().parents[2] / "docs" / "diagram.d2"


@pytest.mark.skipif(not _REAL_DIAGRAM.exists(), reason="diagram.d2 not found")
class TestEndToEnd:
    def test_package_count(self) -> None:
        lines = _REAL_DIAGRAM.read_text().splitlines()
        packages = parse_packages(lines)
        # Current diagram has 13 top-level containers
        assert len(packages) == 13

    def test_arrow_count_range(self) -> None:
        lines = _REAL_DIAGRAM.read_text().splitlines()
        packages = parse_packages(lines)
        pkg_ids = {p.id for p in packages}
        rels = parse_relationships(lines)
        arrows = build_overview_arrows(rels, pkg_ids)
        # Expect roughly 15-25 deduplicated cross-package arrows
        assert 10 <= len(arrows) <= 30

    def test_no_intra_package_arrows(self) -> None:
        lines = _REAL_DIAGRAM.read_text().splitlines()
        packages = parse_packages(lines)
        pkg_ids = {p.id for p in packages}
        rels = parse_relationships(lines)
        arrows = build_overview_arrows(rels, pkg_ids)
        for arrow in arrows:
            assert arrow.source_pkg != arrow.target_pkg

    def test_output_is_valid_d2_structure(self) -> None:
        lines = _REAL_DIAGRAM.read_text().splitlines()
        packages = parse_packages(lines)
        pkg_ids = {p.id for p in packages}
        rels = parse_relationships(lines)
        arrows = build_overview_arrows(rels, pkg_ids)
        output = generate_overview_d2(packages, arrows)
        # Basic structural checks
        assert output.startswith("direction: down")
        assert "classes:" in output
        assert "->" in output
        # Every package should appear
        for pkg in packages:
            assert pkg.id in output


# ---------------------------------------------------------------------------
# generate_overview_html
# ---------------------------------------------------------------------------

_REAL_OVERVIEW_SVG = (
    Path(__file__).resolve().parents[2] / "docs" / "diagram-overview.svg"
)


@pytest.mark.skipif(
    not _REAL_OVERVIEW_SVG.exists(), reason="diagram-overview.svg not found"
)
class TestGenerateOverviewHtml:
    def test_inlines_svg(self) -> None:
        html = generate_overview_html(_REAL_OVERVIEW_SVG, "diagram.svg")
        assert "<svg" in html
        assert "</svg>" in html

    def test_contains_tooltip_js(self) -> None:
        html = generate_overview_html(_REAL_OVERVIEW_SVG, "diagram.svg")
        assert "addEventListener" in html
        assert 'id="tooltip"' in html

    def test_contains_detail_link(self) -> None:
        html = generate_overview_html(_REAL_OVERVIEW_SVG, "diagram.svg")
        assert 'href="diagram.svg"' in html

    def test_is_valid_html(self) -> None:
        html = generate_overview_html(_REAL_OVERVIEW_SVG, "diagram.svg")
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html
