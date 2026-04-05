"""Output manifest data model and serialization.

Agents declare what files they created, modified, or deleted via an
output manifest (``outputs.json``) in their signal directory.  This
module defines the data types and conversion functions.

Constants:
    OUTPUT_MANIFEST_SCHEMA_VERSION: Current schema version for output manifests.
    OUTPUT_MANIFEST_FILENAME: Filename for the output manifest signal file.

Classes:
    OutputAction: Action performed on a file (created, modified, deleted).
    OutputEntry: A single file entry in the output manifest.
    OutputManifest: The complete output manifest.

Functions:
    output_manifest_to_dict: Serialize an OutputManifest to a JSON-compatible dict.
    output_manifest_from_dict: Deserialize a dict to an OutputManifest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

OUTPUT_MANIFEST_SCHEMA_VERSION = "1"
"""Current schema version for output manifests."""

OUTPUT_MANIFEST_FILENAME = "outputs.json"
"""Filename for the output manifest in the signal directory."""


class OutputAction(str, Enum):
    """Action performed on a file by the agent.

    Attributes:
        CREATED: File was newly created.
        MODIFIED: Existing file was modified.
        DELETED: Existing file was deleted.
    """

    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"


@dataclass(frozen=True)
class OutputEntry:
    """A single file entry in the output manifest.

    Attributes:
        path: File path relative to the repository root.
        action: What the agent did to this file.
        category: Semantic category (e.g. ``"stubs"``, ``"tests"``).
    """

    path: Path
    action: OutputAction
    category: str


@dataclass
class OutputManifest:
    """Output manifest declaring what files an agent produced.

    Not frozen because entries are appended incrementally via
    :meth:`~agentrelay.agent_sdk.TaskHelper.declare_output`.

    Attributes:
        schema_version: Schema version string.
        files: List of output file entries.
    """

    schema_version: str = OUTPUT_MANIFEST_SCHEMA_VERSION
    files: list[OutputEntry] = field(default_factory=list)


def output_manifest_to_dict(manifest: OutputManifest) -> dict[str, Any]:
    """Serialize an :class:`OutputManifest` to a JSON-compatible dict.

    Args:
        manifest: Manifest to serialize.

    Returns:
        Nested dict matching the ``outputs.json`` schema.
    """
    return {
        "schema_version": manifest.schema_version,
        "files": [
            {
                "path": str(entry.path),
                "action": entry.action.value,
                "category": entry.category,
            }
            for entry in manifest.files
        ],
    }


def output_manifest_from_dict(data: dict[str, Any]) -> OutputManifest:
    """Deserialize a dict (from JSON) to an :class:`OutputManifest`.

    Args:
        data: Dict parsed from ``outputs.json``.

    Returns:
        Deserialized manifest.
    """
    files_data = data.get("files", [])
    return OutputManifest(
        schema_version=str(data.get("schema_version", OUTPUT_MANIFEST_SCHEMA_VERSION)),
        files=[
            OutputEntry(
                path=Path(f["path"]),
                action=OutputAction(f["action"]),
                category=f["category"],
            )
            for f in files_data
        ],
    )


__all__ = [
    "OUTPUT_MANIFEST_FILENAME",
    "OUTPUT_MANIFEST_SCHEMA_VERSION",
    "OutputAction",
    "OutputEntry",
    "OutputManifest",
    "output_manifest_from_dict",
    "output_manifest_to_dict",
]
