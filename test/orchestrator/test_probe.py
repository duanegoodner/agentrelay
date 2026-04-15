"""Tests for the filesystem probe module.

Covers per-task and per-workstream probing, stale state normalization for
RUNNING and PR_CREATED tasks, resolved.json loading, and the top-level
``probe_graph_state`` entry point.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from agentrelay.agent_sdk.task_helper import NO_PR_SENTINEL
from agentrelay.orchestrator.probe import (
    GraphProbe,
    TaskProbe,
    WorkstreamProbe,
    _latest_attempt_num,
    _normalize_stale_pr_created,
    _normalize_stale_running,
    _probe_task_state,
    _probe_workstream_state,
    probe_graph_state,
)
from agentrelay.resolved import ResolvedTask, ResolvedWorkstream
from agentrelay.task_graph import TaskGraph
from agentrelay.task_graph.builder import TaskGraphBuilder
from agentrelay.task_runtime import TaskStatus
from agentrelay.workstream.core.runtime import WorkstreamStatus

# ── Fake TaskPrProber ──


@dataclass
class _FakeProber:
    merged_urls: set[str] = field(default_factory=set)
    mergeable_urls: set[str] = field(default_factory=set)
    is_merged_calls: list[str] = field(default_factory=list)
    try_merge_calls: list[str] = field(default_factory=list)

    def is_merged(self, pr_url: str) -> bool:
        self.is_merged_calls.append(pr_url)
        return pr_url in self.merged_urls

    def try_merge(self, pr_url: str) -> bool:
        self.try_merge_calls.append(pr_url)
        if pr_url in self.mergeable_urls:
            self.merged_urls.add(pr_url)
            return True
        return False


# ── Graph fixtures ──


def _graph_single_task() -> TaskGraph:
    return TaskGraphBuilder.from_dict(
        {
            "name": "demo",
            "tasks": [{"id": "task_a", "description": "first"}],
        }
    )


def _graph_two_workstreams() -> TaskGraph:
    return TaskGraphBuilder.from_dict(
        {
            "name": "demo",
            "workstreams": [{"id": "ws-a"}, {"id": "ws-b"}],
            "tasks": [
                {"id": "task_a", "workstream_id": "ws-a"},
                {"id": "task_b", "workstream_id": "ws-b"},
            ],
        }
    )


# ── Signal file helpers ──


def _make_signal_dir(run_dir: Path, task_id: str) -> Path:
    signal_dir = run_dir / "signals" / task_id
    signal_dir.mkdir(parents=True, exist_ok=True)
    return signal_dir


def _make_workstream_signal_dir(run_dir: Path, ws_id: str) -> Path:
    signal_dir = run_dir / "workstreams" / ws_id
    signal_dir.mkdir(parents=True, exist_ok=True)
    return signal_dir


def _write_task_status_file(signal_dir: Path, name: str) -> None:
    status_dir = signal_dir / "status"
    status_dir.mkdir(parents=True, exist_ok=True)
    (status_dir / name).write_text("")


def _write_done_file(signal_dir: Path, attempt_num: int, payload: str) -> None:
    attempt_dir = signal_dir / "attempts" / str(attempt_num)
    attempt_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    (attempt_dir / ".done").write_text(f"{timestamp}\n{payload}")


def _write_failed_file(signal_dir: Path, attempt_num: int, reason: str) -> None:
    attempt_dir = signal_dir / "attempts" / str(attempt_num)
    attempt_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    (attempt_dir / ".failed").write_text(f"{timestamp}\n{reason}")


def _sample_resolved_task(task_id: str = "task_a") -> ResolvedTask:
    return ResolvedTask(
        task_id=task_id,
        workstream_id="default",
        dependencies=(),
        inputs_from=(),
        role="generic",
        model=None,
        tagged_paths=(),
        branch_name=f"agentrelay/demo/{task_id}",
        integration_branch="agentrelay/demo/default/integration",
        integration_branch_before_merge="abc123",
        completed_at_attempt=0,
        pr_url="https://github.com/org/repo/pull/1",
    )


def _sample_resolved_workstream(ws_id: str = "ws-a") -> ResolvedWorkstream:
    return ResolvedWorkstream(
        workstream_id=ws_id,
        integration_pr_url="https://github.com/org/repo/pull/2",
        target_branch="main",
        target_branch_before_any_merge="def456",
        merge_occurred=True,
        merged_at=datetime.now(timezone.utc).isoformat(),
    )


# ── _latest_attempt_num ──


class TestLatestAttemptNum:
    def test_returns_zero_when_attempts_dir_missing(self, tmp_path: Path) -> None:
        signal_dir = tmp_path / "sig"
        signal_dir.mkdir()
        assert _latest_attempt_num(signal_dir) == 0

    def test_returns_zero_when_attempts_dir_empty(self, tmp_path: Path) -> None:
        signal_dir = tmp_path / "sig"
        (signal_dir / "attempts").mkdir(parents=True)
        assert _latest_attempt_num(signal_dir) == 0

    def test_returns_max_numeric_subdir(self, tmp_path: Path) -> None:
        signal_dir = tmp_path / "sig"
        (signal_dir / "attempts" / "0").mkdir(parents=True)
        (signal_dir / "attempts" / "2").mkdir()
        (signal_dir / "attempts" / "1").mkdir()
        assert _latest_attempt_num(signal_dir) == 2

    def test_ignores_non_numeric_subdirs(self, tmp_path: Path) -> None:
        signal_dir = tmp_path / "sig"
        (signal_dir / "attempts" / "0").mkdir(parents=True)
        (signal_dir / "attempts" / "notanumber").mkdir()
        assert _latest_attempt_num(signal_dir) == 0


# ── _normalize_stale_running ──


class TestNormalizeStaleRunning:
    def test_done_with_pr_url_returns_pr_created(self, tmp_path: Path) -> None:
        signal_dir = tmp_path / "sig"
        signal_dir.mkdir()
        _write_done_file(signal_dir, 0, "https://github.com/org/repo/pull/1")

        result = _normalize_stale_running(signal_dir, 0)

        assert result == TaskStatus.PR_CREATED
        assert (signal_dir / "status" / "pr_created").is_file()

    def test_done_with_no_pr_sentinel_returns_completed(self, tmp_path: Path) -> None:
        signal_dir = tmp_path / "sig"
        signal_dir.mkdir()
        _write_done_file(signal_dir, 0, NO_PR_SENTINEL)

        result = _normalize_stale_running(signal_dir, 0)

        assert result == TaskStatus.COMPLETED
        assert (signal_dir / "status" / "completed").is_file()

    def test_failed_file_returns_failed(self, tmp_path: Path) -> None:
        signal_dir = tmp_path / "sig"
        signal_dir.mkdir()
        _write_failed_file(signal_dir, 0, "boom")

        result = _normalize_stale_running(signal_dir, 0)

        assert result == TaskStatus.FAILED
        assert (signal_dir / "status" / "failed").is_file()

    def test_neither_signal_returns_failed(self, tmp_path: Path) -> None:
        """Agent killed with no terminal signal → FAILED."""
        signal_dir = tmp_path / "sig"
        (signal_dir / "attempts" / "0").mkdir(parents=True)

        result = _normalize_stale_running(signal_dir, 0)

        assert result == TaskStatus.FAILED
        assert (signal_dir / "status" / "failed").is_file()

    def test_missing_attempt_dir_returns_failed(self, tmp_path: Path) -> None:
        """Missing attempts/<N>/ is indistinguishable from empty → FAILED."""
        signal_dir = tmp_path / "sig"
        signal_dir.mkdir()

        result = _normalize_stale_running(signal_dir, 0)

        assert result == TaskStatus.FAILED
        assert (signal_dir / "status" / "failed").is_file()


# ── _normalize_stale_pr_created ──


class TestNormalizeStalePrCreated:
    def test_none_pr_url_returns_failed(self, tmp_path: Path) -> None:
        signal_dir = tmp_path / "sig"
        signal_dir.mkdir()
        prober = _FakeProber()

        result = _normalize_stale_pr_created(signal_dir, None, prober)

        assert result == TaskStatus.FAILED
        assert (signal_dir / "status" / "failed").is_file()
        assert prober.is_merged_calls == []
        assert prober.try_merge_calls == []

    def test_already_merged_returns_pr_merged(self, tmp_path: Path) -> None:
        signal_dir = tmp_path / "sig"
        signal_dir.mkdir()
        url = "https://github.com/org/repo/pull/1"
        prober = _FakeProber(merged_urls={url})

        result = _normalize_stale_pr_created(signal_dir, url, prober)

        assert result == TaskStatus.PR_MERGED
        assert (signal_dir / "status" / "pr_merged").is_file()
        assert prober.is_merged_calls == [url]
        assert prober.try_merge_calls == []  # short-circuited

    def test_try_merge_success_returns_pr_merged(self, tmp_path: Path) -> None:
        signal_dir = tmp_path / "sig"
        signal_dir.mkdir()
        url = "https://github.com/org/repo/pull/1"
        prober = _FakeProber(mergeable_urls={url})

        result = _normalize_stale_pr_created(signal_dir, url, prober)

        assert result == TaskStatus.PR_MERGED
        assert (signal_dir / "status" / "pr_merged").is_file()
        assert prober.is_merged_calls == [url]
        assert prober.try_merge_calls == [url]

    def test_try_merge_failure_returns_failed(self, tmp_path: Path) -> None:
        signal_dir = tmp_path / "sig"
        signal_dir.mkdir()
        url = "https://github.com/org/repo/pull/1"
        prober = _FakeProber()  # not merged and not mergeable

        result = _normalize_stale_pr_created(signal_dir, url, prober)

        assert result == TaskStatus.FAILED
        assert (signal_dir / "status" / "failed").is_file()
        assert prober.is_merged_calls == [url]
        assert prober.try_merge_calls == [url]


# ── _probe_task_state ──


class TestProbeTaskState:
    def test_missing_signal_dir_returns_pending(self, tmp_path: Path) -> None:
        probe = _probe_task_state(tmp_path, "task_a", "demo", _FakeProber())

        assert probe.task_id == "task_a"
        assert probe.status == TaskStatus.PENDING
        assert probe.attempt_num == 0
        assert probe.pr_url is None
        assert probe.resolved is None
        assert probe.branch_name == "agentrelay/demo/task_a"
        assert probe.signal_dir == tmp_path / "signals" / "task_a"

    def test_pending_status(self, tmp_path: Path) -> None:
        signal_dir = _make_signal_dir(tmp_path, "task_a")
        _write_task_status_file(signal_dir, "pending")

        probe = _probe_task_state(tmp_path, "task_a", "demo", _FakeProber())

        assert probe.status == TaskStatus.PENDING

    def test_pr_merged_status_with_pr_url(self, tmp_path: Path) -> None:
        signal_dir = _make_signal_dir(tmp_path, "task_a")
        _write_task_status_file(signal_dir, "pr_merged")
        _write_done_file(signal_dir, 0, "https://github.com/org/repo/pull/1")

        probe = _probe_task_state(tmp_path, "task_a", "demo", _FakeProber())

        assert probe.status == TaskStatus.PR_MERGED
        assert probe.pr_url == "https://github.com/org/repo/pull/1"

    def test_completed_status_with_no_pr_sentinel(self, tmp_path: Path) -> None:
        signal_dir = _make_signal_dir(tmp_path, "task_a")
        _write_task_status_file(signal_dir, "completed")
        _write_done_file(signal_dir, 0, NO_PR_SENTINEL)

        probe = _probe_task_state(tmp_path, "task_a", "demo", _FakeProber())

        assert probe.status == TaskStatus.COMPLETED
        assert probe.pr_url is None

    def test_failed_status(self, tmp_path: Path) -> None:
        signal_dir = _make_signal_dir(tmp_path, "task_a")
        _write_task_status_file(signal_dir, "failed")

        probe = _probe_task_state(tmp_path, "task_a", "demo", _FakeProber())

        assert probe.status == TaskStatus.FAILED

    def test_resolved_json_loaded(self, tmp_path: Path) -> None:
        signal_dir = _make_signal_dir(tmp_path, "task_a")
        _write_task_status_file(signal_dir, "pr_merged")
        resolved = _sample_resolved_task("task_a")
        (signal_dir / "resolved.json").write_text(json.dumps(resolved.to_dict()))

        probe = _probe_task_state(tmp_path, "task_a", "demo", _FakeProber())

        assert probe.resolved == resolved

    def test_multiple_attempt_dirs_picks_highest(self, tmp_path: Path) -> None:
        signal_dir = _make_signal_dir(tmp_path, "task_a")
        _write_task_status_file(signal_dir, "failed")
        (signal_dir / "attempts" / "0").mkdir(parents=True)
        (signal_dir / "attempts" / "2").mkdir()

        probe = _probe_task_state(tmp_path, "task_a", "demo", _FakeProber())

        assert probe.attempt_num == 2

    def test_stale_running_with_done_and_merged_pr_chains_to_pr_merged(
        self, tmp_path: Path
    ) -> None:
        """End-to-end chained normalization: RUNNING → PR_CREATED → PR_MERGED."""
        signal_dir = _make_signal_dir(tmp_path, "task_a")
        _write_task_status_file(signal_dir, "running")
        url = "https://github.com/org/repo/pull/1"
        _write_done_file(signal_dir, 0, url)
        prober = _FakeProber(merged_urls={url})

        probe = _probe_task_state(tmp_path, "task_a", "demo", prober)

        assert probe.status == TaskStatus.PR_MERGED
        # Both intermediate and final status files exist on disk.
        assert (signal_dir / "status" / "pr_created").is_file()
        assert (signal_dir / "status" / "pr_merged").is_file()
        assert probe.pr_url == url

    def test_stale_running_with_no_signal_resolves_to_failed(
        self, tmp_path: Path
    ) -> None:
        signal_dir = _make_signal_dir(tmp_path, "task_a")
        _write_task_status_file(signal_dir, "running")

        probe = _probe_task_state(tmp_path, "task_a", "demo", _FakeProber())

        assert probe.status == TaskStatus.FAILED

    def test_stale_pr_created_already_merged_resolves_to_pr_merged(
        self, tmp_path: Path
    ) -> None:
        signal_dir = _make_signal_dir(tmp_path, "task_a")
        _write_task_status_file(signal_dir, "pr_created")
        url = "https://github.com/org/repo/pull/1"
        _write_done_file(signal_dir, 0, url)
        prober = _FakeProber(merged_urls={url})

        probe = _probe_task_state(tmp_path, "task_a", "demo", prober)

        assert probe.status == TaskStatus.PR_MERGED
        assert prober.is_merged_calls == [url]


# ── _probe_workstream_state ──


class TestProbeWorkstreamState:
    def test_missing_signal_dir_returns_pending(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        run_dir = tmp_path / "run"

        probe = _probe_workstream_state(run_dir, "ws-a", repo_path, "demo")

        assert probe.workstream_id == "ws-a"
        assert probe.status == WorkstreamStatus.PENDING
        assert probe.merge_pr_url is None
        assert probe.resolved is None
        assert probe.worktree_path == repo_path / ".worktrees" / "demo" / "ws-a"
        assert probe.branch_name == "agentrelay/demo/ws-a/integration"

    def test_pending_signal_file(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        signal_dir = _make_workstream_signal_dir(run_dir, "ws-a")
        (signal_dir / "pending").write_text("")

        probe = _probe_workstream_state(run_dir, "ws-a", tmp_path, "demo")

        assert probe.status == WorkstreamStatus.PENDING

    def test_pr_created_with_url(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        signal_dir = _make_workstream_signal_dir(run_dir, "ws-a")
        (signal_dir / "pr_created").write_text("https://github.com/org/repo/pull/5\n")

        probe = _probe_workstream_state(run_dir, "ws-a", tmp_path, "demo")

        assert probe.status == WorkstreamStatus.PR_CREATED
        assert probe.merge_pr_url == "https://github.com/org/repo/pull/5"

    def test_merged_with_resolved(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        signal_dir = _make_workstream_signal_dir(run_dir, "ws-a")
        (signal_dir / "merged").write_text("")
        resolved = _sample_resolved_workstream("ws-a")
        (signal_dir / "resolved.json").write_text(json.dumps(resolved.to_dict()))

        probe = _probe_workstream_state(run_dir, "ws-a", tmp_path, "demo")

        assert probe.status == WorkstreamStatus.MERGED
        assert probe.resolved == resolved

    def test_failed_status(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        signal_dir = _make_workstream_signal_dir(run_dir, "ws-a")
        (signal_dir / "failed").write_text("")

        probe = _probe_workstream_state(run_dir, "ws-a", tmp_path, "demo")

        assert probe.status == WorkstreamStatus.FAILED


# ── probe_graph_state (top-level) ──


class TestProbeGraphState:
    def test_empty_run_dir_all_pending(self, tmp_path: Path) -> None:
        graph = _graph_single_task()
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        probe = probe_graph_state(tmp_path, "demo", graph, run_dir, _FakeProber())

        assert isinstance(probe, GraphProbe)
        assert set(probe.task_probes.keys()) == {"task_a"}
        assert probe.task_probes["task_a"].status == TaskStatus.PENDING
        # The single-task fixture uses the default workstream.
        assert all(
            p.status == WorkstreamStatus.PENDING
            for p in probe.workstream_probes.values()
        )

    def test_populated_multi_workstream_reconstruction(self, tmp_path: Path) -> None:
        graph = _graph_two_workstreams()
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        task_a_sig = _make_signal_dir(run_dir, "task_a")
        _write_task_status_file(task_a_sig, "pr_merged")
        _write_done_file(task_a_sig, 0, "https://github.com/org/repo/pull/1")

        task_b_sig = _make_signal_dir(run_dir, "task_b")
        _write_task_status_file(task_b_sig, "pending")

        ws_a_sig = _make_workstream_signal_dir(run_dir, "ws-a")
        (ws_a_sig / "merged").write_text("")

        probe = probe_graph_state(tmp_path, "demo", graph, run_dir, _FakeProber())

        assert probe.task_probes["task_a"].status == TaskStatus.PR_MERGED
        assert (
            probe.task_probes["task_a"].pr_url == "https://github.com/org/repo/pull/1"
        )
        assert probe.task_probes["task_b"].status == TaskStatus.PENDING
        assert probe.workstream_probes["ws-a"].status == WorkstreamStatus.MERGED
        assert probe.workstream_probes["ws-b"].status == WorkstreamStatus.PENDING

    def test_pr_prober_is_threaded_to_task_probes(self, tmp_path: Path) -> None:
        """probe_graph_state passes pr_prober through to per-task normalization."""
        graph = _graph_single_task()
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        signal_dir = _make_signal_dir(run_dir, "task_a")
        _write_task_status_file(signal_dir, "pr_created")
        url = "https://github.com/org/repo/pull/1"
        _write_done_file(signal_dir, 0, url)

        prober = _FakeProber(merged_urls={url})
        probe_graph_state(tmp_path, "demo", graph, run_dir, prober)

        assert prober.is_merged_calls == [url]


# ── Type assertions ──


class TestProbeDataclasses:
    def test_task_probe_is_frozen(self) -> None:
        probe = TaskProbe(
            task_id="task_a",
            status=TaskStatus.PENDING,
            signal_dir=Path("/tmp/x"),
            attempt_num=0,
            branch_name="agentrelay/demo/task_a",
            pr_url=None,
            resolved=None,
        )
        try:
            probe.task_id = "other"  # type: ignore[misc]
        except Exception:
            pass
        else:
            raise AssertionError("TaskProbe should be frozen")

    def test_workstream_probe_is_frozen(self) -> None:
        probe = WorkstreamProbe(
            workstream_id="ws-a",
            status=WorkstreamStatus.PENDING,
            signal_dir=Path("/tmp/x"),
            worktree_path=Path("/tmp/y"),
            branch_name="agentrelay/demo/ws-a/integration",
            merge_pr_url=None,
            resolved=None,
        )
        try:
            probe.workstream_id = "other"  # type: ignore[misc]
        except Exception:
            pass
        else:
            raise AssertionError("WorkstreamProbe should be frozen")
