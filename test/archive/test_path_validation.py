"""Tests for validate_task_paths (dispatch-time path validation)."""

import pytest

from agentrelaysmall.archive.agent_task import AgentRole, AgentTask, TaskPaths
from agentrelaysmall.archive.run_graph import validate_task_paths

# ── IMPLEMENTER ───────────────────────────────────────────────────────────────


def test_implementer_all_paths_present_no_exception(tmp_path):
    src = tmp_path / "src" / "foo.py"
    src.parent.mkdir(parents=True)
    src.touch()
    test = tmp_path / "tests" / "test_foo.py"
    test.parent.mkdir(parents=True)
    test.touch()

    task = AgentTask(
        id="impl_001",
        role=AgentRole.IMPLEMENTER,
        paths=TaskPaths(src=("src/foo.py",), test=("tests/test_foo.py",)),
    )
    validate_task_paths(task, tmp_path)  # no exception


def test_implementer_missing_src_path_raises(tmp_path):
    # src/foo.py is NOT created
    test = tmp_path / "tests" / "test_foo.py"
    test.parent.mkdir(parents=True)
    test.touch()

    task = AgentTask(
        id="impl_001",
        role=AgentRole.IMPLEMENTER,
        paths=TaskPaths(src=("src/foo.py",), test=("tests/test_foo.py",)),
    )
    with pytest.raises(ValueError, match="src/foo.py"):
        validate_task_paths(task, tmp_path)


def test_implementer_missing_src_path_includes_task_id(tmp_path):
    task = AgentTask(
        id="impl_roman",
        role=AgentRole.IMPLEMENTER,
        paths=TaskPaths(src=("src/roman.py",)),
    )
    with pytest.raises(ValueError, match="impl_roman"):
        validate_task_paths(task, tmp_path)


def test_implementer_missing_test_path_raises(tmp_path):
    src = tmp_path / "src" / "foo.py"
    src.parent.mkdir(parents=True)
    src.touch()
    # tests/test_foo.py is NOT created

    task = AgentTask(
        id="impl_001",
        role=AgentRole.IMPLEMENTER,
        paths=TaskPaths(src=("src/foo.py",), test=("tests/test_foo.py",)),
    )
    with pytest.raises(ValueError, match="test_foo.py"):
        validate_task_paths(task, tmp_path)


def test_implementer_no_paths_no_exception(tmp_path):
    task = AgentTask(id="impl_001", role=AgentRole.IMPLEMENTER)
    validate_task_paths(task, tmp_path)  # no exception — nothing to check


# ── TEST_WRITER ───────────────────────────────────────────────────────────────


def test_test_writer_stubs_present_no_exception(tmp_path):
    src = tmp_path / "src" / "foo.py"
    src.parent.mkdir(parents=True)
    src.touch()
    # test_paths parent dir must exist (test file itself need not exist yet)
    (tmp_path / "tests").mkdir()

    task = AgentTask(
        id="tw_001",
        role=AgentRole.TEST_WRITER,
        paths=TaskPaths(src=("src/foo.py",), test=("tests/test_foo.py",)),
    )
    validate_task_paths(task, tmp_path)  # no exception


def test_test_writer_missing_stub_raises(tmp_path):
    # src/foo.py does NOT exist
    (tmp_path / "tests").mkdir()

    task = AgentTask(
        id="tw_001",
        role=AgentRole.TEST_WRITER,
        paths=TaskPaths(src=("src/foo.py",), test=("tests/test_foo.py",)),
    )
    with pytest.raises(ValueError, match="src/foo.py"):
        validate_task_paths(task, tmp_path)


def test_test_writer_missing_test_parent_dir_raises(tmp_path):
    src = tmp_path / "src" / "foo.py"
    src.parent.mkdir(parents=True)
    src.touch()
    # tests/ directory does NOT exist

    task = AgentTask(
        id="tw_001",
        role=AgentRole.TEST_WRITER,
        paths=TaskPaths(src=("src/foo.py",), test=("tests/test_foo.py",)),
    )
    with pytest.raises(ValueError, match="test_foo.py"):
        validate_task_paths(task, tmp_path)


# ── SPEC_WRITER ───────────────────────────────────────────────────────────────


def test_spec_writer_parent_dirs_present_no_exception(tmp_path):
    (tmp_path / "src").mkdir()

    task = AgentTask(
        id="sw_001",
        role=AgentRole.SPEC_WRITER,
        paths=TaskPaths(src=("src/foo.py",)),
    )
    validate_task_paths(task, tmp_path)  # no exception


def test_spec_writer_missing_parent_dir_raises(tmp_path):
    # src/ directory does NOT exist

    task = AgentTask(
        id="sw_001",
        role=AgentRole.SPEC_WRITER,
        paths=TaskPaths(src=("src/foo.py",)),
    )
    with pytest.raises(ValueError, match="src"):
        validate_task_paths(task, tmp_path)


def test_spec_writer_with_spec_path_parent_present_no_exception(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "specs").mkdir()

    task = AgentTask(
        id="sw_001",
        role=AgentRole.SPEC_WRITER,
        paths=TaskPaths(src=("src/foo.py",), spec="specs/foo.md"),
    )
    validate_task_paths(task, tmp_path)  # no exception


def test_spec_writer_with_spec_path_missing_parent_raises(tmp_path):
    (tmp_path / "src").mkdir()
    # specs/ does NOT exist

    task = AgentTask(
        id="sw_001",
        role=AgentRole.SPEC_WRITER,
        paths=TaskPaths(src=("src/foo.py",), spec="specs/foo.md"),
    )
    with pytest.raises(ValueError, match="specs/foo.md"):
        validate_task_paths(task, tmp_path)


# ── GENERIC ───────────────────────────────────────────────────────────────────


def test_generic_no_exception_regardless_of_paths(tmp_path):
    task = AgentTask(
        id="t1",
        role=AgentRole.GENERIC,
        paths=TaskPaths(src=("nonexistent/foo.py",), test=("nonexistent/test_foo.py",)),
    )
    validate_task_paths(task, tmp_path)  # no exception — GENERIC is not validated


# ── MERGER ────────────────────────────────────────────────────────────────────


def test_merger_no_exception_regardless_of_paths(tmp_path):
    task = AgentTask(
        id="merger_001",
        role=AgentRole.MERGER,
        paths=TaskPaths(src=("nonexistent/foo.py",)),
    )
    validate_task_paths(task, tmp_path)  # no exception — MERGER is not validated
