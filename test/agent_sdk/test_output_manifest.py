"""Tests for agentrelay.agent_sdk.output_manifest."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from agentrelay.agent_sdk.output_manifest import (
    OutputAction,
    OutputEntry,
    OutputManifest,
    output_manifest_from_dict,
    output_manifest_to_dict,
)

# -- OutputAction --


class TestOutputAction:
    def test_values(self) -> None:
        assert OutputAction.CREATED.value == "created"
        assert OutputAction.MODIFIED.value == "modified"
        assert OutputAction.DELETED.value == "deleted"

    def test_is_string_enum(self) -> None:
        assert OutputAction("created") == OutputAction.CREATED
        assert OutputAction.CREATED == "created"

    def test_all_values_are_strings(self) -> None:
        for member in OutputAction:
            assert isinstance(member.value, str)


# -- OutputEntry --


class TestOutputEntry:
    def test_is_frozen(self) -> None:
        entry = OutputEntry(
            path=Path("src/foo.py"), action=OutputAction.CREATED, category="stubs"
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            entry.path = Path("other.py")  # type: ignore[misc]

    def test_fields(self) -> None:
        entry = OutputEntry(
            path=Path("src/foo.py"),
            action=OutputAction.MODIFIED,
            category="implementation",
        )
        assert entry.path == Path("src/foo.py")
        assert entry.action == OutputAction.MODIFIED
        assert entry.category == "implementation"


# -- OutputManifest --


class TestOutputManifest:
    def test_default(self) -> None:
        manifest = OutputManifest()
        assert manifest.schema_version == "1"
        assert manifest.files == []

    def test_mutable_files(self) -> None:
        manifest = OutputManifest()
        manifest.files.append(
            OutputEntry(
                path=Path("src/foo.py"), action=OutputAction.CREATED, category="stubs"
            )
        )
        assert len(manifest.files) == 1


# -- Serialization --


class TestSerialization:
    def test_to_dict_empty(self) -> None:
        result = output_manifest_to_dict(OutputManifest())
        assert result == {"schema_version": "1", "files": []}

    def test_to_dict_with_entries(self) -> None:
        manifest = OutputManifest(
            files=[
                OutputEntry(
                    path=Path("src/foo.py"),
                    action=OutputAction.CREATED,
                    category="stubs",
                ),
                OutputEntry(
                    path=Path("src/bar.py"),
                    action=OutputAction.MODIFIED,
                    category="implementation",
                ),
            ]
        )
        result = output_manifest_to_dict(manifest)
        assert result["schema_version"] == "1"
        assert len(result["files"]) == 2
        assert result["files"][0] == {
            "path": "src/foo.py",
            "action": "created",
            "category": "stubs",
        }
        assert result["files"][1] == {
            "path": "src/bar.py",
            "action": "modified",
            "category": "implementation",
        }

    def test_from_dict_empty(self) -> None:
        manifest = output_manifest_from_dict({"schema_version": "1", "files": []})
        assert manifest.schema_version == "1"
        assert manifest.files == []

    def test_from_dict_round_trip(self) -> None:
        original = OutputManifest(
            files=[
                OutputEntry(
                    path=Path("src/foo.py"),
                    action=OutputAction.CREATED,
                    category="stubs",
                ),
                OutputEntry(
                    path=Path("docs/spec.md"),
                    action=OutputAction.DELETED,
                    category="spec",
                ),
            ]
        )
        restored = output_manifest_from_dict(output_manifest_to_dict(original))
        assert restored.schema_version == original.schema_version
        assert len(restored.files) == len(original.files)
        for orig, rest in zip(original.files, restored.files):
            assert orig.path == rest.path
            assert orig.action == rest.action
            assert orig.category == rest.category

    def test_from_dict_creates_enum(self) -> None:
        data = {
            "schema_version": "1",
            "files": [{"path": "src/foo.py", "action": "created", "category": "stubs"}],
        }
        manifest = output_manifest_from_dict(data)
        assert manifest.files[0].action is OutputAction.CREATED
