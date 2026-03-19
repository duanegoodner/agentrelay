"""Tests for tools/generate_diagrams.py — variant generation CLI."""

from __future__ import annotations

from pathlib import Path

from tools.generate_diagrams import VARIANTS, apply_filters, generate_variant

_REAL_DIAGRAM = Path("docs/diagrams/uml/diagram-detailed.d2")


class TestVariantConfig:
    def test_three_variants_defined(self) -> None:
        assert set(VARIANTS.keys()) == {"no-private", "no-impl", "standard"}

    def test_standard_has_both_filters(self) -> None:
        assert len(VARIANTS["standard"].filters) == 2

    def test_no_private_has_one_filter(self) -> None:
        assert len(VARIANTS["no-private"].filters) == 1

    def test_no_impl_has_one_filter(self) -> None:
        assert len(VARIANTS["no-impl"].filters) == 1


class TestApplyFilters:
    def test_empty_filters_returns_input(self) -> None:
        lines = ["a", "b", "c"]
        assert apply_filters(lines, ()) == lines

    def test_single_filter(self) -> None:
        def drop_b(lines: list[str]) -> list[str]:
            return [l for l in lines if l != "b"]

        assert apply_filters(["a", "b", "c"], (drop_b,)) == ["a", "c"]

    def test_filter_chain_order(self) -> None:
        def add_x(lines: list[str]) -> list[str]:
            return lines + ["x"]

        def add_y(lines: list[str]) -> list[str]:
            return lines + ["y"]

        result = apply_filters([], (add_x, add_y))
        assert result == ["x", "y"]


class TestGenerateVariant:
    def test_generates_output_file(self, tmp_path: Path) -> None:
        variant = VARIANTS["standard"]
        output = generate_variant(_REAL_DIAGRAM, tmp_path, variant)
        assert output.exists()
        assert output.name == "diagram-standard.d2"
        content = output.read_text()
        assert len(content) > 0

    def test_preamble_prepended(self, tmp_path: Path) -> None:
        variant = VARIANTS["standard"]
        preamble = ["direction: right", "**.style.font-size: 42"]
        output = generate_variant(_REAL_DIAGRAM, tmp_path, variant, preamble=preamble)
        lines = output.read_text().splitlines()
        assert lines[0] == "direction: right"
        assert lines[1] == "**.style.font-size: 42"
        assert lines[2] == ""  # blank separator

    def test_no_preamble_no_extra_lines(self, tmp_path: Path) -> None:
        variant = VARIANTS["standard"]
        output = generate_variant(_REAL_DIAGRAM, tmp_path, variant)
        first_line = output.read_text().splitlines()[0]
        assert "direction" not in first_line

    def test_all_variants_produce_different_sizes(self, tmp_path: Path) -> None:
        sizes: dict[str, int] = {}
        for name, variant in VARIANTS.items():
            output = generate_variant(_REAL_DIAGRAM, tmp_path, variant)
            sizes[name] = len(output.read_text().splitlines())

        detailed_size = len(_REAL_DIAGRAM.read_text().splitlines())

        # All variants should be smaller than detailed
        for name, size in sizes.items():
            assert size < detailed_size, f"{name} not smaller than detailed"

        # Standard (both filters) should be smallest
        assert sizes["standard"] < sizes["no-private"]
        assert sizes["standard"] < sizes["no-impl"]
