"""Tests for WorkstreamRuntime mutation methods."""

from agentrelay.workstream import WorkstreamRuntime, WorkstreamSpec, WorkstreamStatus


def _runtime() -> WorkstreamRuntime:
    return WorkstreamRuntime(spec=WorkstreamSpec(id="ws"))


class TestActivate:
    """Tests for WorkstreamRuntime.activate."""

    def test_sets_active_and_task_id(self) -> None:
        rt = _runtime()
        rt.activate("task_1")
        assert rt.state.status == WorkstreamStatus.ACTIVE
        assert rt.state.active_task_id == "task_1"


class TestDeactivate:
    """Tests for WorkstreamRuntime.deactivate."""

    def test_clears_active_task_id(self) -> None:
        rt = _runtime()
        rt.activate("task_1")
        rt.deactivate()
        assert rt.state.active_task_id is None

    def test_preserves_status(self) -> None:
        rt = _runtime()
        rt.activate("task_1")
        rt.deactivate()
        assert rt.state.status == WorkstreamStatus.ACTIVE


class TestMarkFailed:
    """Tests for WorkstreamRuntime.mark_failed."""

    def test_sets_failed_and_error(self) -> None:
        rt = _runtime()
        rt.mark_failed("boom")
        assert rt.state.status == WorkstreamStatus.FAILED
        assert rt.state.error == "boom"


class TestMarkMerged:
    """Tests for WorkstreamRuntime.mark_merged."""

    def test_sets_merged(self) -> None:
        rt = _runtime()
        rt.mark_merged()
        assert rt.state.status == WorkstreamStatus.MERGED
