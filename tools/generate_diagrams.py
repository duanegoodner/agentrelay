"""Generate filtered diagram variants from the authoritative detailed diagram.

Applies composable filters from :mod:`d2_filters` to produce diagram variants:

- **no-private**: strips ``_``-prefixed nodes and their arrows.
- **no-impl**: collapses ``*_impl_pkg`` contents to a count placeholder.
- **standard**: both filters applied (cleanest view).

The detailed diagram (``diagram-detailed.d2``) is the single source of truth
and is never modified.

Usage::

    python tools/generate_diagrams.py                     # all variants
    python tools/generate_diagrams.py --variant standard   # just one
    python tools/generate_diagrams.py --list               # list available variants
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from tools.d2_filters import collapse_impl_packages, filter_private_nodes

# ---------------------------------------------------------------------------
# Variant definitions
# ---------------------------------------------------------------------------

FilterFn = Callable[[list[str]], list[str]]


@dataclass(frozen=True)
class DiagramVariant:
    """A named diagram variant with its filter chain."""

    name: str
    description: str
    filters: tuple[FilterFn, ...] = field(default_factory=tuple)


VARIANTS: dict[str, DiagramVariant] = {
    "no-private": DiagramVariant(
        name="no-private",
        description="Public API types with full implementation detail",
        filters=(filter_private_nodes,),
    ),
    "no-impl": DiagramVariant(
        name="no-impl",
        description="All types with collapsed implementations",
        filters=(collapse_impl_packages,),
    ),
    "standard": DiagramVariant(
        name="standard",
        description="Public types with collapsed implementations (cleanest)",
        filters=(filter_private_nodes, collapse_impl_packages),
    ),
}


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def apply_filters(lines: list[str], filters: tuple[FilterFn, ...]) -> list[str]:
    """Apply a chain of filters to D2 source lines."""
    for f in filters:
        lines = f(lines)
    return lines


def generate_variant(
    input_path: Path,
    output_dir: Path,
    variant: DiagramVariant,
    preamble: list[str] | None = None,
) -> Path:
    """Generate a single diagram variant and return the output path.

    Args:
        input_path: Path to the source D2 file.
        output_dir: Directory for the output file.
        variant: Variant definition with filter chain.
        preamble: Optional D2 global lines (direction, font-size, etc.)
            prepended to the output. These are injected *before* the source
            content so they take effect as D2 defaults.
    """
    source = input_path.read_text()
    lines = source.splitlines()
    filtered = apply_filters(lines, variant.filters)
    if preamble:
        filtered = preamble + [""] + filtered
    output_path = output_dir / f"diagram-{variant.name}.d2"
    output_path.write_text("\n".join(filtered) + "\n")
    return output_path


def generate_all(
    input_path: Path,
    output_dir: Path,
    variant_names: list[str] | None = None,
    preamble: list[str] | None = None,
) -> list[Path]:
    """Generate diagram variants and return their output paths."""
    if variant_names is None:
        variant_names = list(VARIANTS.keys())

    paths: list[Path] = []
    for name in variant_names:
        variant = VARIANTS[name]
        path = generate_variant(input_path, output_dir, variant, preamble=preamble)
        paths.append(path)

    return paths


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate filtered diagram variants from diagram-detailed.d2.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("docs/diagram-detailed.d2"),
        help="Path to detailed diagram (default: docs/diagram-detailed.d2)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs"),
        help="Directory for output files (default: docs/)",
    )
    parser.add_argument(
        "--variant",
        choices=list(VARIANTS.keys()),
        action="append",
        dest="variants",
        help="Generate a specific variant (repeatable; default: all)",
    )
    parser.add_argument(
        "--preamble",
        action="append",
        dest="preamble",
        metavar="LINE",
        help='D2 global line to prepend (repeatable). Example: --preamble "direction: right"',
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available variants and exit.",
    )
    args = parser.parse_args(argv)

    if args.list:
        for name, variant in VARIANTS.items():
            print(f"  {name:15s} {variant.description}")
        return

    if not args.input.exists():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    paths = generate_all(
        args.input, args.output_dir, args.variants, preamble=args.preamble
    )
    for path in paths:
        print(f"Generated {path}")


if __name__ == "__main__":
    main()
