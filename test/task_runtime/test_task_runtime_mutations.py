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

    def test_archives_artifacts_before_cleanup(self) -> None:
        rt = _runtime(with_signal_dir=True)
        rt.state.attempt_num = 1
        assert rt.state.signal_dir is not None
        artifacts = {
            "agent.log": b"log content",
            "gate_last_output.txt": b"gate output",
            "summary.md": b"summary text",
            "concerns.log": b"design concern",
            "ops_concerns.log": b"ops concern",
        }
        for name, content in artifacts.items():
            (rt.state.signal_dir / name).write_bytes(content)
        rt.mark_failed("gate failed")
        rt.reset_for_retry()
        attempt_dir = rt.state.signal_dir / "attempts" / "1"
        for name, content in artifacts.items():
            assert (attempt_dir / name).read_bytes() == content

    def test_skips_missing_artifacts_silently(self) -> None:
        rt = _runtime(with_signal_dir=True)
        rt.state.attempt_num = 0
        assert rt.state.signal_dir is not None
        (rt.state.signal_dir / "agent.log").write_bytes(b"only this")
        rt.mark_failed("oops")
        rt.reset_for_retry()
        attempt_dir = rt.state.signal_dir / "attempts" / "0"
        assert (attempt_dir / "agent.log").read_bytes() == b"only this"
        assert not (attempt_dir / "gate_last_output.txt").exists()
        assert not (attempt_dir / "summary.md").exists()

    def test_does_not_archive_done_or_failed(self) -> None:
        rt = _runtime(with_signal_dir=True)
        rt.state.attempt_num = 0
        assert rt.state.signal_dir is not None
        (rt.state.signal_dir / ".done").write_text("done\nhttp://pr/1\n")
        (rt.state.signal_dir / ".failed").write_text("failed\nreason\n")
        (rt.state.signal_dir / "agent.log").write_bytes(b"log")
        rt.mark_failed("oops")
        rt.reset_for_retry()
        attempt_dir = rt.state.signal_dir / "attempts" / "0"
        assert not (attempt_dir / ".done").exists()
        assert not (attempt_dir / ".failed").exists()
        assert (attempt_dir / "agent.log").exists()

    def test_no_attempts_dir_when_no_artifacts(self) -> None:
        rt = _runtime(with_signal_dir=True)
        rt.state.attempt_num = 0
        assert rt.state.signal_dir is not None
        rt.mark_failed("oops")
        rt.reset_for_retry()
        assert not (rt.state.signal_dir / "attempts").exists()


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


class TestMarkCompleted:
    """Tests for TaskRuntime.mark_completed."""

    def test_sets_completed(self) -> None:
        rt = _runtime(with_signal_dir=True)
        rt.mark_completed()
        assert rt.status == TaskStatus.COMPLETED

    def test_writes_signal_file(self) -> None:
        rt = _runtime(with_signal_dir=True)
        rt.mark_completed()
        assert rt.state.signal_dir is not None
        assert (rt.state.signal_dir / "status" / "completed").exists()
