"""Graph index for name-based graph selection.

Scans a directory tree for graph YAML files, enforces name uniqueness,
and resolves graph references (by name or path) to absolute file paths.

Usage::

    index = GraphIndex(Path("graphs/"))
    path = index.resolve("quick-chained")       # name-based
    path = index.resolve("smoke/quick.yaml")     # path-based (validated)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class GraphEntry:
    """A single graph registered in the index.

    Attributes:
        name: Graph name from the YAML ``name:`` field.
        category: Subdirectory relative to the graph root (e.g. ``"smoke"``).
            Empty string for files at the root level.
        path: Absolute resolved path to the YAML file.
    """

    name: str
    category: str
    path: Path


class DuplicateGraphNameError(ValueError):
    """Raised when two or more graph YAML files declare the same ``name:``."""


def _is_path_reference(graph_ref: str) -> bool:
    """Return ``True`` if *graph_ref* looks like a file path."""
    return "/" in graph_ref or graph_ref.endswith(".yaml")


def _read_graph_name(yaml_path: Path) -> str | None:
    """Read the ``name:`` field from a graph YAML file.

    Returns ``None`` (with a warning to stderr) when the file cannot be
    parsed, is not a mapping, or has no ``name:`` field.
    """
    try:
        raw = yaml.safe_load(yaml_path.read_text())
    except (yaml.YAMLError, OSError) as exc:
        print(f"Warning: skipping {yaml_path}: {exc}", file=sys.stderr)
        return None

    if not isinstance(raw, dict):
        print(
            f"Warning: skipping {yaml_path}: expected a YAML mapping",
            file=sys.stderr,
        )
        return None

    name = raw.get("name")
    if not name:
        print(
            f"Warning: skipping {yaml_path}: no 'name' field",
            file=sys.stderr,
        )
        return None

    return str(name)


def _extract_category(graph_dir: Path, yaml_path: Path) -> str:
    """Derive the category from the relative path between dir and file.

    Returns the parent directory portion (e.g. ``"smoke"``,
    ``"roles/experiments"``) or ``""`` for files directly in *graph_dir*.
    """
    relative_parent = yaml_path.resolve().relative_to(graph_dir.resolve()).parent
    return str(relative_parent) if str(relative_parent) != "." else ""


def _scan_directory(graph_dir: Path) -> list[GraphEntry]:
    """Recursively scan *graph_dir* for ``.yaml`` files and build entries.

    Raises:
        DuplicateGraphNameError: If two or more files share the same
            ``name:`` value.  The error message lists every conflict.
    """
    entries: list[GraphEntry] = []
    seen: dict[str, list[Path]] = {}

    for yaml_path in sorted(graph_dir.rglob("*.yaml")):
        name = _read_graph_name(yaml_path)
        if name is None:
            continue
        resolved = yaml_path.resolve()
        category = _extract_category(graph_dir, yaml_path)
        entries.append(GraphEntry(name=name, category=category, path=resolved))
        seen.setdefault(name, []).append(resolved)

    duplicates = {n: paths for n, paths in seen.items() if len(paths) > 1}
    if duplicates:
        lines = ["Duplicate graph names found:"]
        for name, paths in sorted(duplicates.items()):
            paths_str = ", ".join(str(p) for p in paths)
            lines.append(f"  '{name}': {paths_str}")
        raise DuplicateGraphNameError("\n".join(lines))

    return entries


class GraphIndex:
    """Index of graph YAML files scanned from a directory.

    Scans *graph_dir* recursively for ``.yaml`` files, reads the
    ``name:`` field from each, and builds a name-to-path mapping.
    Duplicate names are rejected at construction time.

    Args:
        graph_dir: Directory to scan.

    Raises:
        FileNotFoundError: If *graph_dir* does not exist or is not a
            directory.
        DuplicateGraphNameError: If two files share the same ``name:``.
    """

    def __init__(self, graph_dir: Path) -> None:
        if not graph_dir.is_dir():
            raise FileNotFoundError(f"Graph directory not found: {graph_dir}")
        entry_list = _scan_directory(graph_dir)
        self._entries = tuple(sorted(entry_list, key=lambda e: e.name))
        self._by_name: dict[str, Path] = {e.name: e.path for e in self._entries}
        self._by_path: set[Path] = {e.path for e in self._entries}

    @property
    def entries(self) -> tuple[GraphEntry, ...]:
        """All indexed graph entries, sorted by name."""
        return self._entries

    def resolve(self, graph_ref: str) -> Path:
        """Resolve a graph reference (name or path) to an absolute path.

        If *graph_ref* contains ``/`` or ends with ``.yaml`` it is
        treated as a file path and validated against the index.
        Otherwise it is treated as a graph name.

        Args:
            graph_ref: Graph name (e.g. ``"quick-chained"``) or path
                (e.g. ``"graphs/smoke/quick_chained.yaml"``).

        Returns:
            Resolved absolute path to the graph YAML file.

        Raises:
            KeyError: If the name is not found in the index.
            ValueError: If a path is not present in the index.
        """
        if _is_path_reference(graph_ref):
            resolved = Path(graph_ref).resolve()
            if resolved not in self._by_path:
                raise ValueError(
                    f"Graph path not found in index: {resolved}\n"
                    f"Check that the file exists under the --graph-dir directory."
                )
            return resolved

        if graph_ref not in self._by_name:
            available = ", ".join(sorted(self._by_name.keys()))
            raise KeyError(
                f"Graph name '{graph_ref}' not found in index.\n"
                f"Available graphs: {available}"
            )
        return self._by_name[graph_ref]
