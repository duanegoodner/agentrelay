"""Tests for TaskRuntime mutation methods."""

import tempfile
from pathlib import Path

from agentrelay.task import AgentRole, Task
from agentrelay.task_runtime import TaskRuntime, TaskStatus


def _runtime(*, with_signal_dir: bool = False) -> TaskRuntime:
    rt = TaskRuntime(task=Task(id="t", role=AgentRole.GENERIC))
    if with_signal_dir:
        rt.state.signal_dir = Path(tempfile.mkdtemp())
    return rt


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
        rt = _runtime(with_signal_dir=True)
        rt.mark_failed("boom")
        assert rt.status == TaskStatus.FAILED
        assert rt.state.error == "boom"

    def test_writes_signal_file(self) -> None:
        rt = _runtime(with_signal_dir=True)
        rt.mark_failed("boom")
        assert rt.state.signal_dir is not None
        assert (rt.state.signal_dir / "status" / "failed").exists()

    def test_works_without_signal_dir(self) -> None:
        rt = _runtime()
        rt.mark_failed("boom")
        assert rt.status == TaskStatus.FAILED
        assert rt.state.error == "boom"


class TestResetForRetry:
    """Tests for TaskRuntime.reset_for_retry."""

    def test_archives_error_and_resets_to_pending(self) -> None:
        rt = _runtime(with_signal_dir=True)
        rt.mark_failed("oops")
        rt.state.attempt_num = 1
        rt.reset_for_retry()
        assert rt.status == TaskStatus.PENDING
        assert rt.state.error is None
        assert rt.artifacts.concerns == ["attempt_1_error: oops"]

    def test_no_concern_when_no_error(self) -> None:
        rt = _runtime(with_signal_dir=True)
        rt.mark_failed("temp")
        rt.state.error = None
        rt.reset_for_retry()
        assert rt.status == TaskStatus.PENDING
        assert rt.artifacts.concerns == []

    def test_clears_status_signals_on_retry(self) -> None:
        rt = _runtime(with_signal_dir=True)
        rt.mark_running()
        rt.mark_failed("oops")
        rt.reset_for_retry()
        assert rt.state.signal_dir is not None
        status_dir = rt.state.signal_dir / "status"
        assert (status_dir / "pending").exists()
        assert not (status_dir / "running").exists()
        assert not (status_dir / "failed").exists()

    def test_clears_agent_done_signal_on_retry(self) -> None:
        rt = _runtime(with_signal_dir=True)
        rt.mark_failed("gate failed")
        assert rt.state.signal_dir is not None
        (rt.state.signal_dir / ".done").write_text("done\nhttps://example.com/pr/1\n")
        rt.reset_for_retry()
        assert not (rt.state.signal_dir / ".done").exists()

    def test_clears_agent_failed_signal_on_retry(self) -> None:
        rt = _runtime(with_signal_dir=True)
        rt.mark_failed("agent failed")
        assert rt.state.signal_dir is not None
        (rt.state.signal_dir / ".failed").write_text("failed\nsome reason\n")
        rt.reset_for_retry()
        assert not (rt.state.signal_dir / ".failed").exists()


class TestMarkPending:
    """Tests for TaskRuntime.mark_pending."""

    def test_sets_pending(self) -> None:
        rt = _runtime(with_signal_dir=True)
        rt.mark_pending()
        assert rt.status == TaskStatus.PENDING


class TestMarkRunning:
    """Tests for TaskRuntime.mark_running."""

    def test_sets_running(self) -> None:
        rt = _runtime(with_signal_dir=True)
        rt.mark_running()
        assert rt.status == TaskStatus.RUNNING

    def test_writes_signal_file(self) -> None:
        rt = _runtime(with_signal_dir=True)
        rt.mark_running()
        assert rt.state.signal_dir is not None
        assert (rt.state.signal_dir / "status" / "running").exists()


class TestMarkPrCreated:
    """Tests for TaskRuntime.mark_pr_created."""

    def test_sets_pr_created(self) -> None:
        rt = _runtime(with_signal_dir=True)
        rt.mark_pr_created()
        assert rt.status == TaskStatus.PR_CREATED


class TestMarkPrMerged:
    """Tests for TaskRuntime.mark_pr_merged."""

    def test_sets_pr_merged(self) -> None:
        rt = _runtime(with_signal_dir=True)
        rt.mark_pr_merged()
        assert rt.status == TaskStatus.PR_MERGED
