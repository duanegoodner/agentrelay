"""Tests for WorkstreamRuntime mutation methods."""

from agentrelay.workstream import WorkstreamRuntime, WorkstreamSpec, WorkstreamStatus


def _runtime() -> WorkstreamRuntime:
    return WorkstreamRuntime(spec=WorkstreamSpec(id="ws"))


class TestMarkMergeReady:
    """Tests for WorkstreamRuntime.mark_merge_ready."""

    def test_sets_merge_ready(self) -> None:
        rt = _runtime()
        rt.mark_merge_ready()
        assert rt.state.status == WorkstreamStatus.MERGE_READY


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
