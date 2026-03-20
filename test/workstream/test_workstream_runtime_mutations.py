"""Tests for WorkstreamRuntime mutation methods."""

import tempfile
from pathlib import Path

from agentrelay.workstream import WorkstreamRuntime, WorkstreamSpec, WorkstreamStatus


def _runtime() -> WorkstreamRuntime:
    rt = WorkstreamRuntime(spec=WorkstreamSpec(id="ws"))
    rt.state.signal_dir = Path(tempfile.mkdtemp())
    return rt


class TestMarkMergeReady:
    """Tests for WorkstreamRuntime.mark_merge_ready."""

    def test_sets_merge_ready(self) -> None:
        rt = _runtime()
        rt.mark_merge_ready()
        assert rt.status == WorkstreamStatus.MERGE_READY


class TestMarkFailed:
    """Tests for WorkstreamRuntime.mark_failed."""

    def test_sets_failed_and_error(self) -> None:
        rt = _runtime()
        rt.mark_failed("boom")
        assert rt.status == WorkstreamStatus.FAILED
        assert rt.state.error == "boom"


class TestMarkPrCreated:
    """Tests for WorkstreamRuntime.mark_pr_created."""

    def test_sets_pr_created(self) -> None:
        rt = _runtime()
        rt.mark_pr_created("https://example.com/pr/1")
        assert rt.status == WorkstreamStatus.PR_CREATED
        assert rt.artifacts.merge_pr_url == "https://example.com/pr/1"


class TestMarkMerged:
    """Tests for WorkstreamRuntime.mark_merged."""

    def test_sets_merged(self) -> None:
        rt = _runtime()
        rt.mark_merged()
        assert rt.status == WorkstreamStatus.MERGED
