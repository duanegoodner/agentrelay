"""Generate a package-level overview diagram from the detail D2 diagram.

Parses ``docs/diagram.d2``, extracts top-level containers (packages) and
cross-package relationships, deduplicates arrows to one per package pair,
and writes ``docs/diagram-overview.d2`` with tooltips listing each
package's classes.

Usage::

    python tools/generate_overview.py
    python tools/generate_overview.py --input docs/diagram.d2 --output docs/diagram-overview.d2
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Package:
    """A top-level D2 container (package)."""

    id: str
    label: str
    members: list[str] = field(default_factory=list)


@dataclass
class Relationship:
    """A single parsed relationship line."""

    source: str
    target: str
    label: str
    style_class: str


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# Matches top-level container: ``task_py: "task.py" {``
_CONTAINER_RE = re.compile(r'^(\w+):\s*"([^"]+)"\s*\{')

# Matches a nested class/module definition inside a container.
# Handles both ``ClassName: "ClassName <<stereotype>>" {`` and
# ``name: "display label" {`` forms.
_MEMBER_RE = re.compile(r'^\s+(\w+):\s*"([^"]+)"\s*\{')

# Matches a relationship line.
# e.g. ``task_py.Task -> task_py.AgentRole: role { class: composition }``
_RELATIONSHIP_RE = re.compile(
    r"^([\w.]+)\s*->\s*([\w.]+)"  # source -> target
    r"(?::\s*(.*?))?"  # optional label
    r"\s*(?:\{\s*class:\s*(\w+)\s*\})?"  # optional style class
    r"\s*$"
)


def parse_packages(lines: list[str]) -> list[Package]:
    """Extract top-level packages and their member names from D2 source lines."""
    packages: list[Package] = []
    current_pkg: Package | None = None
    depth = 0

    for line in lines:
        stripped = line.rstrip()

        # Track brace depth to know when we exit a top-level container
        if current_pkg is not None:
            depth += stripped.count("{") - stripped.count("}")
            if depth <= 0:
                current_pkg = None
                depth = 0
                continue

            member_match = _MEMBER_RE.match(line)
            if member_match:
                member_id = member_match.group(1)
                # Skip sub-containers (nested packages like core/, implementations/)
                # — they are structural groupings, not classes/modules.
                if member_id.endswith("_pkg"):
                    continue
                current_pkg.members.append(member_id)
            continue

        container_match = _CONTAINER_RE.match(stripped)
        if container_match:
            pkg = Package(
                id=container_match.group(1),
                label=container_match.group(2),
            )
            packages.append(pkg)
            current_pkg = pkg
            depth = 1

    return packages


def parse_relationships(lines: list[str]) -> list[Relationship]:
    """Extract relationship definitions from D2 source lines."""
    relationships: list[Relationship] = []

    # Only parse lines after the Relationships section header
    in_relationships = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and "Relationships" in stripped:
            in_relationships = True
            continue
        if not in_relationships:
            continue

        match = _RELATIONSHIP_RE.match(stripped)
        if match:
            label = (match.group(3) or "").strip().strip('"')
            style_class = match.group(4) or ""
            relationships.append(
                Relationship(
                    source=match.group(1),
                    target=match.group(2),
                    label=label,
                    style_class=style_class,
                )
            )

    return relationships


def resolve_package(dotted_path: str, package_ids: set[str]) -> str | None:
    """Resolve a dotted D2 path to its top-level package ID.

    Returns ``None`` if the path doesn't belong to any known package.
    """
    first_segment = dotted_path.split(".")[0]
    if first_segment in package_ids:
        return first_segment
    return None


# ---------------------------------------------------------------------------
# Overview generation
# ---------------------------------------------------------------------------


@dataclass
class OverviewArrow:
    """A deduplicated package-to-package arrow."""

    source_pkg: str
    target_pkg: str
    labels: list[str] = field(default_factory=list)
    style_classes: set[str] = field(default_factory=set)


def build_overview_arrows(
    relationships: list[Relationship],
    package_ids: set[str],
) -> list[OverviewArrow]:
    """Deduplicate relationships to package-level arrows."""
    arrow_map: dict[tuple[str, str], OverviewArrow] = {}

    for rel in relationships:
        src_pkg = resolve_package(rel.source, package_ids)
        tgt_pkg = resolve_package(rel.target, package_ids)

        if src_pkg is None or tgt_pkg is None:
            continue
        if src_pkg == tgt_pkg:
            continue

        key = (src_pkg, tgt_pkg)
        if key not in arrow_map:
            arrow_map[key] = OverviewArrow(source_pkg=src_pkg, target_pkg=tgt_pkg)

        arrow = arrow_map[key]
        if rel.label and rel.label not in arrow.labels:
            arrow.labels.append(rel.label)
        if rel.style_class:
            arrow.style_classes.add(rel.style_class)

    return sorted(arrow_map.values(), key=lambda a: (a.source_pkg, a.target_pkg))


def _summarize_labels(labels: list[str], max_labels: int = 3) -> str:
    """Create a concise arrow label from collected relationship labels."""
    if not labels:
        return ""
    unique = list(dict.fromkeys(labels))
    if len(unique) <= max_labels:
        return ", ".join(unique)
    return ", ".join(unique[:max_labels]) + ", ..."


def _pick_style_class(style_classes: set[str]) -> str:
    """Pick the dominant style class for a deduplicated arrow."""
    # Prefer composition > dependency > implementation > inheritance
    for candidate in ("composition", "dependency", "implementation", "inheritance"):
        if candidate in style_classes:
            return candidate
    return ""


def generate_overview_d2(
    packages: list[Package],
    arrows: list[OverviewArrow],
) -> str:
    """Generate the D2 source for the overview diagram."""
    lines: list[str] = []
    lines.append("direction: down")
    lines.append("")
    lines.append("# ─────────────────────────────────────────────")
    lines.append("#  Auto-generated package overview diagram")
    lines.append("#  Source: docs/diagram.d2")
    lines.append("#  Generator: tools/generate_overview.py")
    lines.append("# ─────────────────────────────────────────────")
    lines.append("")

    # Style classes
    lines.append("classes: {")
    lines.append("  composition: {")
    lines.append('    style.stroke: "#333333"')
    lines.append("  }")
    lines.append("  dependency: {")
    lines.append("    style.stroke-dash: 3")
    lines.append("  }")
    lines.append("}")
    lines.append("")

    # Package boxes with tooltips
    lines.append("# ─────────────────────────────────────────────")
    lines.append("#  Packages")
    lines.append("# ─────────────────────────────────────────────")
    for pkg in packages:
        tooltip_content = ", ".join(pkg.members) if pkg.members else "(empty)"
        lines.append(f'{pkg.id}: "{pkg.label}" {{')
        lines.append(f'  tooltip: "Classes: {tooltip_content}"')
        lines.append(f'  link: "diagram.svg"')
        lines.append("}")
        lines.append("")

    # Arrows
    lines.append("# ─────────────────────────────────────────────")
    lines.append("#  Cross-package relationships")
    lines.append("# ─────────────────────────────────────────────")
    for arrow in arrows:
        label = _summarize_labels(arrow.labels)
        style = _pick_style_class(arrow.style_classes)

        parts = [f"{arrow.source_pkg} -> {arrow.target_pkg}"]
        if label:
            parts.append(f": {label}")
        if style:
            if not label:
                parts.append(":")
            parts.append(f" {{ class: {style} }}")
        lines.append("".join(parts))

    lines.append("")
    return "\n".join(lines)


def generate_overview_html(svg_path: Path, detail_svg_path: str) -> str:
    """Generate an HTML page that inlines the overview SVG with JS tooltips.

    Reads the rendered SVG, embeds it in an HTML page, and adds JavaScript
    that converts ``<title>`` elements into visible tooltip popups on hover.

    Args:
        svg_path: Path to the rendered overview SVG.
        detail_svg_path: Relative path to the detail SVG (for link clicks).

    Returns:
        HTML page content as a string.
    """
    svg_content = svg_path.read_text()

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>agentrelay — Package Overview</title>
<style>
  body {{
    margin: 0;
    padding: 20px;
    background: #fff;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }}
  h1 {{
    font-size: 18px;
    color: #333;
    margin: 0 0 12px 0;
  }}
  .subtitle {{
    font-size: 13px;
    color: #666;
    margin-bottom: 16px;
  }}
  .svg-container {{
    overflow: auto;
  }}
  .svg-container svg {{
    max-width: 100%;
    height: auto;
  }}
  #tooltip {{
    display: none;
    position: fixed;
    background: #1a1a2e;
    color: #e0e0e0;
    padding: 10px 14px;
    border-radius: 6px;
    font-size: 13px;
    line-height: 1.5;
    max-width: 420px;
    pointer-events: none;
    z-index: 1000;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  }}
  #tooltip .tip-title {{
    font-weight: 600;
    color: #fff;
    margin-bottom: 4px;
  }}
  #tooltip .tip-classes {{
    color: #b0b0c0;
  }}
</style>
</head>
<body>
<h1>Package Overview</h1>
<p class="subtitle">
  Hover over a package to see its classes. Click to open the
  <a href="{detail_svg_path}">detail diagram</a>.
</p>
<div class="svg-container">
{svg_content}
</div>
<div id="tooltip"></div>
<script>
(function() {{
  const tooltip = document.getElementById('tooltip');
  const svgEl = document.querySelector('.svg-container svg');
  if (!svgEl) return;

  // Find all groups that have a <title> child with tooltip content.
  const groups = svgEl.querySelectorAll('g');
  groups.forEach(function(g) {{
    const title = g.querySelector(':scope > title');
    if (!title || !title.textContent) return;
    const text = title.textContent.trim();
    if (!text.startsWith('Classes:') && !text.startsWith('**Classes')) return;

    // Find the display label from the <text> sibling.
    const labelEl = g.querySelector(':scope > text');
    const label = labelEl ? labelEl.textContent.trim() : '';

    // Clean up the classes text.
    let classes = text
      .replace(/^\\*\\*Classes\\/modules:\\*\\*\\s*/, '')
      .replace(/^Classes:\\s*/, '');

    g.style.cursor = 'pointer';

    g.addEventListener('mouseenter', function(e) {{
      tooltip.innerHTML =
        '<div class="tip-title">' + escapeHtml(label) + '</div>' +
        '<div class="tip-classes">' + escapeHtml(classes) + '</div>';
      tooltip.style.display = 'block';
      positionTooltip(e);
    }});

    g.addEventListener('mousemove', positionTooltip);

    g.addEventListener('mouseleave', function() {{
      tooltip.style.display = 'none';
    }});
  }});

  function positionTooltip(e) {{
    const pad = 12;
    let x = e.clientX + pad;
    let y = e.clientY + pad;
    // Keep tooltip on screen.
    const rect = tooltip.getBoundingClientRect();
    if (x + rect.width > window.innerWidth - pad) {{
      x = e.clientX - rect.width - pad;
    }}
    if (y + rect.height > window.innerHeight - pad) {{
      y = e.clientY - rect.height - pad;
    }}
    tooltip.style.left = x + 'px';
    tooltip.style.top = y + 'px';
  }}

  function escapeHtml(str) {{
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }}
}})();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def generate_overview(input_path: Path, output_path: Path) -> None:
    """Read the detail diagram and write the overview diagram."""
    source = input_path.read_text()
    source_lines = source.splitlines()

    packages = parse_packages(source_lines)
    package_ids = {pkg.id for pkg in packages}
    relationships = parse_relationships(source_lines)
    arrows = build_overview_arrows(relationships, package_ids)

    overview = generate_overview_d2(packages, arrows)
    output_path.write_text(overview)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate package-level overview from detail D2 diagram.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("docs/diagram.d2"),
        help="Path to detail diagram (default: docs/diagram.d2)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/diagram-overview.d2"),
        help="Path to write overview diagram (default: docs/diagram-overview.d2)",
    )
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Only generate HTML wrapper (SVG must already exist).",
    )
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    svg_path = args.output.with_suffix(".svg")
    html_path = args.output.with_suffix(".html")

    if args.html_only:
        if not svg_path.exists():
            print(f"Error: SVG not found: {svg_path}", file=sys.stderr)
            sys.exit(1)
        html = generate_overview_html(svg_path, detail_svg_path="diagram.svg")
        html_path.write_text(html)
        print(f"Overview HTML written to {html_path}")
        return

    generate_overview(args.input, args.output)
    print(f"Overview diagram written to {args.output}")


if __name__ == "__main__":
    main()
