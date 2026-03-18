"""Composable D2 diagram filters.

Each filter is a pure function ``list[str] -> list[str]`` that removes or
transforms lines from a D2 source.  Filters can be composed by chaining::

    lines = filter_private_nodes(lines)
    lines = collapse_impl_packages(lines)

Filters:
    filter_private_nodes: Strip nodes whose identifier starts with ``_``.
    collapse_impl_packages: Replace ``*_impl_pkg`` contents with a placeholder.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Private-node filter
# ---------------------------------------------------------------------------

# Matches a node definition whose identifier starts with ``_``.
_PRIVATE_NODE_RE = re.compile(r"^(\s*)_\w+\s*:")

# Matches a relationship line containing a ``_``-prefixed identifier segment.
_PRIVATE_REL_RE = re.compile(r"(?:^|\.|\s)_\w+")


def filter_private_nodes(lines: list[str]) -> list[str]:
    """Remove ``_``-prefixed node blocks and their relationship lines.

    Node blocks are detected by matching a definition line whose identifier
    starts with ``_``, then tracking brace depth to skip the entire block
    (including nested content). Relationship lines referencing any
    ``_``-prefixed identifier segment are also removed.
    """
    result: list[str] = []
    skip_depth = 0

    for line in lines:
        stripped = line.rstrip()

        if skip_depth > 0:
            skip_depth += stripped.count("{") - stripped.count("}")
            if skip_depth <= 0:
                skip_depth = 0
            continue

        if _PRIVATE_NODE_RE.match(stripped):
            if "{" in stripped:
                skip_depth = stripped.count("{") - stripped.count("}")
                if skip_depth <= 0:
                    skip_depth = 0
            continue

        if "->" in stripped and _PRIVATE_REL_RE.search(stripped):
            continue

        result.append(line)

    return result


# ---------------------------------------------------------------------------
# Implementation-package collapse filter
# ---------------------------------------------------------------------------

# Matches an impl_pkg container opening: ``  agent_impl_pkg: "implementations/" {``
_IMPL_PKG_RE = re.compile(r"^(\s*)(\w+_impl_pkg)\s*:\s*\"([^\"]*)\"\s*\{")

# Matches a nested class/node definition inside an impl_pkg (to count members).
_MEMBER_DEF_RE = re.compile(r"^\s+\w+\s*:\s*\"[^\"]*\"\s*\{")


def _count_members(lines: list[str], start: int) -> int:
    """Count top-level member definitions inside an impl_pkg block.

    Scans forward from the line *after* the container opening (``start``),
    counting lines that match the member definition pattern at the immediate
    nesting level (depth == 1 relative to the container).
    """
    count = 0
    depth = 1

    for line in lines[start:]:
        stripped = line.rstrip()

        # Check for member definition *before* updating depth, so we catch
        # members at depth 1 (their opening ``{`` hasn't been counted yet).
        if depth == 1 and _MEMBER_DEF_RE.match(line):
            count += 1

        depth += stripped.count("{") - stripped.count("}")

        if depth <= 0:
            break

    return count


def collapse_impl_packages(lines: list[str]) -> list[str]:
    """Replace ``*_impl_pkg`` contents with a count placeholder.

    For each container whose D2 identifier ends with ``_impl_pkg``:

    1. Keep the container opening line.
    2. Replace all contents with a single ``"(N classes hidden)"`` note.
    3. Keep the container closing brace.
    4. Strip relationship lines referencing nodes inside any impl_pkg.

    The impl_pkg identifiers are collected in a first pass so that the
    relationship filter knows which dotted paths to strip.
    """
    # First pass: collect impl_pkg identifiers and their member counts.
    impl_pkg_ids: set[str] = set()
    impl_members: dict[str, int] = {}
    i = 0
    while i < len(lines):
        match = _IMPL_PKG_RE.match(lines[i].rstrip())
        if match:
            pkg_id = match.group(2)
            impl_pkg_ids.add(pkg_id)
            impl_members[pkg_id] = _count_members(lines, i + 1)
        i += 1

    if not impl_pkg_ids:
        return lines

    # Second pass: collapse contents, filter relationships.
    result: list[str] = []
    skip_depth = 0
    current_impl_id: str | None = None

    for line in lines:
        stripped = line.rstrip()

        # Inside an impl_pkg block — skip contents until closing brace.
        if skip_depth > 0:
            skip_depth += stripped.count("{") - stripped.count("}")
            if skip_depth <= 0:
                # Emit placeholder + closing brace.
                assert current_impl_id is not None
                count = impl_members.get(current_impl_id, 0)
                indent = "  " * 2  # typical nesting for impl_pkg contents
                noun = "class" if count == 1 else "classes"
                result.append(f'{indent}"({count} {noun} hidden)"')
                result.append(stripped)  # closing brace line
                skip_depth = 0
                current_impl_id = None
            continue

        # Check if this line opens an impl_pkg container.
        match = _IMPL_PKG_RE.match(stripped)
        if match and match.group(2) in impl_pkg_ids:
            current_impl_id = match.group(2)
            result.append(line)  # keep the opening line
            skip_depth = stripped.count("{") - stripped.count("}")
            continue

        # Filter relationship lines referencing nodes inside any impl_pkg.
        if "->" in stripped:
            if _references_impl_node(stripped, impl_pkg_ids):
                continue

        result.append(line)

    return result


def _references_impl_node(rel_line: str, impl_pkg_ids: set[str]) -> bool:
    """Check if a relationship line references a node inside an impl_pkg.

    A dotted path like ``task_runner_pkg.task_runner_impl_pkg.WorktreeTaskPreparer``
    references a node inside ``task_runner_impl_pkg`` if the path contains an
    impl_pkg ID followed by at least one more segment (the actual node).
    """
    for pkg_id in impl_pkg_ids:
        # Pattern: pkg_id.SomeNode (node inside the impl package)
        pattern = pkg_id + "."
        if pattern in rel_line:
            return True
    return False
