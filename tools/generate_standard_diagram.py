"""Generate a standard diagram by filtering private nodes from the detailed diagram.

Reads ``docs/diagram-detailed.d2`` and strips any node whose D2 identifier
starts with ``_`` (matching the Python private naming convention), along with
any relationship lines that reference such nodes. The result is written to
``docs/diagram-standard.d2``.

Usage::

    python tools/generate_standard_diagram.py
    python tools/generate_standard_diagram.py --input path/to/detail.d2 --output path/to/standard.d2
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Matches a node definition whose identifier starts with ``_``.
# Handles both nested (indented) and top-level definitions:
#   ``  _OrchestratorRun: "_OrchestratorRun <<internal>>" {``
#   ``  _validation: "_validation <<module>>" {``
_PRIVATE_NODE_RE = re.compile(r"^(\s*)_\w+\s*:")

# Matches a relationship line containing a ``_``-prefixed identifier segment.
# D2 relationship identifiers use ``.`` as a separator, so we look for a segment
# that starts with ``_`` after a ``.`` or at the start of the identifier.
# Examples:
#   ``task_graph_pkg.TaskGraph -> task_graph_pkg._validation: uses``
#   ``orchestrator_pkg.Orchestrator -> orchestrator_pkg._OrchestratorRun: creates``
_PRIVATE_REL_RE = re.compile(r"(?:^|\.|\s)_\w+")


def filter_private_nodes(lines: list[str]) -> list[str]:
    """Remove ``_``-prefixed node blocks and their relationship lines.

    Node blocks are detected by matching a definition line whose identifier
    starts with ``_``, then tracking brace depth to skip the entire block
    (including nested content). Relationship lines referencing any
    ``_``-prefixed identifier segment are also removed.

    Args:
        lines: D2 source lines (without trailing newlines).

    Returns:
        Filtered lines with private elements removed.
    """
    result: list[str] = []
    skip_depth = 0

    for line in lines:
        stripped = line.rstrip()

        # If we're inside a private node block, track braces until we exit.
        if skip_depth > 0:
            skip_depth += stripped.count("{") - stripped.count("}")
            if skip_depth <= 0:
                skip_depth = 0
            continue

        # Check if this line starts a private node definition.
        if _PRIVATE_NODE_RE.match(stripped):
            if "{" in stripped:
                skip_depth = stripped.count("{") - stripped.count("}")
                if skip_depth <= 0:
                    skip_depth = 0
            continue

        # Check if this is a relationship line referencing a private node.
        # Only check lines that contain ``->`` (relationship syntax).
        if "->" in stripped and _PRIVATE_REL_RE.search(stripped):
            continue

        result.append(line)

    return result


def generate_standard(input_path: Path, output_path: Path) -> None:
    """Read the detailed diagram and write the filtered standard diagram."""
    source = input_path.read_text()
    lines = source.splitlines()
    filtered = filter_private_nodes(lines)
    output_path.write_text("\n".join(filtered) + "\n")


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate standard diagram by filtering private nodes.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("docs/diagram-detailed.d2"),
        help="Path to detailed diagram (default: docs/diagram-detailed.d2)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/diagram-standard.d2"),
        help="Path to write output (default: docs/diagram-standard.d2)",
    )
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    generate_standard(args.input, args.output)
    print(f"Standard diagram written to {args.output}")


if __name__ == "__main__":
    main()
