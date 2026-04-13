"""Tests for resolved record validation against current graph definitions."""

from __future__ import annotations

from pathlib import Path

from agentrelay.resolved import InputFromSpec, ResolvedTask, TaggedPathSpec
from agentrelay.resolved_validation import (
    FieldMismatch,
    validate_frozen_tasks,
    validate_resolved_task,
)
from agentrelay.task import AgentConfig, AgentRole, InputFrom, TaggedPath, Task


def _make_task(
    task_id: str = "task_a",
    role: AgentRole = AgentRole.TEST_WRITER,
    model: str | None = "claude-sonnet-4-6",
    dependencies: tuple[str, ...] = ("spec_task",),
    inputs_from: tuple[InputFrom, ...] = (
        InputFrom(task="spec_task", category="stubs"),
    ),
    tagged_paths: tuple[TaggedPath, ...] = (
        TaggedPath(path=Path("tests/test_foo.py"), category="test"),
    ),
    workstream_id: str = "ws-1",
) -> Task:
    return Task(
        id=task_id,
        role=role,
        dependencies=dependencies,
        inputs_from=inputs_from,
        tagged_paths=tagged_paths,
        workstream_id=workstream_id,
        primary_agent=AgentConfig(model=model),
    )


def _make_resolved(
    task_id: str = "task_a",
    role: str = "test_writer",
    model: str | None = "claude-sonnet-4-6",
    dependencies: tuple[str, ...] = ("spec_task",),
    inputs_from: tuple[InputFromSpec, ...] = (
        InputFromSpec(task="spec_task", category="stubs"),
    ),
    tagged_paths: tuple[TaggedPathSpec, ...] = (
        TaggedPathSpec(path="tests/test_foo.py", category="test"),
    ),
    workstream_id: str = "ws-1",
) -> ResolvedTask:
    return ResolvedTask(
        task_id=task_id,
        workstream_id=workstream_id,
        dependencies=dependencies,
        inputs_from=inputs_from,
        role=role,
        model=model,
        tagged_paths=tagged_paths,
        branch_name="agentrelay/demo/task_a",
        integration_branch="agentrelay/demo/ws-1/integration",
        integration_branch_before_merge="abc123",
        completed_at_attempt=0,
        pr_url="https://github.com/org/repo/pull/42",
    )


# ── validate_resolved_task ──


class TestValidateResolvedTask:
    """Tests for per-task resolved validation."""

    def test_matching_definitions_no_mismatches(self) -> None:
        """Identical definitions produce no mismatches."""
        result = validate_resolved_task(_make_resolved(), _make_task())
        assert result.task_id == "task_a"
        assert result.mismatches == ()
        assert result.has_overrides is False

    def test_changed_role_produces_mismatch(self) -> None:
        """Different role values produce a role mismatch."""
        resolved = _make_resolved(role="generic")
        task = _make_task(role=AgentRole.TEST_WRITER)
        result = validate_resolved_task(resolved, task)
        assert result.has_overrides is True
        assert any(m.field == "role" for m in result.mismatches)
        role_mismatch = next(m for m in result.mismatches if m.field == "role")
        assert role_mismatch.resolved_value == "generic"
        assert role_mismatch.current_value == "test_writer"

    def test_changed_model_produces_mismatch(self) -> None:
        """Different model values produce a model mismatch."""
        resolved = _make_resolved(model="claude-sonnet-4-6")
        task = _make_task(model="claude-opus-4-6")
        result = validate_resolved_task(resolved, task)
        assert any(m.field == "model" for m in result.mismatches)

    def test_changed_dependencies_produces_mismatch(self) -> None:
        """Different dependency lists produce a dependencies mismatch."""
        resolved = _make_resolved(dependencies=("spec_task",))
        task = _make_task(dependencies=("spec_task", "extra_task"))
        result = validate_resolved_task(resolved, task)
        assert any(m.field == "dependencies" for m in result.mismatches)

    def test_changed_tagged_paths_produces_mismatch(self) -> None:
        """Different tagged paths produce a tagged_paths mismatch."""
        resolved = _make_resolved(
            tagged_paths=(TaggedPathSpec(path="tests/test_foo.py", category="test"),)
        )
        task = _make_task(
            tagged_paths=(TaggedPath(path=Path("tests/test_bar.py"), category="test"),)
        )
        result = validate_resolved_task(resolved, task)
        assert any(m.field == "tagged_paths" for m in result.mismatches)

    def test_changed_inputs_from_produces_mismatch(self) -> None:
        """Different inputs_from produce an inputs_from mismatch."""
        resolved = _make_resolved(
            inputs_from=(InputFromSpec(task="old_task", category="stubs"),)
        )
        task = _make_task(inputs_from=(InputFrom(task="spec_task", category="stubs"),))
        result = validate_resolved_task(resolved, task)
        assert any(m.field == "inputs_from" for m in result.mismatches)

    def test_changed_workstream_id_produces_mismatch(self) -> None:
        """Different workstream IDs produce a workstream_id mismatch."""
        resolved = _make_resolved(workstream_id="ws-old")
        task = _make_task(workstream_id="ws-new")
        result = validate_resolved_task(resolved, task)
        assert any(m.field == "workstream_id" for m in result.mismatches)

    def test_execution_artifacts_not_compared(self) -> None:
        """branch_name, pr_url, and attempt are not compared (execution artifacts)."""
        resolved = _make_resolved()
        task = _make_task()
        result = validate_resolved_task(resolved, task)
        assert result.mismatches == ()


# ── validate_frozen_tasks ──


class TestValidateFrozenTasks:
    """Tests for aggregate frozen task validation."""

    def test_all_matching(self) -> None:
        """All frozen tasks match — no overrides, no errors."""
        frozen = {"task_a": _make_resolved()}
        tasks = {"task_a": _make_task()}
        result = validate_frozen_tasks(frozen, tasks)
        assert result.has_errors is False
        assert result.has_overrides is False
        assert result.task_results == ()
        assert result.missing_task_ids == ()

    def test_missing_task_id_is_error(self) -> None:
        """A frozen task ID not in the current graph is a hard error."""
        frozen = {"removed_task": _make_resolved(task_id="removed_task")}
        tasks = {"task_a": _make_task()}
        result = validate_frozen_tasks(frozen, tasks)
        assert result.has_errors is True
        assert "removed_task" in result.missing_task_ids

    def test_overrides_reported(self) -> None:
        """Changed definitions produce override entries."""
        frozen = {"task_a": _make_resolved(model="claude-sonnet-4-6")}
        tasks = {"task_a": _make_task(model="claude-opus-4-6")}
        result = validate_frozen_tasks(frozen, tasks)
        assert result.has_errors is False
        assert result.has_overrides is True
        assert len(result.task_results) == 1
        assert result.task_results[0].task_id == "task_a"

    def test_mixed_overrides_and_missing(self) -> None:
        """Both overrides and missing tasks are reported."""
        frozen = {
            "task_a": _make_resolved(model="claude-sonnet-4-6"),
            "removed": _make_resolved(task_id="removed"),
        }
        tasks = {"task_a": _make_task(model="claude-opus-4-6")}
        result = validate_frozen_tasks(frozen, tasks)
        assert result.has_errors is True
        assert result.has_overrides is True
        assert "removed" in result.missing_task_ids
