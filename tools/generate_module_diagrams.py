"""Extract per-module diagrams from diagram-detailed.d2.

For each top-level module (container) in the detailed diagram, generates a
focused diagram showing:

1. The module's full type definitions (verbatim from the source).
2. Simplified stubs for external types referenced by relationships.
3. Only the relationships that involve this module.

Also generates a ``diagram-modules.d2`` overview showing inter-module
dependency arrows with no internal types.

Usage::

    python -m tools.generate_module_diagrams                    # all modules
    python -m tools.generate_module_diagrams --module task_py   # single module
    python -m tools.generate_module_diagrams --list             # list modules
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Top-level container opening (no leading whitespace).
_CONTAINER_OPEN_RE = re.compile(r"^(\w+)\s*:\s*\"([^\"]+)\"\s*\{")

# Any named node/container definition line: ``  Foo: "Foo <<bar>>" {``
_NODE_DEF_RE = re.compile(r"^(\s+)(\w+)\s*:\s*\"([^\"]+)\"\s*\{")

# Relationship line: ``source -> target: label { class: ... }``
_REL_RE = re.compile(r"^([\w.]+)\s*->\s*([\w.]+)(.*?)$")

# Section divider (thick or thin).
_SECTION_RE = re.compile(r"^#\s*[─═]+")

# Comment line.
_COMMENT_RE = re.compile(r"^\s*#")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ContainerBlock:
    """A top-level D2 container and its full source lines."""

    id: str  # e.g. "task_py", "orchestrator_pkg"
    display: str  # e.g. "task.py", "orchestrator/"
    lines: list[str]  # verbatim source lines (opening brace through closing)
    comment_lines: list[str] = field(default_factory=list)  # preceding section comment


Rel = tuple[str, str, str]  # (source_path, target_path, full_line)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_containers(lines: list[str]) -> list[ContainerBlock]:
    """Extract all top-level container blocks from the diagram source."""
    containers: list[ContainerBlock] = []
    pending_comments: list[str] = []
    i = 0

    while i < len(lines):
        stripped = lines[i].rstrip()

        # Accumulate section comments.
        if _SECTION_RE.match(stripped) or (
            _COMMENT_RE.match(stripped) and not containers
        ):
            pending_comments.append(lines[i])
            i += 1
            continue

        if _COMMENT_RE.match(stripped) and pending_comments:
            pending_comments.append(lines[i])
            i += 1
            continue

        # Top-level container (no leading whitespace).
        m = _CONTAINER_OPEN_RE.match(stripped)
        if m:
            container_id = m.group(1)
            display_name = m.group(2)
            block_lines = [lines[i]]
            depth = stripped.count("{") - stripped.count("}")
            i += 1
            while i < len(lines) and depth > 0:
                s = lines[i].rstrip()
                depth += s.count("{") - s.count("}")
                block_lines.append(lines[i])
                i += 1
            containers.append(
                ContainerBlock(
                    id=container_id,
                    display=display_name,
                    lines=block_lines,
                    comment_lines=pending_comments,
                )
            )
            pending_comments = []
            continue

        # Non-container, non-comment line outside containers: reset comments.
        if stripped:
            pending_comments = []
        i += 1

    return containers


def _parse_relationships(lines: list[str]) -> list[Rel]:
    """Parse all relationship lines from the source."""
    rels: list[Rel] = []
    for line in lines:
        stripped = line.strip()
        if "->" not in stripped or stripped.startswith("#"):
            continue
        m = _REL_RE.match(stripped)
        if m:
            rels.append((m.group(1), m.group(2), stripped))
    return rels


def _top_container(dotted_path: str) -> str:
    """Return the top-level container ID from a dotted path."""
    return dotted_path.split(".")[0]


# ---------------------------------------------------------------------------
# Type label extraction
# ---------------------------------------------------------------------------


def _build_type_labels(containers: list[ContainerBlock]) -> dict[str, str]:
    """Build a mapping from dotted path to display label.

    Walks each container block tracking nesting depth to build correct
    dotted paths for all named nodes.
    """
    labels: dict[str, str] = {}

    for container in containers:
        labels[container.id] = container.display
        path_stack: list[str] = [container.id]
        depth_stack: list[int] = [0]
        current_depth = 0

        for line in container.lines:
            stripped = line.rstrip()

            # Check for named node definition.
            m = _NODE_DEF_RE.match(stripped)
            if m:
                node_id = m.group(2)
                node_label = m.group(3)

                # Pop stack to the correct nesting level.
                opens = stripped.count("{")
                closes = stripped.count("}")
                net = opens - closes

                dotted = ".".join(path_stack) + "." + node_id
                labels[dotted] = node_label

                if net > 0:
                    # This node opens a new nesting level.
                    path_stack.append(node_id)
                    depth_stack.append(current_depth + 1)
                    current_depth += net
                else:
                    current_depth += net
            else:
                current_depth += stripped.count("{") - stripped.count("}")

                # If depth decreased, pop the path stack accordingly.
                while len(path_stack) > 1 and current_depth <= depth_stack[-1]:
                    path_stack.pop()
                    depth_stack.pop()

    return labels


# ---------------------------------------------------------------------------
# Stub generation
# ---------------------------------------------------------------------------


def _build_stub_container(
    container: ContainerBlock,
    type_paths: set[str],
    labels: dict[str, str],
) -> list[str]:
    """Build a simplified stub container showing only referenced types.

    External containers are rendered with reduced opacity so they're
    visually distinct from the focus module.
    """
    # Group type paths by their sub-container path (for nested containers).
    # e.g. "agent_pkg.agent_core_pkg.Agent" -> sub_path="agent_core_pkg", type="Agent"
    # e.g. "task_py.Task" -> sub_path=None, type="Task"
    # e.g. "ops_pkg.git" -> sub_path=None, type="git"

    # Build nested structure: {sub_container_path: [type_id, ...]}
    direct_types: list[str] = []  # types directly in the container
    nested: dict[str, list[str]] = defaultdict(list)  # sub_container -> [types]
    sub_container_labels: dict[str, str] = {}

    for path in sorted(type_paths):
        segments = path.split(".")
        if len(segments) == 2:
            # Direct child: container.Type
            direct_types.append(segments[1])
        elif len(segments) >= 3:
            # Nested: container.sub_container.Type (or deeper)
            sub_id = segments[1]
            type_id = segments[-1]
            sub_dotted = ".".join(segments[:2])
            sub_container_labels[sub_id] = labels.get(sub_dotted, sub_id)
            nested[sub_id].append(type_id)
        # segments == 1 means the container itself is referenced (e.g. ops_pkg.git
        # where git is a sub-module)

    result: list[str] = []
    result.append(f'{container.id}: "{container.display}" {{')
    result.append("  style.opacity: 0.5")

    # Direct types.
    for type_id in direct_types:
        type_dotted = f"{container.id}.{type_id}"
        label = labels.get(type_dotted, type_id)
        result.append(f'  {type_id}: "{label}" {{ shape: class }}')

    # Nested sub-containers.
    for sub_id, types in sorted(nested.items()):
        sub_label = sub_container_labels.get(sub_id, sub_id)
        result.append(f'  {sub_id}: "{sub_label}" {{')
        for type_id in sorted(types):
            type_dotted = f"{container.id}.{sub_id}.{type_id}"
            label = labels.get(type_dotted, type_id)
            result.append(f'    {type_id}: "{label}" {{ shape: class }}')
        result.append("  }")

    result.append("}")
    return result


# ---------------------------------------------------------------------------
# Per-module diagram generation
# ---------------------------------------------------------------------------


def generate_module_diagram(
    module: ContainerBlock,
    all_containers: dict[str, ContainerBlock],
    relationships: list[Rel],
    labels: dict[str, str],
) -> list[str]:
    """Generate a focused diagram for a single module."""
    module_id = module.id

    # Find relationships involving this module.
    relevant_rels: list[str] = []
    external_paths: set[str] = set()

    for src, tgt, line in relationships:
        src_mod = _top_container(src)
        tgt_mod = _top_container(tgt)

        if src_mod == module_id or tgt_mod == module_id:
            relevant_rels.append(line)
            if src_mod != module_id:
                external_paths.add(src)
            if tgt_mod != module_id:
                external_paths.add(tgt)

    # Group external paths by container.
    external_by_container: dict[str, set[str]] = defaultdict(set)
    for path in external_paths:
        container_id = _top_container(path)
        external_by_container[container_id].add(path)

    # Build output.
    output: list[str] = []

    # Module section.
    for comment in module.comment_lines:
        output.append(comment.rstrip())
    output.extend(line.rstrip() for line in module.lines)
    output.append("")

    # External stubs.
    if external_by_container:
        output.append("")
        output.append("# ─── External dependencies ───")
        output.append("")
        for container_id in sorted(external_by_container.keys()):
            if container_id not in all_containers:
                continue
            stub = _build_stub_container(
                all_containers[container_id],
                external_by_container[container_id],
                labels,
            )
            output.extend(stub)
            output.append("")

    # Relationships.
    if relevant_rels:
        output.append("")
        output.append("# ─── Relationships ───")
        output.append("")
        for rel in relevant_rels:
            output.append(rel)

    return output


# ---------------------------------------------------------------------------
# Module-overview diagram
# ---------------------------------------------------------------------------


def generate_overview(
    containers: list[ContainerBlock],
    relationships: list[Rel],
) -> list[str]:
    """Generate an inter-module overview diagram (no internal types)."""
    output: list[str] = []
    output.append("# Module dependency overview")
    output.append("# Auto-generated from diagram-detailed.d2")
    output.append("")

    # Module boxes (no internals).
    for c in containers:
        output.append(f'{c.id}: "{c.display}"')
    output.append("")

    # Inter-module arrows (deduplicated).
    seen: set[tuple[str, str]] = set()
    for src, tgt, _line in relationships:
        src_mod = _top_container(src)
        tgt_mod = _top_container(tgt)
        if src_mod != tgt_mod:
            key = (src_mod, tgt_mod)
            if key not in seen:
                seen.add(key)
                output.append(f"{src_mod} -> {tgt_mod} {{ class: dependency }}")

    return output


# ---------------------------------------------------------------------------
# Friendly module name for filenames
# ---------------------------------------------------------------------------


def _module_filename(container_id: str) -> str:
    """Convert container ID to a diagram filename.

    ``task_py`` -> ``task``
    ``orchestrator_pkg`` -> ``orchestrator``
    ``agent_comm_protocol_pkg`` -> ``agent-comm-protocol``
    ``run_graph_py`` -> ``run-graph``
    """
    name = container_id
    for suffix in ("_pkg", "_py"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name.replace("_", "-")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Extract per-module diagrams from diagram-detailed.d2.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("docs/diagrams/uml/diagram-detailed.d2"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/diagrams/uml/modules"),
    )
    parser.add_argument(
        "--overview-dir",
        type=Path,
        default=Path("docs/diagrams/uml"),
    )
    parser.add_argument(
        "--module",
        action="append",
        dest="modules",
        help="Generate a specific module (repeatable; default: all)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available modules and exit.",
    )
    parser.add_argument(
        "--preamble",
        action="append",
        dest="preamble",
        metavar="LINE",
        help="D2 global line to prepend (repeatable).",
    )
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    source = args.input.read_text()
    lines = source.splitlines()

    containers = _parse_containers(lines)
    container_map = {c.id: c for c in containers}
    relationships = _parse_relationships(lines)
    labels = _build_type_labels(containers)

    if args.list:
        for c in containers:
            fname = _module_filename(c.id)
            print(f"  {c.id:35s} -> diagram-{fname}.d2  ({c.display})")
        return

    selected = args.modules or [c.id for c in containers]

    args.output_dir.mkdir(parents=True, exist_ok=True)

    preamble = args.preamble or []

    for module_id in selected:
        if module_id not in container_map:
            print(f"Warning: unknown module '{module_id}', skipping", file=sys.stderr)
            continue

        module = container_map[module_id]
        diagram_lines = generate_module_diagram(
            module, container_map, relationships, labels
        )

        if preamble:
            diagram_lines = preamble + [""] + diagram_lines

        fname = _module_filename(module_id)
        out_path = args.output_dir / f"diagram-{fname}.d2"
        out_path.write_text("\n".join(diagram_lines) + "\n")
        print(f"Generated {out_path}")

    # Overview diagram.
    overview_lines = generate_overview(containers, relationships)
    if preamble:
        overview_lines = preamble + [""] + overview_lines
    overview_path = args.overview_dir / "diagram-modules.d2"
    overview_path.write_text("\n".join(overview_lines) + "\n")
    print(f"Generated {overview_path}")


if __name__ == "__main__":
    main()
