"""Tests for agentrelay.agent_comm_protocol.manifest — TaskManifest and builders."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentrelay.agent_comm_protocol.manifest import (
    MANIFEST_SCHEMA_VERSION,
    DependencyInfo,
    InputFileInfo,
    TaskManifest,
    build_manifest,
    manifest_to_dict,
)
from agentrelay.task import AgentRole, Task, TaskPaths


def _minimal_task(**overrides: object) -> Task:
    """Create a minimal Task with sensible defaults."""
    kwargs: dict[str, object] = {"id": "my_task", "role": AgentRole.GENERIC}
    kwargs.update(overrides)
    return Task(**kwargs)  # type: ignore[arg-type]


class TestDependencyInfo:
    """Tests for DependencyInfo."""

    def test_construction(self) -> None:
        info = DependencyInfo(description="Write the greet module")
        assert info.description == "Write the greet module"

    def test_none_description(self) -> None:
        info = DependencyInfo(description=None)
        assert info.description is None

    def test_frozen(self) -> None:
        info = DependencyInfo(description="x")
        with pytest.raises(AttributeError):
            info.description = "y"  # type: ignore[misc]


class TestTaskManifest:
    """Tests for TaskManifest construction."""

    def test_construction(self) -> None:
        manifest = TaskManifest(
            schema_version="1",
            task_id="t1",
            role=AgentRole.TEST_WRITER,
            description="Write tests",
            src_paths=(Path("src/a.py"),),
            test_paths=(Path("test/test_a.py"),),
            spec_path=None,
            branch_name="graph/demo/t1",
            integration_branch="graph/demo",
            attempt_num=0,
            graph_name="demo",
            dependencies={},
        )
        assert manifest.task_id == "t1"
        assert manifest.role == AgentRole.TEST_WRITER

    def test_frozen(self) -> None:
        manifest = TaskManifest(
            schema_version="1",
            task_id="t1",
            role=AgentRole.GENERIC,
            description=None,
            src_paths=(),
            test_paths=(),
            spec_path=None,
            branch_name="b",
            integration_branch="main",
            attempt_num=0,
            graph_name=None,
            dependencies={},
        )
        with pytest.raises(AttributeError):
            manifest.task_id = "t2"  # type: ignore[misc]


class TestBuildManifest:
    """Tests for build_manifest."""

    def test_minimal_task(self) -> None:
        """Builds manifest from a minimal task with no deps or paths."""
        task = _minimal_task()
        manifest = build_manifest(
            task=task,
            branch_name="graph/demo/my_task",
            integration_branch="graph/demo",
            graph_name="demo",
            attempt_num=0,
            dependency_descriptions={},
        )
        assert manifest.schema_version == MANIFEST_SCHEMA_VERSION
        assert manifest.task_id == "my_task"
        assert manifest.role == AgentRole.GENERIC
        assert manifest.src_paths == ()
        assert manifest.test_paths == ()
        assert manifest.spec_path is None
        assert manifest.dependencies == {}

    def test_task_with_paths(self) -> None:
        """Paths are extracted from TaskPaths."""
        task = _minimal_task(
            role=AgentRole.TEST_WRITER,
            paths=TaskPaths(
                src=(Path("src/greet.py"),),
                test=(Path("test/test_greet.py"),),
                spec=Path("specs/greet.md"),
            ),
        )
        manifest = build_manifest(
            task=task,
            branch_name="b",
            integration_branch="main",
            graph_name=None,
            attempt_num=1,
            dependency_descriptions={},
        )
        assert manifest.src_paths == (Path("src/greet.py"),)
        assert manifest.test_paths == (Path("test/test_greet.py"),)
        assert manifest.spec_path == Path("specs/greet.md")
        assert manifest.attempt_num == 1

    def test_task_with_dependencies(self) -> None:
        """Dependency descriptions are mapped to DependencyInfo."""
        task = _minimal_task(dependencies=("dep_a", "dep_b"))
        manifest = build_manifest(
            task=task,
            branch_name="b",
            integration_branch="main",
            graph_name="demo",
            attempt_num=0,
            dependency_descriptions={
                "dep_a": "Create stubs",
                "dep_b": None,
            },
        )
        assert manifest.dependencies["dep_a"].description == "Create stubs"
        assert manifest.dependencies["dep_b"].description is None

    def test_role_is_enum(self) -> None:
        """Role is stored as AgentRole enum."""
        task = _minimal_task(role=AgentRole.IMPLEMENTER)
        manifest = build_manifest(
            task=task,
            branch_name="b",
            integration_branch="main",
            graph_name=None,
            attempt_num=0,
            dependency_descriptions={},
        )
        assert manifest.role == AgentRole.IMPLEMENTER

    def test_graph_name_none(self) -> None:
        """graph_name=None is preserved."""
        task = _minimal_task()
        manifest = build_manifest(
            task=task,
            branch_name="b",
            integration_branch="main",
            graph_name=None,
            attempt_num=0,
            dependency_descriptions={},
        )
        assert manifest.graph_name is None


class TestManifestToDict:
    """Tests for manifest_to_dict."""

    def _build_and_serialize(self, **kwargs: object) -> dict:
        task = _minimal_task(
            role=AgentRole.TEST_WRITER,
            paths=TaskPaths(src=(Path("src/a.py"),), test=(Path("test/test_a.py"),)),
        )
        defaults: dict[str, object] = {
            "task": task,
            "branch_name": "graph/demo/my_task",
            "integration_branch": "graph/demo",
            "graph_name": "demo",
            "attempt_num": 0,
            "dependency_descriptions": {},
        }
        defaults.update(kwargs)
        manifest = build_manifest(**defaults)  # type: ignore[arg-type]
        return manifest_to_dict(manifest)

    def test_top_level_structure(self) -> None:
        """Dict has the expected top-level keys."""
        d = self._build_and_serialize()
        assert set(d.keys()) == {
            "schema_version",
            "task",
            "paths",
            "workspace",
            "execution",
            "dependencies",
            "input_files",
            "tools",
        }

    def test_schema_version(self) -> None:
        d = self._build_and_serialize()
        assert d["schema_version"] == MANIFEST_SCHEMA_VERSION

    def test_task_section(self) -> None:
        d = self._build_and_serialize()
        assert d["task"]["id"] == "my_task"
        assert d["task"]["role"] == "test_writer"

    def test_paths_section(self) -> None:
        d = self._build_and_serialize()
        assert d["paths"]["src"] == ["src/a.py"]
        assert d["paths"]["test"] == ["test/test_a.py"]
        assert d["paths"]["spec"] is None

    def test_workspace_section(self) -> None:
        d = self._build_and_serialize()
        assert d["workspace"]["branch_name"] == "graph/demo/my_task"
        assert d["workspace"]["integration_branch"] == "graph/demo"

    def test_execution_section(self) -> None:
        d = self._build_and_serialize()
        assert d["execution"]["attempt_num"] == 0
        assert d["execution"]["graph_name"] == "demo"

    def test_dependencies_section(self) -> None:
        d = self._build_and_serialize(dependency_descriptions={"dep_a": "Create stubs"})
        assert d["dependencies"] == {"dep_a": {"description": "Create stubs"}}

    def test_empty_dependencies(self) -> None:
        d = self._build_and_serialize()
        assert d["dependencies"] == {}

    def test_input_files_empty_by_default(self) -> None:
        """Empty input_files serializes to empty list."""
        d = self._build_and_serialize()
        assert d["input_files"] == []

    def test_input_files_serialized(self) -> None:
        """input_files with entries serialize correctly."""
        files = (
            InputFileInfo(
                path=Path("src/queue.py"), category="stubs", source_task="spec"
            ),
        )
        d = self._build_and_serialize(input_files=files)
        assert d["input_files"] == [
            {"path": "src/queue.py", "category": "stubs", "source_task": "spec"}
        ]

    def test_json_serializable(self) -> None:
        """Round-trip through JSON works without error."""
        d = self._build_and_serialize(
            dependency_descriptions={"dep_a": "Create stubs", "dep_b": None}
        )
        text = json.dumps(d)
        assert json.loads(text) == d


class TestInputFileInfo:
    """Tests for InputFileInfo."""

    def test_construction(self) -> None:
        info = InputFileInfo(
            path=Path("src/queue.py"), category="stubs", source_task="spec"
        )
        assert info.path == Path("src/queue.py")
        assert info.category == "stubs"
        assert info.source_task == "spec"

    def test_frozen(self) -> None:
        info = InputFileInfo(
            path=Path("src/queue.py"), category="stubs", source_task="spec"
        )
        with pytest.raises(AttributeError):
            info.category = "tests"  # type: ignore[misc]


class TestBuildManifestInputFiles:
    """Tests for input_files in build_manifest."""

    def test_with_input_files(self) -> None:
        """input_files parameter flows through to manifest."""
        task = Task(id="t1", role=AgentRole.GENERIC)
        files = (
            InputFileInfo(path=Path("src/q.py"), category="stubs", source_task="spec"),
        )
        manifest = build_manifest(
            task=task,
            branch_name="b",
            integration_branch="i",
            graph_name="g",
            attempt_num=0,
            dependency_descriptions={},
            input_files=files,
        )
        assert manifest.input_files == files

    def test_without_input_files_defaults_empty(self) -> None:
        """Omitting input_files defaults to empty tuple."""
        task = Task(id="t1", role=AgentRole.GENERIC)
        manifest = build_manifest(
            task=task,
            branch_name="b",
            integration_branch="i",
            graph_name="g",
            attempt_num=0,
            dependency_descriptions={},
        )
        assert manifest.input_files == ()
