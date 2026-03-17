"""Generate the overview diagram from the detail D2 diagram.

Parses the detail D2 source to extract packages and relationships, then
generates a package-level overview D2 file and an interactive HTML page
with connector click popups showing class-level dependencies.

Usage::

    python tools/generate_overview.py
    python tools/generate_overview.py --html-only
"""

from __future__ import annotations

import argparse
import json
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
    lines.append("#  Source: docs/diagram-detailed.d2")
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
        lines.append(f'  link: "diagram-detailed.svg"')
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


# ---------------------------------------------------------------------------
# Cross-package arrow detail (used by overview HTML)
# ---------------------------------------------------------------------------


@dataclass
class CrossPackageArrow:
    """A deduplicated cross-package arrow with class-level detail."""

    source_pkg: str
    target_pkg: str
    details: list[str] = field(default_factory=list)
    style_classes: set[str] = field(default_factory=set)


def build_cross_package_arrows(
    relationships: list[Relationship],
    package_ids: set[str],
) -> list[CrossPackageArrow]:
    """Deduplicate cross-package relationships, collecting class-level detail."""
    arrow_map: dict[tuple[str, str], CrossPackageArrow] = {}

    for rel in relationships:
        src_pkg = resolve_package(rel.source, package_ids)
        tgt_pkg = resolve_package(rel.target, package_ids)

        if src_pkg is None or tgt_pkg is None:
            continue
        if src_pkg == tgt_pkg:
            continue

        key = (src_pkg, tgt_pkg)
        if key not in arrow_map:
            arrow_map[key] = CrossPackageArrow(source_pkg=src_pkg, target_pkg=tgt_pkg)

        arrow = arrow_map[key]
        src_class = rel.source.rsplit(".", 1)[-1]
        tgt_class = rel.target.rsplit(".", 1)[-1]
        detail = f"{src_class} \u2192 {tgt_class}"
        if rel.label:
            detail += f" ({rel.label})"
        arrow.details.append(detail)
        if rel.style_class:
            arrow.style_classes.add(rel.style_class)

    return sorted(arrow_map.values(), key=lambda a: (a.source_pkg, a.target_pkg))


# ---------------------------------------------------------------------------
# Overview HTML
# ---------------------------------------------------------------------------


def generate_overview_html(
    svg_path: Path,
    detail_svg_path: str,
    arrows: list[CrossPackageArrow] | None = None,
) -> str:
    """Generate an HTML page that inlines the overview SVG with connector popups.

    Clicking a connector arrow opens a popup showing the class-level dependency
    list between the two packages.  Package nodes are not interactive.
    """
    svg_content = svg_path.read_text()

    # Build arrow connection data for popup display.
    arrow_connection_map: dict[str, str] = {}
    if arrows:
        for arrow in arrows:
            key = f"{arrow.source_pkg}|{arrow.target_pkg}"
            conn_lines: list[str] = []
            conn_lines.append(f"{arrow.source_pkg} \u2192 {arrow.target_pkg}")
            for detail in arrow.details:
                conn_lines.append(detail)
            arrow_connection_map[key] = "\n".join(conn_lines)

    arrow_connections_json = json.dumps(arrow_connection_map, ensure_ascii=False)

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>agentrelay \u2014 Package Overview</title>
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
  /* Click-to-open popup panel */
  #popup-overlay {{
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.4);
    z-index: 2000;
  }}
  #popup-panel {{
    display: none;
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    z-index: 2001;
    max-width: 60vw;
    max-height: 70vh;
    overflow: auto;
    min-width: 320px;
  }}
  #popup-panel .popup-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid #e0e0e0;
    background: #f8f8f8;
    border-radius: 8px 8px 0 0;
    position: sticky;
    top: 0;
    z-index: 1;
  }}
  #popup-panel .popup-title {{
    font-weight: 600;
    font-size: 15px;
    color: #333;
  }}
  #popup-panel .popup-close {{
    cursor: pointer;
    font-size: 20px;
    color: #666;
    border: none;
    background: none;
    padding: 0 4px;
    line-height: 1;
  }}
  #popup-panel .popup-close:hover {{
    color: #333;
  }}
  #popup-panel .popup-body {{
    padding: 16px;
  }}
  .conn-item {{
    color: #555;
    font-family: "SF Mono", "Fira Code", Menlo, Consolas, monospace;
    font-size: 13px;
    line-height: 1.6;
  }}
</style>
</head>
<body>
<h1>Package Overview</h1>
<p class="subtitle">
  Click a connection to see class-level dependencies.
  <a href="{detail_svg_path}">View full detail diagram</a>.
</p>
<div class="svg-container">
{svg_content}
</div>
<div id="popup-overlay"></div>
<div id="popup-panel">
  <div class="popup-header">
    <span class="popup-title"></span>
    <button class="popup-close">&times;</button>
  </div>
  <div class="popup-body"></div>
</div>
<script>
(function() {{
  var ARROW_CONNECTIONS = {arrow_connections_json};

  var overlay = document.getElementById('popup-overlay');
  var panel = document.getElementById('popup-panel');
  var panelTitle = panel.querySelector('.popup-title');
  var panelBody = panel.querySelector('.popup-body');
  var panelClose = panel.querySelector('.popup-close');
  var svgEl = document.querySelector('.svg-container svg');
  if (!svgEl) return;

  function openPopup(title, bodyHtml) {{
    panelTitle.textContent = title;
    panelBody.innerHTML = bodyHtml;
    overlay.style.display = 'block';
    panel.style.display = 'block';
  }}
  function closePopup() {{
    overlay.style.display = 'none';
    panel.style.display = 'none';
    panelBody.innerHTML = '';
  }}
  panelClose.addEventListener('click', closePopup);
  overlay.addEventListener('click', closePopup);
  document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') closePopup();
  }});

  function escapeHtml(str) {{
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }}

  // --- Arrow click ---
  if (Object.keys(ARROW_CONNECTIONS).length > 0) {{
    svgEl.querySelectorAll('g').forEach(function(g) {{
      var cls = g.getAttribute('class') || '';
      if (!cls || cls === 'shape') return;
      var decoded = '';
      try {{ decoded = atob(cls.split(' ')[0]); }} catch(e) {{ return; }}
      decoded = decoded.replace(/&gt;/g, '>');
      var edgeMatch = decoded.match(/^\\((.+?)\\s*->\\s*(.+?)\\)/);
      if (!edgeMatch) return;
      var key = edgeMatch[1].trim() + '|' + edgeMatch[2].trim();

      if (!ARROW_CONNECTIONS[key]) return;
      g.style.cursor = 'pointer';

      g.addEventListener('click', function(e) {{
        e.stopPropagation();
        var connData = ARROW_CONNECTIONS[key];
        var lines = connData.split('\\n');
        var html = '';
        for (var i = 1; i < lines.length; i++) {{
          html += '<div class="conn-item">' + escapeHtml(lines[i]) + '</div>';
        }}
        var titleParts = key.split('|');
        openPopup(titleParts[0] + ' \\u2192 ' + titleParts[1], html);
      }});
    }});
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


_DEFAULT_OUTPUT = Path("docs/diagram-overview.d2")


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate the overview diagram from the detail D2 diagram.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("docs/diagram-detailed.d2"),
        help="Path to detail diagram (default: docs/diagram-detailed.d2)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to write output (default: docs/diagram-overview.d2)",
    )
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Only generate HTML wrapper (SVG must already exist).",
    )
    args = parser.parse_args(argv)

    if args.output is None:
        args.output = _DEFAULT_OUTPUT

    if not args.input.exists():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    svg_path = args.output.with_suffix(".svg")
    html_path = args.output.with_suffix(".html")

    if args.html_only:
        if not svg_path.exists():
            print(f"Error: SVG not found: {svg_path}", file=sys.stderr)
            sys.exit(1)
        source_lines = args.input.read_text().splitlines()
        relationships = parse_relationships(source_lines)
        packages = parse_packages(source_lines)
        package_ids = {p.id for p in packages}
        arrows = build_cross_package_arrows(relationships, package_ids)

        html = generate_overview_html(
            svg_path,
            detail_svg_path="diagram-detailed.svg",
            arrows=arrows,
        )
        html_path.write_text(html)
        print(f"Overview HTML written to {html_path}")
        return

    generate_overview(args.input, args.output)
    print(f"Overview diagram written to {args.output}")


if __name__ == "__main__":
    main()
