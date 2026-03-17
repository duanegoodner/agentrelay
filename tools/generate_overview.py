"""Generate derived diagrams from the detail D2 diagram.

Supports three modes:

**Overview** (default) — package-level boxes with tooltips listing classes.
**Midlevel** — full package internals, but cross-package arrows collapsed
to one per package pair with tooltips showing class-to-class connections.
**Package-SVGs** — extract per-package D2 files, render each to SVG via
D2, and regenerate the overview HTML with click-to-open graphical popups.

Usage::

    python tools/generate_overview.py
    python tools/generate_overview.py --mode midlevel --output docs/diagram-midlevel.d2
    python tools/generate_overview.py --mode package-svgs
    python tools/generate_overview.py --html-only
    python tools/generate_overview.py --mode midlevel --html-only
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from textwrap import dedent

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


@dataclass
class ClassInfo:
    """A class/module parsed from D2 with its members."""

    id: str
    display_label: str
    members: list[str] = field(default_factory=list)


@dataclass
class SubPackageDetail:
    """A nested sub-package within a top-level package."""

    id: str
    label: str
    classes: list[ClassInfo] = field(default_factory=list)


@dataclass
class PackageDetail:
    """A top-level package with full internal structure."""

    id: str
    label: str
    direct_classes: list[ClassInfo] = field(default_factory=list)
    sub_packages: list[SubPackageDetail] = field(default_factory=list)


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


# Lines to skip when collecting class body members.
_SKIP_BODY = {"shape: class", ""}


def parse_package_details(lines: list[str]) -> list[PackageDetail]:
    """Extract full internal structure of each top-level package.

    Returns packages with nested sub-packages, classes, and their members
    (fields and methods).
    """
    packages: list[PackageDetail] = []
    current_pkg: PackageDetail | None = None
    current_subpkg: SubPackageDetail | None = None
    current_class: ClassInfo | None = None
    depth = 0

    for line in lines:
        stripped = line.rstrip()
        opens = stripped.count("{")
        closes = stripped.count("}")

        if depth == 0:
            m = _CONTAINER_RE.match(stripped)
            if m:
                current_pkg = PackageDetail(id=m.group(1), label=m.group(2))
                packages.append(current_pkg)
                current_subpkg = None
                current_class = None
            depth += opens - closes
            continue

        if current_pkg is None:
            depth += opens - closes
            if depth <= 0:
                depth = 0
            continue

        # depth 1: inside top-level package — sub-packages or direct classes
        if depth == 1:
            m = _MEMBER_RE.match(line)
            if m:
                member_id, member_label = m.group(1), m.group(2)
                if member_id.endswith("_pkg"):
                    current_subpkg = SubPackageDetail(id=member_id, label=member_label)
                    current_pkg.sub_packages.append(current_subpkg)
                    current_class = None
                else:
                    current_class = ClassInfo(id=member_id, display_label=member_label)
                    current_pkg.direct_classes.append(current_class)
                    current_subpkg = None

        # depth 2: class inside sub-pkg OR body of direct class
        elif depth == 2:
            m = _MEMBER_RE.match(line)
            if current_subpkg is not None and m:
                current_class = ClassInfo(id=m.group(1), display_label=m.group(2))
                current_subpkg.classes.append(current_class)
            elif current_class is not None:
                content = stripped.strip()
                if (
                    content not in _SKIP_BODY
                    and not content.startswith("#")
                    and content != "}"
                ):
                    # Skip style directives
                    if not content.startswith("style."):
                        current_class.members.append(content)

        # depth 3: body of class inside sub-package
        elif depth == 3 and current_class is not None:
            content = stripped.strip()
            if (
                content not in _SKIP_BODY
                and not content.startswith("#")
                and content != "}"
            ):
                if not content.startswith("style."):
                    current_class.members.append(content)

        depth += opens - closes

        # Reset context when exiting scopes.
        if depth <= 0:
            current_pkg = None
            current_subpkg = None
            current_class = None
            depth = 0
        elif depth <= 1:
            if current_subpkg is not None:
                current_subpkg = None
            current_class = None

    return packages


# ---------------------------------------------------------------------------
# Per-package D2 extraction and SVG rendering
# ---------------------------------------------------------------------------


def extract_package_d2_blocks(lines: list[str]) -> dict[str, list[str]]:
    """Extract each top-level package's inner D2 lines.

    Returns ``{pkg_id: [inner_lines...]}``.  Each inner-line list contains the
    *unwrapped* content of the container — dedented by one level so classes and
    sub-packages become top-level D2 elements.
    """
    blocks: dict[str, list[str]] = {}
    current_id: str | None = None
    inner_lines: list[str] = []
    depth = 0

    for line in lines:
        stripped = line.rstrip()
        opens = stripped.count("{")
        closes = stripped.count("}")

        if depth == 0:
            m = _CONTAINER_RE.match(stripped)
            if m:
                current_id = m.group(1)
                inner_lines = []
                depth = opens - closes
                if depth <= 0:
                    # Single-line container (unlikely) — skip.
                    current_id = None
                    depth = 0
            continue

        if current_id is not None:
            depth += opens - closes
            if depth <= 0:
                # Closing brace of the top-level container — don't include it.
                blocks[current_id] = inner_lines
                current_id = None
                inner_lines = []
                depth = 0
            else:
                # Remove one level of indentation (2 spaces).
                if line.startswith("  "):
                    inner_lines.append(line[2:])
                else:
                    inner_lines.append(line)
        else:
            depth += opens - closes
            if depth <= 0:
                depth = 0

    return blocks


def _style_classes_block() -> str:
    """Return the standard D2 style-classes preamble."""
    return dedent("""\
        classes: {
          composition: {
            style.stroke: "#333333"
          }
          dependency: {
            style.stroke-dash: 3
          }
          inheritance: {
            target-arrowhead.shape: triangle
            style.stroke: "#333333"
          }
          implementation: {
            style.stroke-dash: 3
            target-arrowhead.shape: triangle
          }
        }
    """)


def generate_package_d2_files(
    input_path: Path,
    output_dir: Path,
) -> list[Path]:
    """Extract per-package D2 files with intra-package relationships.

    Writes one ``.d2`` file per top-level package to *output_dir*.
    Returns the list of generated file paths.
    """
    source_lines = input_path.read_text().splitlines()
    blocks = extract_package_d2_blocks(source_lines)
    packages = parse_packages(source_lines)
    package_ids = {p.id for p in packages}
    relationships = parse_relationships(source_lines)
    intra_rels, _ = classify_relationships(relationships, package_ids)

    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []

    for pkg_id, inner_lines in blocks.items():
        parts: list[str] = []
        parts.append("direction: down")
        parts.append("")
        parts.append(_style_classes_block())

        # Package inner content (classes, sub-packages).
        for inner_line in inner_lines:
            parts.append(inner_line)

        # Intra-package relationships (strip the package prefix).
        pkg_rels = [r for r in intra_rels if resolve_package(r.source, {pkg_id})]
        if pkg_rels:
            parts.append("")
            parts.append("# Relationships")
            for rel in pkg_rels:
                # Strip pkg_id prefix from source/target.
                src = rel.source
                tgt = rel.target
                if src.startswith(f"{pkg_id}."):
                    src = src[len(pkg_id) + 1 :]
                if tgt.startswith(f"{pkg_id}."):
                    tgt = tgt[len(pkg_id) + 1 :]
                line = f"{src} -> {tgt}"
                if rel.label:
                    line += f": {rel.label}"
                if rel.style_class:
                    if not rel.label:
                        line += ":"
                    line += f" {{ class: {rel.style_class} }}"
                parts.append(line)

        parts.append("")
        out_path = output_dir / f"{pkg_id}.d2"
        out_path.write_text("\n".join(parts))
        generated.append(out_path)

    return generated


def render_package_svgs(
    d2_files: list[Path],
) -> dict[str, str]:
    """Render each D2 file to SVG using ``d2`` and return SVG content.

    Returns ``{pkg_id: svg_content}``.  Raises ``RuntimeError`` if ``d2``
    is not available or rendering fails.
    """
    results: dict[str, str] = {}

    for d2_path in d2_files:
        pkg_id = d2_path.stem
        svg_path = d2_path.with_suffix(".svg")
        result = subprocess.run(
            [
                "d2",
                "--layout",
                "elk",
                "--elk-padding",
                "[top=10,left=10,bottom=10,right=10]",
                "--scale",
                "0.8",
                "--pad",
                "10",
                str(d2_path),
                str(svg_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(
                f"Warning: d2 render failed for {d2_path}: {result.stderr}",
                file=sys.stderr,
            )
            continue

        results[pkg_id] = svg_path.read_text()

    return results


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


def _format_package_detail_html(pkg: PackageDetail) -> str:
    """Format a PackageDetail as an HTML snippet for tooltip display."""
    parts: list[str] = []

    def _format_class(cls: ClassInfo, indent: int = 0) -> None:
        pad = "  " * indent
        parts.append(f"{pad}{cls.display_label}")
        for member in cls.members:
            parts.append(f"{pad}  {member}")

    if pkg.sub_packages:
        for subpkg in pkg.sub_packages:
            parts.append(f"{subpkg.label}")
            for cls in subpkg.classes:
                _format_class(cls, indent=1)
    if pkg.direct_classes:
        for cls in pkg.direct_classes:
            _format_class(cls, indent=0)

    return "\n".join(parts)


def generate_overview_html(
    svg_path: Path,
    detail_svg_path: str,
    package_details: list[PackageDetail] | None = None,
    midlevel_arrows: list[MidlevelArrow] | None = None,
    package_svgs: dict[str, str] | None = None,
) -> str:
    """Generate an HTML page that inlines the overview SVG with interactive popups.

    When *package_svgs* is provided, clicking a package opens a popup panel
    showing that package's D2-rendered class diagram.  Clicking an arrow shows
    both endpoint packages side-by-side with a text connection list.

    Falls back to hover tooltips when *package_svgs* is ``None``.
    """
    svg_content = svg_path.read_text()

    # Build JSON data for tooltips / popups.
    pkg_tooltip_map: dict[str, str] = {}
    if package_details:
        for pkg in package_details:
            pkg_tooltip_map[pkg.label] = _format_package_detail_html(pkg)
        pkg_by_id: dict[str, PackageDetail] = {pkg.id: pkg for pkg in package_details}
    else:
        pkg_by_id = {}

    arrow_tooltip_map: dict[str, str] = {}
    arrow_connection_map: dict[str, str] = {}
    arrow_pkg_ids_map: dict[str, list[str]] = {}
    if midlevel_arrows and pkg_by_id:
        for arrow in midlevel_arrows:
            src_pkg = pkg_by_id.get(arrow.source_pkg)
            tgt_pkg = pkg_by_id.get(arrow.target_pkg)
            src_label = src_pkg.label if src_pkg else arrow.source_pkg
            tgt_label = tgt_pkg.label if tgt_pkg else arrow.target_pkg

            key = f"{arrow.source_pkg}|{arrow.target_pkg}"
            arrow_pkg_ids_map[key] = [arrow.source_pkg, arrow.target_pkg]

            # Connection text (always text-based).
            conn_lines: list[str] = []
            conn_lines.append(f"{src_label} \u2192 {tgt_label}")
            for detail in arrow.details:
                conn_lines.append(detail)
            arrow_connection_map[key] = "\n".join(conn_lines)

            # Text fallback (used when no package_svgs).
            sections: list[str] = []
            sections.append(f"=== {src_label} ===")
            if src_pkg:
                sections.append(_format_package_detail_html(src_pkg))
            sections.append("")
            sections.append(f"=== {tgt_label} ===")
            if tgt_pkg:
                sections.append(_format_package_detail_html(tgt_pkg))
            sections.append("")
            sections.append("--- connections ---")
            for detail in arrow.details:
                sections.append(detail)
            arrow_tooltip_map[key] = "\n".join(sections)

    pkg_json = json.dumps(pkg_tooltip_map, ensure_ascii=False)
    arrow_json = json.dumps(arrow_tooltip_map, ensure_ascii=False)

    # Map package label → pkg_id for JS to look up SVGs by label.
    pkg_label_to_id: dict[str, str] = {}
    if package_details:
        for pkg in package_details:
            pkg_label_to_id[pkg.label] = pkg.id
    pkg_label_to_id_json = json.dumps(pkg_label_to_id, ensure_ascii=False)

    # Package SVGs (base64 encoded to avoid quoting issues in JSON).
    import base64

    pkg_svgs_b64: dict[str, str] = {}
    if package_svgs:
        for pid, svg in package_svgs.items():
            pkg_svgs_b64[pid] = base64.b64encode(svg.encode()).decode()
    pkg_svgs_json = json.dumps(pkg_svgs_b64, ensure_ascii=False)

    # Arrow endpoint pkg ids and connection text.
    arrow_pkg_ids_json = json.dumps(arrow_pkg_ids_map, ensure_ascii=False)
    arrow_connections_json = json.dumps(arrow_connection_map, ensure_ascii=False)

    use_popups = package_svgs is not None and len(package_svgs) > 0

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
  /* Hover tooltip (fallback when no SVG popups) */
  #tooltip {{
    display: none;
    position: fixed;
    background: #1a1a2e;
    color: #e0e0e0;
    padding: 12px 16px;
    border-radius: 6px;
    font-size: 13px;
    line-height: 1.4;
    max-width: 520px;
    max-height: 70vh;
    overflow-y: auto;
    pointer-events: none;
    z-index: 1000;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    white-space: pre;
    font-family: "SF Mono", "Fira Code", "Fira Mono", Menlo, Consolas, monospace;
  }}
  #tooltip .tip-title {{
    font-weight: 600;
    color: #fff;
    margin-bottom: 6px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    white-space: normal;
  }}
  #tooltip .tip-body {{
    color: #c0c0d0;
  }}
  #tooltip .tip-section {{
    color: #7eb8da;
    font-weight: 600;
    margin-top: 6px;
  }}
  #tooltip .tip-connections {{
    color: #a0d0a0;
    margin-top: 4px;
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
    max-width: 90vw;
    max-height: 85vh;
    overflow: auto;
    min-width: 400px;
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
  #popup-panel .popup-body svg {{
    max-width: 100%;
    height: auto;
  }}
  /* Arrow popup: two packages side by side + connections */
  .arrow-popup-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 16px;
  }}
  .arrow-popup-pkg {{
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    overflow: auto;
    max-height: 50vh;
  }}
  .arrow-popup-pkg-title {{
    font-weight: 600;
    font-size: 13px;
    color: #555;
    padding: 8px 12px;
    background: #f8f8f8;
    border-bottom: 1px solid #e0e0e0;
    position: sticky;
    top: 0;
  }}
  .arrow-popup-pkg svg {{
    max-width: 100%;
    height: auto;
    display: block;
    padding: 8px;
  }}
  .arrow-popup-connections {{
    border-top: 1px solid #e0e0e0;
    padding: 12px 16px;
    font-size: 13px;
    line-height: 1.6;
  }}
  .arrow-popup-connections .conn-title {{
    font-weight: 600;
    color: #333;
    margin-bottom: 6px;
  }}
  .arrow-popup-connections .conn-item {{
    color: #555;
    font-family: "SF Mono", "Fira Code", Menlo, Consolas, monospace;
    font-size: 12px;
  }}
</style>
</head>
<body>
<h1>Package Overview</h1>
<p class="subtitle">
  Click a package to see its internal structure.
  Click a connection to see what classes are linked.
  <a href="{detail_svg_path}">View full detail diagram</a>.
</p>
<div class="svg-container">
{svg_content}
</div>
<div id="tooltip"></div>
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
  var USE_POPUPS = {'true' if use_popups else 'false'};
  var PKG_TOOLTIPS = {pkg_json};
  var ARROW_TOOLTIPS = {arrow_json};
  var PKG_LABEL_TO_ID = {pkg_label_to_id_json};
  var PKG_SVGS_B64 = {pkg_svgs_json};
  var ARROW_PKG_IDS = {arrow_pkg_ids_json};
  var ARROW_CONNECTIONS = {arrow_connections_json};

  var tooltip = document.getElementById('tooltip');
  var overlay = document.getElementById('popup-overlay');
  var panel = document.getElementById('popup-panel');
  var panelTitle = panel.querySelector('.popup-title');
  var panelBody = panel.querySelector('.popup-body');
  var panelClose = panel.querySelector('.popup-close');
  var svgEl = document.querySelector('.svg-container svg');
  if (!svgEl) return;

  // --- Popup helpers ---
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

  function decodePkgSvg(pkgId) {{
    var b64 = PKG_SVGS_B64[pkgId];
    if (!b64) return null;
    return atob(b64);
  }}

  // --- Package click/hover ---
  var groups = svgEl.querySelectorAll('g');
  groups.forEach(function(g) {{
    var title = g.querySelector(':scope > title');
    if (!title || !title.textContent) return;
    var text = title.textContent.trim();
    if (!text.startsWith('Classes:')) return;

    var labelEl = g.querySelector(':scope > text');
    var label = labelEl ? labelEl.textContent.trim() : '';
    g.style.cursor = 'pointer';

    if (USE_POPUPS) {{
      g.addEventListener('click', function(e) {{
        e.stopPropagation();
        var pkgId = PKG_LABEL_TO_ID[label];
        var svgHtml = pkgId ? decodePkgSvg(pkgId) : null;
        if (svgHtml) {{
          openPopup(label, svgHtml);
        }} else {{
          // Fallback to text.
          var detail = PKG_TOOLTIPS[label] || text.replace(/^Classes:\\s*/, '');
          openPopup(label, '<pre style="margin:0;font-size:13px;line-height:1.4">' + escapeHtml(detail) + '</pre>');
        }}
      }});
    }} else {{
      // Hover tooltip fallback.
      var detail = PKG_TOOLTIPS[label];
      if (!detail) detail = text.replace(/^Classes:\\s*/, '');
      g.addEventListener('mouseenter', function(e) {{
        tooltip.innerHTML =
          '<div class="tip-title">' + escapeHtml(label) + '</div>' +
          '<div class="tip-body">' + escapeHtml(detail) + '</div>';
        tooltip.style.display = 'block';
        positionTooltip(e);
      }});
      g.addEventListener('mousemove', positionTooltip);
      g.addEventListener('mouseleave', hideTooltip);
    }}
  }});

  // --- Arrow click/hover ---
  if (Object.keys(ARROW_TOOLTIPS).length > 0 || Object.keys(ARROW_CONNECTIONS).length > 0) {{
    var edgeGroups = svgEl.querySelectorAll('g');
    edgeGroups.forEach(function(g) {{
      var cls = g.getAttribute('class') || '';
      if (!cls || cls === 'shape') return;
      var decoded = '';
      try {{ decoded = atob(cls.split(' ')[0]); }} catch(e) {{ return; }}
      decoded = decoded.replace(/&gt;/g, '>');
      var edgeMatch = decoded.match(/^\\((.+?)\\s*->\\s*(.+?)\\)/);
      if (!edgeMatch) return;
      var key = edgeMatch[1].trim() + '|' + edgeMatch[2].trim();

      // Need either tooltip or connection data.
      if (!ARROW_TOOLTIPS[key] && !ARROW_CONNECTIONS[key]) return;

      g.style.cursor = 'pointer';

      if (USE_POPUPS && ARROW_PKG_IDS[key]) {{
        g.addEventListener('click', function(e) {{
          e.stopPropagation();
          var pkgIds = ARROW_PKG_IDS[key];
          var srcId = pkgIds[0], tgtId = pkgIds[1];
          var srcSvg = decodePkgSvg(srcId);
          var tgtSvg = decodePkgSvg(tgtId);

          var html = '<div class="arrow-popup-grid">';

          // Source package.
          html += '<div class="arrow-popup-pkg">';
          html += '<div class="arrow-popup-pkg-title">' + escapeHtml(srcId) + '</div>';
          if (srcSvg) html += srcSvg;
          else html += '<div style="padding:12px;color:#999">SVG not available</div>';
          html += '</div>';

          // Target package.
          html += '<div class="arrow-popup-pkg">';
          html += '<div class="arrow-popup-pkg-title">' + escapeHtml(tgtId) + '</div>';
          if (tgtSvg) html += tgtSvg;
          else html += '<div style="padding:12px;color:#999">SVG not available</div>';
          html += '</div>';

          html += '</div>';

          // Connection text.
          var connData = ARROW_CONNECTIONS[key];
          if (connData) {{
            var lines = connData.split('\\n');
            html += '<div class="arrow-popup-connections">';
            html += '<div class="conn-title">' + escapeHtml(lines[0]) + '</div>';
            for (var i = 1; i < lines.length; i++) {{
              html += '<div class="conn-item">' + escapeHtml(lines[i]) + '</div>';
            }}
            html += '</div>';
          }}

          var titleParts = key.split('|');
          openPopup(titleParts[0] + ' \\u2192 ' + titleParts[1], html);
        }});
      }} else {{
        // Hover tooltip fallback.
        var detail = ARROW_TOOLTIPS[key];
        if (!detail) return;
        g.addEventListener('mouseenter', function(e) {{
          var lines = detail.split('\\n');
          var html = '';
          for (var i = 0; i < lines.length; i++) {{
            var line = lines[i];
            if (line.startsWith('===')) {{
              html += '<div class="tip-section">' + escapeHtml(line.replace(/^=+\\s*|\\s*=+$/g, '')) + '</div>';
            }} else if (line.startsWith('---')) {{
              html += '<div class="tip-section" style="color:#a0d0a0">' + escapeHtml(line.replace(/^-+\\s*|\\s*-+$/g, '')) + '</div>';
            }} else if (line.includes('\\u2192')) {{
              html += '<div class="tip-connections">' + escapeHtml(line) + '</div>';
            }} else {{
              html += escapeHtml(line) + '\\n';
            }}
          }}
          tooltip.innerHTML = html;
          tooltip.style.display = 'block';
          positionTooltip(e);
        }});
        g.addEventListener('mousemove', positionTooltip);
        g.addEventListener('mouseleave', hideTooltip);
      }}
    }});
  }}

  function hideTooltip() {{
    tooltip.style.display = 'none';
  }}

  function positionTooltip(e) {{
    var pad = 12;
    var x = e.clientX + pad;
    var y = e.clientY + pad;
    tooltip.style.left = x + 'px';
    tooltip.style.top = y + 'px';
    var rect = tooltip.getBoundingClientRect();
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
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }}
}})();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Mid-level generation
# ---------------------------------------------------------------------------


@dataclass
class MidlevelArrow:
    """A deduplicated cross-package arrow with class-level detail."""

    source_pkg: str
    target_pkg: str
    details: list[str] = field(default_factory=list)
    style_classes: set[str] = field(default_factory=set)


def build_midlevel_arrows(
    relationships: list[Relationship],
    package_ids: set[str],
) -> list[MidlevelArrow]:
    """Deduplicate cross-package relationships, collecting class-level detail."""
    arrow_map: dict[tuple[str, str], MidlevelArrow] = {}

    for rel in relationships:
        src_pkg = resolve_package(rel.source, package_ids)
        tgt_pkg = resolve_package(rel.target, package_ids)

        if src_pkg is None or tgt_pkg is None:
            continue
        if src_pkg == tgt_pkg:
            continue

        key = (src_pkg, tgt_pkg)
        if key not in arrow_map:
            arrow_map[key] = MidlevelArrow(source_pkg=src_pkg, target_pkg=tgt_pkg)

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


def classify_relationships(
    relationships: list[Relationship],
    package_ids: set[str],
) -> tuple[list[Relationship], list[Relationship]]:
    """Split relationships into (intra-package, cross-package) lists."""
    intra: list[Relationship] = []
    cross: list[Relationship] = []

    for rel in relationships:
        src_pkg = resolve_package(rel.source, package_ids)
        tgt_pkg = resolve_package(rel.target, package_ids)

        if src_pkg is not None and tgt_pkg is not None and src_pkg == tgt_pkg:
            intra.append(rel)
        else:
            cross.append(rel)

    return intra, cross


def _find_relationships_start(lines: list[str]) -> int:
    """Return the line index where the Relationships section header begins.

    Looks for the ``\u2550`` separator line immediately before the
    ``Relationships`` comment.  Returns ``len(lines)`` if not found.
    """
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "\u2550" in stripped:
            for j in range(i + 1, min(i + 3, len(lines))):
                if "Relationships" in lines[j]:
                    return i
    return len(lines)


def _format_rel_line(rel: Relationship) -> str:
    """Format a single relationship as a D2 arrow line."""
    line = f"{rel.source} -> {rel.target}"
    if rel.label:
        line += f": {rel.label}"
    if rel.style_class:
        if not rel.label:
            line += ":"
        line += f" {{ class: {rel.style_class} }}"
    return line


def generate_midlevel_d2(
    source_lines: list[str],
    relationships: list[Relationship],
    package_ids: set[str],
) -> str:
    """Generate D2 source for the mid-level diagram.

    Copies all package definitions verbatim, keeps intra-package relationships,
    and replaces cross-package relationships with collapsed package-level arrows
    that carry tooltip text listing the underlying class-to-class connections.
    """
    rel_start = _find_relationships_start(source_lines)

    # Copy everything before the Relationships section.
    output_lines = list(source_lines[:rel_start])

    # Inject a larger font size after the direction line for readability.
    for idx, line in enumerate(output_lines):
        if line.strip() == "direction: down":
            output_lines.insert(idx + 1, "style.font-size: 22")
            break

    # Trim trailing blank lines.
    while output_lines and not output_lines[-1].strip():
        output_lines.pop()
    output_lines.append("")

    # Section header.
    sep = "# " + "\u2550" * 45
    output_lines.append(sep)
    output_lines.append("#  Relationships")
    output_lines.append(sep)
    output_lines.append("")

    intra_rels, _ = classify_relationships(relationships, package_ids)

    # Intra-package relationships (verbatim).
    if intra_rels:
        output_lines.append("# --- intra-package (unchanged) ---")
        for rel in intra_rels:
            output_lines.append(_format_rel_line(rel))
        output_lines.append("")

    # Cross-package arrows (collapsed with tooltip).
    midlevel_arrows = build_midlevel_arrows(relationships, package_ids)
    if midlevel_arrows:
        output_lines.append("# --- cross-package (collapsed) ---")
        for arrow in midlevel_arrows:
            count = len(arrow.details)
            label = f"{count} connection{'s' if count != 1 else ''}"
            style = _pick_style_class(arrow.style_classes)

            tooltip_text = "\\n".join(arrow.details)

            parts = [f'{arrow.source_pkg} -> {arrow.target_pkg}: "{label}"']
            props: list[str] = []
            if style:
                props.append(f"class: {style}")
            props.append(f'tooltip: "{tooltip_text}"')
            parts.append(" { " + "; ".join(props) + " }")

            output_lines.append("".join(parts))
        output_lines.append("")

    return "\n".join(output_lines)


def generate_midlevel_html(
    svg_path: Path,
    detail_svg_path: str,
    arrows: list[MidlevelArrow],
) -> str:
    """Generate an HTML page with the mid-level SVG and JS arrow tooltips.

    Tooltip data is embedded as a JSON lookup keyed by arrow label text.
    JavaScript finds matching ``<text>`` elements in the SVG and attaches
    hover handlers.
    """
    svg_content = svg_path.read_text()

    tooltip_map: dict[str, str] = {}
    for arrow in arrows:
        count = len(arrow.details)
        label = f"{count} connection{'s' if count != 1 else ''}"
        detail_text = "\n".join(arrow.details)
        # Disambiguate if multiple arrows share the same count.
        key = label
        suffix = 2
        while key in tooltip_map:
            key = f"{label} ({suffix})"
            suffix += 1
        tooltip_map[key] = (
            f"{arrow.source_pkg} \u2192 {arrow.target_pkg}\n{detail_text}"
        )

    tooltip_json = json.dumps(tooltip_map, ensure_ascii=False)

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>agentrelay \u2014 Mid-Level Diagram</title>
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
  #tooltip {{
    display: none;
    position: fixed;
    background: #1a1a2e;
    color: #e0e0e0;
    padding: 10px 14px;
    border-radius: 6px;
    font-size: 13px;
    line-height: 1.5;
    max-width: 480px;
    pointer-events: none;
    z-index: 1000;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  }}
  #tooltip .tip-title {{
    font-weight: 600;
    color: #fff;
    margin-bottom: 4px;
  }}
  #tooltip .tip-detail {{
    color: #b0b0c0;
  }}
</style>
</head>
<body>
<h1>Mid-Level Diagram</h1>
<p class="subtitle">
  Full package internals with collapsed cross-package arrows.
  Hover over a cross-package arrow label to see the underlying connections.
  <a href="{detail_svg_path}">View full detail diagram</a>.
  Use Ctrl+scroll to zoom.
</p>
<div class="svg-container">
{svg_content}
</div>
<div id="tooltip"></div>
<script>
(function() {{
  var TOOLTIPS = {tooltip_json};

  var tooltip = document.getElementById('tooltip');
  var svgEl = document.querySelector('.svg-container svg');
  if (!svgEl) return;

  // Find text elements whose content matches a tooltip key.
  var textEls = svgEl.querySelectorAll('text');
  textEls.forEach(function(textEl) {{
    var content = textEl.textContent.trim();
    if (!TOOLTIPS[content]) return;

    var target = textEl.closest('g') || textEl;
    target.style.cursor = 'pointer';

    target.addEventListener('mouseenter', function(e) {{
      var detail = TOOLTIPS[content];
      var lines = detail.split('\\n');
      var title = lines[0];
      var connections = lines.slice(1);
      tooltip.innerHTML =
        '<div class="tip-title">' + escapeHtml(title) + '</div>' +
        '<div class="tip-detail">' + connections.map(escapeHtml).join('<br>') + '</div>';
      tooltip.style.display = 'block';
      positionTooltip(e);
    }});

    target.addEventListener('mousemove', positionTooltip);

    target.addEventListener('mouseleave', function() {{
      tooltip.style.display = 'none';
    }});
  }});

  function positionTooltip(e) {{
    var pad = 12;
    var x = e.clientX + pad;
    var y = e.clientY + pad;
    var rect = tooltip.getBoundingClientRect();
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
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }}
}})();
</script>
</body>
</html>"""


def generate_midlevel_grid_html(
    packages: list[Package],
    package_svgs: dict[str, str],
    arrows: list[MidlevelArrow],
    detail_svg_path: str,
) -> str:
    """Generate midlevel HTML using per-package SVGs in a CSS column layout.

    Instead of one monolithic D2-rendered SVG (which ELK lays out too wide),
    this arranges individually-rendered package SVGs in a single-column CSS
    layout with cross-package connections shown as interactive text.
    """
    import base64

    # Build per-package connection summaries.
    pkg_connections: dict[str, list[str]] = {p.id: [] for p in packages}
    for arrow in arrows:
        for detail in arrow.details:
            pkg_connections[arrow.source_pkg].append(
                f"\u2192 {arrow.target_pkg}: {detail}"
            )
            pkg_connections[arrow.target_pkg].append(
                f"\u2190 {arrow.source_pkg}: {detail}"
            )

    # Build package label lookup.
    pkg_labels = {p.id: p.label for p in packages}

    # Build package cards HTML.
    cards_html_parts: list[str] = []
    for pkg in packages:
        if pkg.id not in package_svgs:
            continue
        svg_b64 = base64.b64encode(package_svgs[pkg.id].encode("utf-8")).decode("ascii")
        conns = pkg_connections.get(pkg.id, [])
        conn_html = ""
        if conns:
            conn_items = "\n".join(
                f"          <li>{_escape_html(c)}</li>" for c in conns
            )
            conn_html = f"""
        <details class="pkg-connections">
          <summary>{len(conns)} cross-package connection{"s" if len(conns) != 1 else ""}</summary>
          <ul>
{conn_items}
          </ul>
        </details>"""

        cards_html_parts.append(f"""
      <div class="pkg-card" id="pkg-{pkg.id}">
        <div class="pkg-header">{_escape_html(pkg.label)}</div>
        <div class="pkg-svg">
          <img src="data:image/svg+xml;base64,{svg_b64}" alt="{_escape_html(pkg.label)}">
        </div>{conn_html}
      </div>""")

    cards_html = "\n".join(cards_html_parts)

    # Build cross-package connections summary table.
    conn_rows: list[str] = []
    for arrow in arrows:
        count = len(arrow.details)
        details_text = "<br>".join(_escape_html(d) for d in arrow.details)
        conn_rows.append(
            f"        <tr>"
            f"<td>{_escape_html(pkg_labels.get(arrow.source_pkg, arrow.source_pkg))}</td>"
            f"<td>{_escape_html(pkg_labels.get(arrow.target_pkg, arrow.target_pkg))}</td>"
            f"<td>{count}</td>"
            f"<td class='detail-cell'>{details_text}</td>"
            f"</tr>"
        )
    conn_table_html = "\n".join(conn_rows)

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>agentrelay \u2014 Mid-Level Diagram</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 20px;
    background: #f5f5f5;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }}
  h1 {{
    font-size: 18px;
    color: #333;
    margin: 0 0 4px 0;
  }}
  .subtitle {{
    font-size: 13px;
    color: #666;
    margin-bottom: 16px;
  }}
  .pkg-grid {{
    display: flex;
    flex-direction: column;
    gap: 16px;
    max-width: 1400px;
    margin: 0 auto;
  }}
  .pkg-card {{
    background: #fff;
    border: 1px solid #ddd;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }}
  .pkg-header {{
    font-weight: 600;
    font-size: 15px;
    color: #333;
    padding: 10px 16px;
    background: #f8f8f8;
    border-bottom: 1px solid #e0e0e0;
  }}
  .pkg-svg {{
    padding: 8px;
    overflow-x: auto;
    text-align: center;
  }}
  .pkg-svg img {{
    max-width: 100%;
    height: auto;
  }}
  .pkg-connections {{
    padding: 8px 16px 12px;
    border-top: 1px solid #f0f0f0;
    font-size: 13px;
    color: #555;
  }}
  .pkg-connections summary {{
    cursor: pointer;
    font-weight: 500;
    color: #444;
    padding: 4px 0;
  }}
  .pkg-connections ul {{
    margin: 6px 0 0 0;
    padding-left: 20px;
    line-height: 1.6;
  }}
  .connections-section {{
    max-width: 1400px;
    margin: 32px auto 0;
    background: #fff;
    border: 1px solid #ddd;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }}
  .connections-section h2 {{
    font-size: 15px;
    color: #333;
    padding: 10px 16px;
    margin: 0;
    background: #f8f8f8;
    border-bottom: 1px solid #e0e0e0;
  }}
  .connections-section table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }}
  .connections-section th,
  .connections-section td {{
    padding: 8px 12px;
    text-align: left;
    border-bottom: 1px solid #f0f0f0;
  }}
  .connections-section th {{
    background: #fafafa;
    font-weight: 600;
    color: #555;
  }}
  .detail-cell {{
    color: #666;
    line-height: 1.5;
  }}
</style>
</head>
<body>
<h1>Mid-Level Diagram</h1>
<p class="subtitle">
  Full package internals with cross-package connections.
  Each package is rendered individually for readable layout.
  <a href="{detail_svg_path}">View full detail diagram</a>.
</p>
<div class="pkg-grid">
{cards_html}
</div>
<div class="connections-section">
  <h2>Cross-Package Connections</h2>
  <table>
    <thead>
      <tr><th>From</th><th>To</th><th>#</th><th>Details</th></tr>
    </thead>
    <tbody>
{conn_table_html}
    </tbody>
  </table>
</div>
</body>
</html>"""


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


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


def generate_midlevel(input_path: Path, output_path: Path) -> list[MidlevelArrow]:
    """Read the detail diagram and write the mid-level diagram.

    Returns the list of collapsed arrows (needed for HTML generation).
    """
    source = input_path.read_text()
    source_lines = source.splitlines()

    packages = parse_packages(source_lines)
    package_ids = {pkg.id for pkg in packages}
    relationships = parse_relationships(source_lines)

    output = generate_midlevel_d2(source_lines, relationships, package_ids)
    output_path.write_text(output)

    return build_midlevel_arrows(relationships, package_ids)


_DEFAULT_OUTPUTS = {
    "overview": Path("docs/diagram-overview.d2"),
    "midlevel": Path("docs/diagram-midlevel.d2"),
    "package-svgs": Path("docs/diagram-overview.d2"),
}

_PKG_DETAIL_DIR = Path("docs/pkg-detail")


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate derived diagrams from the detail D2 diagram.",
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
        default=None,
        help="Path to write output (default depends on --mode)",
    )
    parser.add_argument(
        "--mode",
        choices=["overview", "midlevel", "package-svgs"],
        default="overview",
        help="Diagram mode: overview (default), midlevel, or package-svgs.",
    )
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Only generate HTML wrapper (SVG must already exist).",
    )
    args = parser.parse_args(argv)

    if args.output is None:
        args.output = _DEFAULT_OUTPUTS[args.mode]

    if not args.input.exists():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    svg_path = args.output.with_suffix(".svg")
    html_path = args.output.with_suffix(".html")

    if args.mode == "package-svgs":
        # Generate per-package D2 files, render to SVG, then regenerate
        # overview HTML with embedded graphical popups.
        if not svg_path.exists():
            print(f"Error: overview SVG not found: {svg_path}", file=sys.stderr)
            print(
                "Run overview mode first to generate the overview SVG.", file=sys.stderr
            )
            sys.exit(1)

        d2_files = generate_package_d2_files(args.input, _PKG_DETAIL_DIR)
        print(f"Generated {len(d2_files)} per-package D2 files in {_PKG_DETAIL_DIR}")

        pkg_svgs = render_package_svgs(d2_files)
        print(f"Rendered {len(pkg_svgs)} per-package SVGs")

        # Build overview HTML with graphical popups.
        source_lines = args.input.read_text().splitlines()
        pkg_details = parse_package_details(source_lines)
        relationships = parse_relationships(source_lines)
        packages = parse_packages(source_lines)
        package_ids = {p.id for p in packages}
        ml_arrows = build_midlevel_arrows(relationships, package_ids)
        html = generate_overview_html(
            svg_path,
            detail_svg_path="diagram.svg",
            package_details=pkg_details,
            midlevel_arrows=ml_arrows,
            package_svgs=pkg_svgs,
        )
        html_path.write_text(html)
        print(f"Overview HTML with graphical popups written to {html_path}")

    elif args.mode == "overview":
        if args.html_only:
            if not svg_path.exists():
                print(f"Error: SVG not found: {svg_path}", file=sys.stderr)
                sys.exit(1)
            # Parse full detail for rich tooltips.
            source_lines = args.input.read_text().splitlines()
            pkg_details = parse_package_details(source_lines)
            relationships = parse_relationships(source_lines)
            packages = parse_packages(source_lines)
            package_ids = {p.id for p in packages}
            ml_arrows = build_midlevel_arrows(relationships, package_ids)

            # Check for pre-rendered package SVGs.
            pkg_svgs: dict[str, str] | None = None
            if _PKG_DETAIL_DIR.exists():
                pkg_svgs = {}
                for p in packages:
                    svg_file = _PKG_DETAIL_DIR / f"{p.id}.svg"
                    if svg_file.exists():
                        pkg_svgs[p.id] = svg_file.read_text()
                if not pkg_svgs:
                    pkg_svgs = None

            html = generate_overview_html(
                svg_path,
                detail_svg_path="diagram.svg",
                package_details=pkg_details,
                midlevel_arrows=ml_arrows,
                package_svgs=pkg_svgs,
            )
            html_path.write_text(html)
            print(f"Overview HTML written to {html_path}")
            return
        generate_overview(args.input, args.output)
        print(f"Overview diagram written to {args.output}")

    elif args.mode == "midlevel":
        if args.html_only:
            # Re-parse to get arrow data.
            source_lines = args.input.read_text().splitlines()
            packages = parse_packages(source_lines)
            package_ids = {pkg.id for pkg in packages}
            relationships = parse_relationships(source_lines)
            arrows = build_midlevel_arrows(relationships, package_ids)

            # Use grid layout with per-package SVGs if available.
            pkg_svgs: dict[str, str] | None = None
            if _PKG_DETAIL_DIR.exists():
                pkg_svgs = {}
                for p in packages:
                    svg_file = _PKG_DETAIL_DIR / f"{p.id}.svg"
                    if svg_file.exists():
                        pkg_svgs[p.id] = svg_file.read_text()
                if not pkg_svgs:
                    pkg_svgs = None

            if pkg_svgs is not None:
                html = generate_midlevel_grid_html(
                    packages=packages,
                    package_svgs=pkg_svgs,
                    arrows=arrows,
                    detail_svg_path="diagram.svg",
                )
                html_path.write_text(html)
                print(f"Mid-level grid HTML written to {html_path}")
            else:
                if not svg_path.exists():
                    print(f"Error: SVG not found: {svg_path}", file=sys.stderr)
                    sys.exit(1)
                html = generate_midlevel_html(
                    svg_path, detail_svg_path="diagram.svg", arrows=arrows
                )
                html_path.write_text(html)
                print(f"Mid-level HTML written to {html_path}")
            return
        generate_midlevel(args.input, args.output)
        print(f"Mid-level diagram written to {args.output}")


if __name__ == "__main__":
    main()
