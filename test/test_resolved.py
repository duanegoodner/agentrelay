"""Tests for resolved record dataclasses, serialization, and builders."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentrelay.resolved import (
    InputFromSpec,
    ResolvedTask,
    ResolvedWorkstream,
    TaggedPathSpec,
    build_resolved_task,
    build_resolved_workstream,
)
from agentrelay.task import AgentRole, InputFrom, TaggedPath, Task
from agentrelay.task_runtime import TaskRuntime
from agentrelay.workstream.core.runtime import WorkstreamRuntime
from agentrelay.workstream.core.workstream import WorkstreamSpec

# ── ResolvedTask serialization ──


class TestResolvedTaskSerialization:
    """Round-trip serialization tests for ResolvedTask."""

    def _make_resolved_task(self, **overrides: object) -> ResolvedTask:
        defaults = dict(
            task_id="write_tests",
            workstream_id="ws-1",
            dependencies=("write_spec",),
            inputs_from=(InputFromSpec(task="write_spec", category="stubs"),),
            role="test_writer",
            model="claude-sonnet-4-6",
            tagged_paths=(TaggedPathSpec(path="tests/test_foo.py", category="test"),),
            branch_name="agentrelay/demo/write_tests",
            integration_branch="agentrelay/demo/ws-1/integration",
            integration_branch_before_merge="abc123",
            completed_at_attempt=0,
            pr_url="https://github.com/org/repo/pull/42",
        )
        defaults.update(overrides)
        return ResolvedTask(**defaults)  # type: ignore[arg-type]

    def test_round_trip(self) -> None:
        """to_dict -> from_dict produces an equal object."""
        original = self._make_resolved_task()
        restored = ResolvedTask.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_no_pr(self) -> None:
        """Round-trip for a COMPLETED task (no PR, no pre-merge SHA)."""
        original = self._make_resolved_task(
            pr_url=None, integration_branch_before_merge=None
        )
        restored = ResolvedTask.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_no_model(self) -> None:
        """Round-trip when model is None (framework default)."""
        original = self._make_resolved_task(model=None)
        restored = ResolvedTask.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_no_inputs_from(self) -> None:
        """Round-trip with empty inputs_from."""
        original = self._make_resolved_task(inputs_from=())
        restored = ResolvedTask.from_dict(original.to_dict())
        assert restored == original

    def test_frozen(self) -> None:
        """ResolvedTask instances are immutable."""
        rt = self._make_resolved_task()
        with pytest.raises(AttributeError):
            rt.task_id = "changed"  # type: ignore[misc]


# ── ResolvedWorkstream serialization ──


class TestResolvedWorkstreamSerialization:
    """Round-trip serialization tests for ResolvedWorkstream."""

    def test_round_trip_merged(self) -> None:
        """Round-trip for a workstream with a merged integration PR."""
        original = ResolvedWorkstream(
            workstream_id="ws-1",
            integration_pr_url="https://github.com/org/repo/pull/99",
            target_branch="main",
            target_branch_before_any_merge="def456",
            merge_occurred=True,
            merged_at="2026-04-12T14:30:00+00:00",
        )
        restored = ResolvedWorkstream.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_skipped(self) -> None:
        """Round-trip for a skipped workstream (no commits ahead)."""
        original = ResolvedWorkstream(
            workstream_id="ws-1",
            integration_pr_url=None,
            target_branch="main",
            target_branch_before_any_merge="def456",
            merge_occurred=False,
            merged_at=None,
        )
        restored = ResolvedWorkstream.from_dict(original.to_dict())
        assert restored == original

    def test_frozen(self) -> None:
        """ResolvedWorkstream instances are immutable."""
        rw = ResolvedWorkstream(
            workstream_id="ws-1",
            integration_pr_url=None,
            target_branch="main",
            target_branch_before_any_merge="x",
            merge_occurred=False,
            merged_at=None,
        )
        with pytest.raises(AttributeError):
            rw.workstream_id = "changed"  # type: ignore[misc]


# ── Builder: build_resolved_task ──


class TestBuildResolvedTask:
    """Tests for the build_resolved_task builder function."""

    def _make_runtime(
        self,
        *,
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
        pr_url: str | None = "https://github.com/org/repo/pull/42",
    ) -> TaskRuntime:
        from agentrelay.task import AgentConfig

        task = Task(
            id=task_id,
            role=role,
            dependencies=dependencies,
            inputs_from=inputs_from,
            tagged_paths=tagged_paths,
            workstream_id=workstream_id,
            primary_agent=AgentConfig(model=model),
        )
        runtime = TaskRuntime(task=task)
        runtime.state.branch_name = f"agentrelay/demo/{task_id}"
        runtime.state.integration_branch = (
            f"agentrelay/demo/{workstream_id}/integration"
        )
        runtime.state.attempt_num = 0
        runtime.artifacts.pr_url = pr_url
        return runtime

    def test_build_from_pr_merged_runtime(self) -> None:
        """Builds correctly for a PR_MERGED task."""
        runtime = self._make_runtime()
        resolved = build_resolved_task(runtime, "pre_merge_sha_123")

        assert resolved.task_id == "task_a"
        assert resolved.workstream_id == "ws-1"
        assert resolved.role == "test_writer"
        assert resolved.model == "claude-sonnet-4-6"
        assert resolved.dependencies == ("spec_task",)
        assert resolved.inputs_from == (
            InputFromSpec(task="spec_task", category="stubs"),
        )
        assert resolved.tagged_paths == (
            TaggedPathSpec(path="tests/test_foo.py", category="test"),
        )
        assert resolved.branch_name == "agentrelay/demo/task_a"
        assert resolved.integration_branch == "agentrelay/demo/ws-1/integration"
        assert resolved.integration_branch_before_merge == "pre_merge_sha_123"
        assert resolved.completed_at_attempt == 0
        assert resolved.pr_url == "https://github.com/org/repo/pull/42"

    def test_build_from_completed_runtime(self) -> None:
        """Builds correctly for a COMPLETED (no-PR) task."""
        runtime = self._make_runtime(pr_url=None)
        resolved = build_resolved_task(runtime, None)

        assert resolved.pr_url is None
        assert resolved.integration_branch_before_merge is None


# ── Builder: build_resolved_workstream ──


class TestBuildResolvedWorkstream:
    """Tests for the build_resolved_workstream builder function."""

    def test_build_from_merged_runtime(self) -> None:
        """Builds correctly for a workstream with a merged integration PR."""
        runtime = WorkstreamRuntime(
            spec=WorkstreamSpec(id="ws-1", merge_target_branch="main"),
        )
        runtime.artifacts.merge_pr_url = "https://github.com/org/repo/pull/99"
        runtime.artifacts.target_branch_before_any_merge = "before_sha"

        resolved = build_resolved_workstream(runtime)

        assert resolved.workstream_id == "ws-1"
        assert resolved.integration_pr_url == "https://github.com/org/repo/pull/99"
        assert resolved.target_branch == "main"
        assert resolved.target_branch_before_any_merge == "before_sha"
        assert resolved.merge_occurred is True
        assert resolved.merged_at is not None

    def test_build_from_skipped_runtime(self) -> None:
        """Builds correctly for a skipped workstream (no PR)."""
        runtime = WorkstreamRuntime(
            spec=WorkstreamSpec(id="ws-1", merge_target_branch="main"),
        )
        runtime.artifacts.target_branch_before_any_merge = "skip_sha"

        resolved = build_resolved_workstream(runtime)

        assert resolved.workstream_id == "ws-1"
        assert resolved.integration_pr_url is None
        assert resolved.target_branch_before_any_merge == "skip_sha"
        assert resolved.merge_occurred is False
        assert resolved.merged_at is None
