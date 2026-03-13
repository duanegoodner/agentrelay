"""Tests for TaskRuntime mutation methods."""

from agentrelay.task import AgentRole, Task
from agentrelay.task_runtime import TaskRuntime, TaskStatus


def _runtime() -> TaskRuntime:
    return TaskRuntime(task=Task(id="t", role=AgentRole.GENERIC))


class TestPrepareForAttempt:
    """Tests for TaskRuntime.prepare_for_attempt."""

    def test_sets_attempt_num_and_clears_error(self) -> None:
        rt = _runtime()
        rt.state.error = "old"
        rt.prepare_for_attempt(2)
        assert rt.state.attempt_num == 2
        assert rt.state.error is None

    def test_clears_error_when_none(self) -> None:
        rt = _runtime()
        rt.prepare_for_attempt(0)
        assert rt.state.attempt_num == 0
        assert rt.state.error is None


class TestMarkFailed:
    """Tests for TaskRuntime.mark_failed."""

    def test_sets_failed_status_and_error(self) -> None:
        rt = _runtime()
        rt.mark_failed("boom")
        assert rt.state.status == TaskStatus.FAILED
        assert rt.state.error == "boom"


class TestResetForRetry:
    """Tests for TaskRuntime.reset_for_retry."""

    def test_archives_error_and_resets_to_pending(self) -> None:
        rt = _runtime()
        rt.state.status = TaskStatus.FAILED
        rt.state.error = "oops"
        rt.state.attempt_num = 1
        rt.reset_for_retry()
        assert rt.state.status == TaskStatus.PENDING
        assert rt.state.error is None
        assert rt.artifacts.concerns == ["attempt_1_error: oops"]

    def test_no_concern_when_no_error(self) -> None:
        rt = _runtime()
        rt.state.status = TaskStatus.FAILED
        rt.reset_for_retry()
        assert rt.state.status == TaskStatus.PENDING
        assert rt.artifacts.concerns == []


class TestMarkPending:
    """Tests for TaskRuntime.mark_pending."""

    def test_sets_pending(self) -> None:
        rt = _runtime()
        rt.state.status = TaskStatus.FAILED
        rt.mark_pending()
        assert rt.state.status == TaskStatus.PENDING
