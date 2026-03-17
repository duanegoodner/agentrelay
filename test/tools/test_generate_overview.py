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
build_midlevel_arrows = generate_overview_mod.build_midlevel_arrows
classify_relationships = generate_overview_mod.classify_relationships
generate_midlevel_d2 = generate_overview_mod.generate_midlevel_d2
generate_midlevel_html = generate_overview_mod.generate_midlevel_html
parse_package_details = generate_overview_mod.parse_package_details
extract_package_d2_blocks = generate_overview_mod.extract_package_d2_blocks
generate_package_d2_files = generate_overview_mod.generate_package_d2_files
render_package_svgs = generate_overview_mod.render_package_svgs
MidlevelArrow = generate_overview_mod.MidlevelArrow
Package = generate_overview_mod.Package
PackageDetail = generate_overview_mod.PackageDetail
ClassInfo = generate_overview_mod.ClassInfo
SubPackageDetail = generate_overview_mod.SubPackageDetail
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


# ---------------------------------------------------------------------------
# parse_package_details
# ---------------------------------------------------------------------------


class TestParsePackageDetails:
    def test_finds_all_packages(self) -> None:
        details = parse_package_details(SAMPLE_D2.splitlines())
        ids = [p.id for p in details]
        assert ids == ["pkg_a", "pkg_b", "pkg_c"]

    def test_extracts_direct_classes(self) -> None:
        details = parse_package_details(SAMPLE_D2.splitlines())
        pkg_a = next(p for p in details if p.id == "pkg_a")
        class_ids = [c.id for c in pkg_a.direct_classes]
        assert "ClassA" in class_ids
        assert "ClassB" in class_ids

    def test_extracts_sub_packages(self) -> None:
        details = parse_package_details(SAMPLE_D2.splitlines())
        pkg_b = next(p for p in details if p.id == "pkg_b")
        sub_ids = [s.id for s in pkg_b.sub_packages]
        assert "sub_pkg" in sub_ids
        assert "impl_pkg" in sub_ids

    def test_extracts_classes_in_sub_packages(self) -> None:
        details = parse_package_details(SAMPLE_D2.splitlines())
        pkg_b = next(p for p in details if p.id == "pkg_b")
        sub_pkg = next(s for s in pkg_b.sub_packages if s.id == "sub_pkg")
        class_ids = [c.id for c in sub_pkg.classes]
        assert "ClassC" in class_ids

    def test_extracts_class_members(self) -> None:
        details = parse_package_details(SAMPLE_D2.splitlines())
        pkg_a = next(p for p in details if p.id == "pkg_a")
        class_a = next(c for c in pkg_a.direct_classes if c.id == "ClassA")
        assert "field1: str" in class_a.members

    def test_extracts_class_labels(self) -> None:
        details = parse_package_details(SAMPLE_D2.splitlines())
        pkg_a = next(p for p in details if p.id == "pkg_a")
        class_b = next(c for c in pkg_a.direct_classes if c.id == "ClassB")
        assert "<<enum>>" in class_b.display_label

    def test_collects_enum_values(self) -> None:
        details = parse_package_details(SAMPLE_D2.splitlines())
        pkg_a = next(p for p in details if p.id == "pkg_a")
        class_b = next(c for c in pkg_a.direct_classes if c.id == "ClassB")
        assert "VAL1" in class_b.members
        assert "VAL2" in class_b.members

    def test_collects_methods(self) -> None:
        details = parse_package_details(SAMPLE_D2.splitlines())
        pkg_b = next(p for p in details if p.id == "pkg_b")
        sub_pkg = next(s for s in pkg_b.sub_packages if s.id == "sub_pkg")
        class_c = next(c for c in sub_pkg.classes if c.id == "ClassC")
        assert "+method(): void" in class_c.members

    def test_empty_input(self) -> None:
        assert parse_package_details([]) == []


@pytest.mark.skipif(not _REAL_DIAGRAM.exists(), reason="diagram.d2 not found")
class TestParsePackageDetailsEndToEnd:
    def test_all_packages_have_content(self) -> None:
        lines = _REAL_DIAGRAM.read_text().splitlines()
        details = parse_package_details(lines)
        assert len(details) == 13
        for pkg in details:
            total = len(pkg.direct_classes) + sum(
                len(s.classes) for s in pkg.sub_packages
            )
            assert total > 0, f"Package {pkg.id} has no classes"

    def test_known_class_has_members(self) -> None:
        lines = _REAL_DIAGRAM.read_text().splitlines()
        details = parse_package_details(lines)
        task_py = next(p for p in details if p.id == "task_py")
        task_cls = next(c for c in task_py.direct_classes if c.id == "Task")
        assert len(task_cls.members) > 3  # Task has many fields


# ---------------------------------------------------------------------------
# classify_relationships
# ---------------------------------------------------------------------------


class TestClassifyRelationships:
    def test_splits_intra_and_cross(self) -> None:
        rels = parse_relationships(SAMPLE_D2.splitlines())
        pkg_ids = {"pkg_a", "pkg_b", "pkg_c"}
        intra, cross = classify_relationships(rels, pkg_ids)
        # pkg_a.ClassA -> pkg_a.ClassB is intra
        assert len(intra) == 1
        assert intra[0].source == "pkg_a.ClassA"
        # The rest are cross-package
        assert len(cross) == 4

    def test_empty_input(self) -> None:
        intra, cross = classify_relationships([], {"pkg_a"})
        assert intra == []
        assert cross == []


# ---------------------------------------------------------------------------
# build_midlevel_arrows
# ---------------------------------------------------------------------------


class TestBuildMidlevelArrows:
    def test_excludes_intra_package(self) -> None:
        rels = parse_relationships(SAMPLE_D2.splitlines())
        pkg_ids = {"pkg_a", "pkg_b", "pkg_c"}
        arrows = build_midlevel_arrows(rels, pkg_ids)
        pairs = [(a.source_pkg, a.target_pkg) for a in arrows]
        assert ("pkg_a", "pkg_a") not in pairs

    def test_collects_class_details(self) -> None:
        rels = parse_relationships(SAMPLE_D2.splitlines())
        pkg_ids = {"pkg_a", "pkg_b", "pkg_c"}
        arrows = build_midlevel_arrows(rels, pkg_ids)
        pkg_b_to_a = next(
            a for a in arrows if a.source_pkg == "pkg_b" and a.target_pkg == "pkg_a"
        )
        # Should have two class-level details
        assert len(pkg_b_to_a.details) == 2
        assert any("ClassC" in d and "ClassA" in d for d in pkg_b_to_a.details)
        assert any("ClassD" in d and "ClassB" in d for d in pkg_b_to_a.details)

    def test_details_include_labels(self) -> None:
        rels = parse_relationships(SAMPLE_D2.splitlines())
        pkg_ids = {"pkg_a", "pkg_b", "pkg_c"}
        arrows = build_midlevel_arrows(rels, pkg_ids)
        pkg_b_to_a = next(
            a for a in arrows if a.source_pkg == "pkg_b" and a.target_pkg == "pkg_a"
        )
        assert any("(reads)" in d for d in pkg_b_to_a.details)
        assert any("(uses)" in d for d in pkg_b_to_a.details)

    def test_arrow_count(self) -> None:
        rels = parse_relationships(SAMPLE_D2.splitlines())
        pkg_ids = {"pkg_a", "pkg_b", "pkg_c"}
        arrows = build_midlevel_arrows(rels, pkg_ids)
        assert len(arrows) == 3

    def test_sorted_output(self) -> None:
        rels = parse_relationships(SAMPLE_D2.splitlines())
        pkg_ids = {"pkg_a", "pkg_b", "pkg_c"}
        arrows = build_midlevel_arrows(rels, pkg_ids)
        keys = [(a.source_pkg, a.target_pkg) for a in arrows]
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# generate_midlevel_d2
# ---------------------------------------------------------------------------


class TestGenerateMidlevelD2:
    def test_preserves_package_definitions(self) -> None:
        lines = SAMPLE_D2.splitlines()
        rels = parse_relationships(lines)
        pkgs = parse_packages(lines)
        pkg_ids = {p.id for p in pkgs}
        output = generate_midlevel_d2(lines, rels, pkg_ids)
        # All package definitions should be present
        assert 'pkg_a: "package_a/"' in output
        assert 'pkg_b: "package_b/"' in output
        assert "ClassA" in output
        assert "ClassC" in output

    def test_keeps_intra_package_arrows(self) -> None:
        lines = SAMPLE_D2.splitlines()
        rels = parse_relationships(lines)
        pkgs = parse_packages(lines)
        pkg_ids = {p.id for p in pkgs}
        output = generate_midlevel_d2(lines, rels, pkg_ids)
        assert "pkg_a.ClassA -> pkg_a.ClassB" in output

    def test_collapses_cross_package_arrows(self) -> None:
        lines = SAMPLE_D2.splitlines()
        rels = parse_relationships(lines)
        pkgs = parse_packages(lines)
        pkg_ids = {p.id for p in pkgs}
        output = generate_midlevel_d2(lines, rels, pkg_ids)
        # Should have collapsed arrows like: pkg_b -> pkg_a: "2 connections"
        assert 'pkg_b -> pkg_a: "2 connections"' in output

    def test_no_original_cross_package_arrows(self) -> None:
        lines = SAMPLE_D2.splitlines()
        rels = parse_relationships(lines)
        pkgs = parse_packages(lines)
        pkg_ids = {p.id for p in pkgs}
        output = generate_midlevel_d2(lines, rels, pkg_ids)
        # Original cross-package arrows should NOT appear
        assert "pkg_b.sub_pkg.ClassC -> pkg_a.ClassA" not in output
        assert "pkg_b.impl_pkg.ClassD -> pkg_a.ClassB" not in output

    def test_collapsed_arrows_have_tooltip(self) -> None:
        lines = SAMPLE_D2.splitlines()
        rels = parse_relationships(lines)
        pkgs = parse_packages(lines)
        pkg_ids = {p.id for p in pkgs}
        output = generate_midlevel_d2(lines, rels, pkg_ids)
        assert "tooltip:" in output

    def test_contains_relationships_header(self) -> None:
        lines = SAMPLE_D2.splitlines()
        rels = parse_relationships(lines)
        pkgs = parse_packages(lines)
        pkg_ids = {p.id for p in pkgs}
        output = generate_midlevel_d2(lines, rels, pkg_ids)
        assert "Relationships" in output


# ---------------------------------------------------------------------------
# End-to-end midlevel with real diagram.d2
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _REAL_DIAGRAM.exists(), reason="diagram.d2 not found")
class TestMidlevelEndToEnd:
    def test_preserves_all_packages(self) -> None:
        lines = _REAL_DIAGRAM.read_text().splitlines()
        packages = parse_packages(lines)
        pkg_ids = {p.id for p in packages}
        rels = parse_relationships(lines)
        output = generate_midlevel_d2(lines, rels, pkg_ids)
        for pkg in packages:
            assert pkg.id in output

    def test_keeps_class_definitions(self) -> None:
        lines = _REAL_DIAGRAM.read_text().splitlines()
        packages = parse_packages(lines)
        pkg_ids = {p.id for p in packages}
        rels = parse_relationships(lines)
        output = generate_midlevel_d2(lines, rels, pkg_ids)
        # Spot-check some classes that should be preserved
        assert "Task:" in output or "Task " in output
        assert "Orchestrator:" in output or "Orchestrator " in output

    def test_no_cross_package_class_arrows(self) -> None:
        """No original cross-package dotted arrows should remain."""
        lines = _REAL_DIAGRAM.read_text().splitlines()
        packages = parse_packages(lines)
        pkg_ids = {p.id for p in packages}
        rels = parse_relationships(lines)
        output = generate_midlevel_d2(lines, rels, pkg_ids)
        output_lines = output.splitlines()
        # After the "cross-package (collapsed)" comment, all arrows should
        # be pkg -> pkg format (no dots in source/target).
        in_collapsed = False
        for line in output_lines:
            if "cross-package (collapsed)" in line:
                in_collapsed = True
                continue
            if in_collapsed and "->" in line:
                src = line.split("->")[0].strip()
                assert "." not in src, f"Unexpected dotted arrow in collapsed: {line}"

    def test_collapsed_arrow_count(self) -> None:
        lines = _REAL_DIAGRAM.read_text().splitlines()
        packages = parse_packages(lines)
        pkg_ids = {p.id for p in packages}
        rels = parse_relationships(lines)
        arrows = build_midlevel_arrows(rels, pkg_ids)
        # Should have roughly the same count as overview arrows
        assert 10 <= len(arrows) <= 30


# ---------------------------------------------------------------------------
# generate_midlevel_html
# ---------------------------------------------------------------------------


class TestGenerateMidlevelHtml:
    def test_contains_tooltip_json(self) -> None:
        arrows = [
            MidlevelArrow(
                source_pkg="pkg_a",
                target_pkg="pkg_b",
                details=["ClassX \u2192 ClassY (uses)"],
                style_classes={"dependency"},
            )
        ]
        # Create a minimal SVG file in tmp
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".svg", mode="w", delete=False) as f:
            f.write("<svg></svg>")
            svg_path = Path(f.name)
        try:
            html = generate_midlevel_html(svg_path, "diagram.svg", arrows)
            assert "TOOLTIPS" in html
            assert "ClassX" in html
            assert "ClassY" in html
        finally:
            svg_path.unlink()

    def test_is_valid_html(self) -> None:
        arrows = []
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".svg", mode="w", delete=False) as f:
            f.write("<svg></svg>")
            svg_path = Path(f.name)
        try:
            html = generate_midlevel_html(svg_path, "diagram.svg", arrows)
            assert html.startswith("<!DOCTYPE html>")
            assert "</html>" in html
        finally:
            svg_path.unlink()

    def test_contains_detail_link(self) -> None:
        arrows = []
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".svg", mode="w", delete=False) as f:
            f.write("<svg></svg>")
            svg_path = Path(f.name)
        try:
            html = generate_midlevel_html(svg_path, "diagram.svg", arrows)
            assert 'href="diagram.svg"' in html
        finally:
            svg_path.unlink()


# ---------------------------------------------------------------------------
# extract_package_d2_blocks
# ---------------------------------------------------------------------------


class TestExtractPackageD2Blocks:
    def test_extracts_all_packages(self) -> None:
        blocks = extract_package_d2_blocks(SAMPLE_D2.splitlines())
        assert set(blocks.keys()) == {"pkg_a", "pkg_b", "pkg_c"}

    def test_block_contains_classes(self) -> None:
        blocks = extract_package_d2_blocks(SAMPLE_D2.splitlines())
        pkg_a_text = "\n".join(blocks["pkg_a"])
        assert "ClassA" in pkg_a_text
        assert "ClassB" in pkg_a_text

    def test_block_is_unwrapped(self) -> None:
        """Inner lines should be dedented — no leading 2-space indent."""
        blocks = extract_package_d2_blocks(SAMPLE_D2.splitlines())
        pkg_a_lines = blocks["pkg_a"]
        # First non-blank line should start without indent (class definition).
        first_content = next(l for l in pkg_a_lines if l.strip())
        assert not first_content.startswith("  ") or first_content.startswith("  shape")

    def test_block_excludes_outer_container_line(self) -> None:
        blocks = extract_package_d2_blocks(SAMPLE_D2.splitlines())
        for pkg_id, lines in blocks.items():
            # The outer container line like `pkg_a: "package_a/" {` must not appear.
            assert not any(f'{pkg_id}: "' in line for line in lines)

    def test_nested_sub_packages_present(self) -> None:
        blocks = extract_package_d2_blocks(SAMPLE_D2.splitlines())
        pkg_b_text = "\n".join(blocks["pkg_b"])
        assert "sub_pkg" in pkg_b_text
        assert "impl_pkg" in pkg_b_text
        assert "ClassC" in pkg_b_text
        assert "ClassD" in pkg_b_text

    def test_empty_input(self) -> None:
        assert extract_package_d2_blocks([]) == {}


@pytest.mark.skipif(not _REAL_DIAGRAM.exists(), reason="diagram.d2 not found")
class TestExtractPackageD2BlocksEndToEnd:
    def test_extracts_all_13_packages(self) -> None:
        lines = _REAL_DIAGRAM.read_text().splitlines()
        blocks = extract_package_d2_blocks(lines)
        assert len(blocks) == 13

    def test_each_block_has_content(self) -> None:
        lines = _REAL_DIAGRAM.read_text().splitlines()
        blocks = extract_package_d2_blocks(lines)
        for pkg_id, block_lines in blocks.items():
            assert len(block_lines) > 0, f"Empty block for {pkg_id}"

    def test_known_package_contains_class(self) -> None:
        lines = _REAL_DIAGRAM.read_text().splitlines()
        blocks = extract_package_d2_blocks(lines)
        task_py_text = "\n".join(blocks["task_py"])
        assert "Task:" in task_py_text or "Task " in task_py_text
        assert "AgentRole" in task_py_text


# ---------------------------------------------------------------------------
# generate_package_d2_files
# ---------------------------------------------------------------------------


class TestGeneratePackageD2Files:
    def test_generates_files_for_all_packages(self, tmp_path: Path) -> None:
        d2_input = tmp_path / "input.d2"
        d2_input.write_text(SAMPLE_D2)
        out_dir = tmp_path / "pkg-detail"
        files = generate_package_d2_files(d2_input, out_dir)
        assert len(files) == 3
        names = {f.stem for f in files}
        assert names == {"pkg_a", "pkg_b", "pkg_c"}

    def test_generated_file_contains_classes(self, tmp_path: Path) -> None:
        d2_input = tmp_path / "input.d2"
        d2_input.write_text(SAMPLE_D2)
        out_dir = tmp_path / "pkg-detail"
        generate_package_d2_files(d2_input, out_dir)
        pkg_a_d2 = (out_dir / "pkg_a.d2").read_text()
        assert "ClassA" in pkg_a_d2
        assert "ClassB" in pkg_a_d2

    def test_includes_intra_package_relationships(self, tmp_path: Path) -> None:
        d2_input = tmp_path / "input.d2"
        d2_input.write_text(SAMPLE_D2)
        out_dir = tmp_path / "pkg-detail"
        generate_package_d2_files(d2_input, out_dir)
        pkg_a_d2 = (out_dir / "pkg_a.d2").read_text()
        # pkg_a has one intra relationship: ClassA -> ClassB
        assert "ClassA -> ClassB" in pkg_a_d2

    def test_excludes_cross_package_relationships(self, tmp_path: Path) -> None:
        d2_input = tmp_path / "input.d2"
        d2_input.write_text(SAMPLE_D2)
        out_dir = tmp_path / "pkg-detail"
        generate_package_d2_files(d2_input, out_dir)
        pkg_b_d2 = (out_dir / "pkg_b.d2").read_text()
        # pkg_b has no intra-package relationships in the sample
        assert "# Relationships" not in pkg_b_d2

    def test_strips_package_prefix_from_relationships(self, tmp_path: Path) -> None:
        d2_input = tmp_path / "input.d2"
        d2_input.write_text(SAMPLE_D2)
        out_dir = tmp_path / "pkg-detail"
        generate_package_d2_files(d2_input, out_dir)
        pkg_a_d2 = (out_dir / "pkg_a.d2").read_text()
        # Should be "ClassA -> ClassB" not "pkg_a.ClassA -> pkg_a.ClassB"
        assert "pkg_a.ClassA" not in pkg_a_d2

    def test_includes_style_classes(self, tmp_path: Path) -> None:
        d2_input = tmp_path / "input.d2"
        d2_input.write_text(SAMPLE_D2)
        out_dir = tmp_path / "pkg-detail"
        generate_package_d2_files(d2_input, out_dir)
        pkg_a_d2 = (out_dir / "pkg_a.d2").read_text()
        assert "classes:" in pkg_a_d2


# ---------------------------------------------------------------------------
# render_package_svgs (mocked subprocess)
# ---------------------------------------------------------------------------


class TestRenderPackageSvgs:
    def test_renders_all_packages(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import subprocess as sp

        # Create fake D2 files.
        d2_a = tmp_path / "pkg_a.d2"
        d2_b = tmp_path / "pkg_b.d2"
        d2_a.write_text("A: {}")
        d2_b.write_text("B: {}")

        def fake_run(cmd: list[str], **_kwargs: object) -> sp.CompletedProcess[str]:
            # Write a fake SVG to the output path.
            out_path = cmd[-1]  # Last arg is SVG output path
            Path(out_path).write_text(f"<svg>fake for {Path(cmd[-2]).stem}</svg>")
            return sp.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(generate_overview_mod.subprocess, "run", fake_run)

        result = render_package_svgs([d2_a, d2_b])
        assert set(result.keys()) == {"pkg_a", "pkg_b"}
        assert "<svg>" in result["pkg_a"]
        assert "<svg>" in result["pkg_b"]

    def test_skips_failed_renders(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import subprocess as sp

        d2_a = tmp_path / "pkg_a.d2"
        d2_a.write_text("A: {}")

        def fake_run(cmd: list[str], **_kwargs: object) -> sp.CompletedProcess[str]:
            return sp.CompletedProcess(cmd, 1, "", "error rendering")

        monkeypatch.setattr(generate_overview_mod.subprocess, "run", fake_run)

        result = render_package_svgs([d2_a])
        assert result == {}


# ---------------------------------------------------------------------------
# generate_overview_html with package SVGs
# ---------------------------------------------------------------------------


class TestGenerateOverviewHtmlWithPopups:
    def test_enables_popup_mode(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".svg", mode="w", delete=False) as f:
            f.write("<svg></svg>")
            svg_path = Path(f.name)
        try:
            html = generate_overview_html(
                svg_path,
                "diagram.svg",
                package_svgs={"pkg_a": "<svg>mini A</svg>"},
            )
            assert "USE_POPUPS = true" in html
            assert "popup-panel" in html
            assert "popup-overlay" in html
        finally:
            svg_path.unlink()

    def test_embeds_package_svgs_as_base64(self) -> None:
        import base64
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".svg", mode="w", delete=False) as f:
            f.write("<svg></svg>")
            svg_path = Path(f.name)
        try:
            svg_content = "<svg>mini A</svg>"
            html = generate_overview_html(
                svg_path,
                "diagram.svg",
                package_svgs={"pkg_a": svg_content},
            )
            expected_b64 = base64.b64encode(svg_content.encode()).decode()
            assert expected_b64 in html
        finally:
            svg_path.unlink()

    def test_falls_back_to_hover_without_svgs(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".svg", mode="w", delete=False) as f:
            f.write("<svg></svg>")
            svg_path = Path(f.name)
        try:
            html = generate_overview_html(svg_path, "diagram.svg")
            assert "USE_POPUPS = false" in html
        finally:
            svg_path.unlink()

    def test_click_instruction_in_subtitle(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".svg", mode="w", delete=False) as f:
            f.write("<svg></svg>")
            svg_path = Path(f.name)
        try:
            html = generate_overview_html(
                svg_path,
                "diagram.svg",
                package_svgs={"pkg_a": "<svg></svg>"},
            )
            assert "Click" in html
        finally:
            svg_path.unlink()


# ---------------------------------------------------------------------------
# generate_midlevel_grid_html
# ---------------------------------------------------------------------------

generate_midlevel_grid_html = generate_overview_mod.generate_midlevel_grid_html


class TestGenerateMidlevelGridHtml:
    """Tests for CSS-grid-based midlevel HTML generation."""

    def _make_packages(self):
        return [
            Package(id="pkg_a", label="pkg_a/", members=["ClassA"]),
            Package(id="pkg_b", label="pkg_b/", members=["ClassB"]),
        ]

    def _make_arrows(self):
        return [
            MidlevelArrow(
                source_pkg="pkg_a",
                target_pkg="pkg_b",
                details=["ClassA -> ClassB : uses"],
            ),
        ]

    def _make_svgs(self):
        return {
            "pkg_a": '<svg xmlns="http://www.w3.org/2000/svg"><text>A</text></svg>',
            "pkg_b": '<svg xmlns="http://www.w3.org/2000/svg"><text>B</text></svg>',
        }

    def test_generates_valid_html(self):
        html = generate_midlevel_grid_html(
            self._make_packages(),
            self._make_svgs(),
            self._make_arrows(),
            "diagram.svg",
        )
        assert "<!DOCTYPE html>" in html
        assert "Mid-Level Diagram" in html

    def test_embeds_package_svgs_as_base64(self):
        html = generate_midlevel_grid_html(
            self._make_packages(),
            self._make_svgs(),
            self._make_arrows(),
            "diagram.svg",
        )
        assert "data:image/svg+xml;base64," in html

    def test_includes_package_cards(self):
        html = generate_midlevel_grid_html(
            self._make_packages(),
            self._make_svgs(),
            self._make_arrows(),
            "diagram.svg",
        )
        assert 'id="pkg-pkg_a"' in html
        assert 'id="pkg-pkg_b"' in html

    def test_includes_cross_package_connections_table(self):
        html = generate_midlevel_grid_html(
            self._make_packages(),
            self._make_svgs(),
            self._make_arrows(),
            "diagram.svg",
        )
        assert "Cross-Package Connections" in html
        assert "ClassA -&gt; ClassB : uses" in html

    def test_includes_per_package_connection_details(self):
        html = generate_midlevel_grid_html(
            self._make_packages(),
            self._make_svgs(),
            self._make_arrows(),
            "diagram.svg",
        )
        assert "1 cross-package connection" in html

    def test_skips_packages_without_svgs(self):
        packages = self._make_packages()
        svgs = {"pkg_a": "<svg></svg>"}  # Only pkg_a has SVG
        html = generate_midlevel_grid_html(
            packages, svgs, self._make_arrows(), "diagram.svg"
        )
        assert 'id="pkg-pkg_a"' in html
        assert 'id="pkg-pkg_b"' not in html

    def test_detail_svg_link(self):
        html = generate_midlevel_grid_html(
            self._make_packages(),
            self._make_svgs(),
            self._make_arrows(),
            "diagram.svg",
        )
        assert 'href="diagram.svg"' in html
