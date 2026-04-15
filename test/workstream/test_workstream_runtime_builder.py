"""Tests for workstream_runtime_builder: graph -> initial workstream runtimes."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from agentrelay.orchestrator.builders import WorkstreamRuntimeBuilder
from agentrelay.orchestrator.probe import GraphProbe, WorkstreamProbe
from agentrelay.resolved import ResolvedWorkstream
from agentrelay.task import AgentRole, Task
from agentrelay.task_graph import TaskGraph
from agentrelay.workstream import WorkstreamSpec, WorkstreamStatus


def _task(
    task_id: str,
    dependencies: tuple[str, ...] = (),
    workstream_id: str = "default",
) -> Task:
    return Task(
        id=task_id,
        role=AgentRole.GENERIC,
        dependencies=dependencies,
        workstream_id=workstream_id,
    )


def _graph() -> TaskGraph:
    task_a = _task("a", workstream_id="feature_a")
    task_b = _task("b", dependencies=("a",), workstream_id="feature_b")
    return TaskGraph.from_tasks(
        [task_b, task_a],
        workstreams=[
            WorkstreamSpec(id="feature_a"),
            WorkstreamSpec(id="feature_b", parent_workstream_id="feature_a"),
        ],
    )


def test_from_graph_builds_runtime_for_each_workstream() -> None:
    graph = _graph()

    runtimes = WorkstreamRuntimeBuilder.from_graph(graph)

    assert tuple(runtimes.keys()) == graph.workstream_ids()
    assert set(runtimes.keys()) == {"feature_a", "feature_b"}


def test_runtime_spec_identity_matches_graph() -> None:
    graph = _graph()

    runtimes = WorkstreamRuntimeBuilder.from_graph(graph)

    for workstream_id in graph.workstream_ids():
        assert runtimes[workstream_id].spec is graph.workstream(workstream_id)


def test_runtime_defaults_state_and_artifacts() -> None:
    graph = _graph()
    runtimes = WorkstreamRuntimeBuilder.from_graph(graph)

    for runtime in runtimes.values():
        assert runtime.status == WorkstreamStatus.PENDING
        assert runtime.state.worktree_path is None
        assert runtime.state.branch_name is None
        assert runtime.state.error is None
        assert runtime.artifacts.merge_pr_url is None
        assert runtime.artifacts.concerns == []


def test_runtime_mutation_isolated_per_workstream_state() -> None:
    graph = _graph()
    runtimes = WorkstreamRuntimeBuilder.from_graph(graph)

    runtimes["feature_a"].state.signal_dir = Path(tempfile.mkdtemp())
    runtimes["feature_a"].mark_pending()
    runtimes["feature_a"].mark_active()
    runtimes["feature_a"].state.worktree_path = Path("/tmp/worktree-feature-a")

    assert runtimes["feature_b"].status == WorkstreamStatus.PENDING
    assert runtimes["feature_b"].state.worktree_path is None


def test_runtime_mutation_isolated_per_workstream_artifacts() -> None:
    graph = _graph()
    runtimes = WorkstreamRuntimeBuilder.from_graph(graph)

    runtimes["feature_a"].artifacts.concerns.append("lane concern")
    runtimes["feature_a"].artifacts.merge_pr_url = "https://example.com/pr/42"

    assert runtimes["feature_b"].artifacts.concerns == []
    assert runtimes["feature_b"].artifacts.merge_pr_url is None


def test_from_graph_returns_fresh_runtime_objects_each_call() -> None:
    graph = _graph()

    runtimes_1 = WorkstreamRuntimeBuilder.from_graph(graph)
    runtimes_2 = WorkstreamRuntimeBuilder.from_graph(graph)

    for workstream_id in graph.workstream_ids():
        assert runtimes_1[workstream_id] is not runtimes_2[workstream_id]
        assert runtimes_1[workstream_id].state is not runtimes_2[workstream_id].state
        assert (
            runtimes_1[workstream_id].artifacts
            is not runtimes_2[workstream_id].artifacts
        )


def test_from_graph_runtimes_can_track_different_lifecycle_states() -> None:
    graph = _graph()
    runtimes = WorkstreamRuntimeBuilder.from_graph(graph)

    for ws_id in ("feature_a", "feature_b"):
        runtimes[ws_id].state.signal_dir = Path(tempfile.mkdtemp())

    runtimes["feature_a"].mark_merged()
    runtimes["feature_b"].mark_failed("test failure")

    assert runtimes["feature_a"].status == WorkstreamStatus.MERGED
    assert runtimes["feature_b"].status == WorkstreamStatus.FAILED


# ── from_probe ──


def _empty_probe(graph: TaskGraph, run_dir: Path) -> GraphProbe:
    """Build a probe where no workstream has a signal directory."""
    workstream_probes = {
        ws_id: WorkstreamProbe(
            workstream_id=ws_id,
            status=WorkstreamStatus.PENDING,
            signal_dir=run_dir / "workstreams" / ws_id,
            worktree_path=Path("/unused") / ws_id,
            branch_name=f"agentrelay/demo/{ws_id}/integration",
            merge_pr_url=None,
            resolved=None,
        )
        for ws_id in graph.workstream_ids()
    }
    return GraphProbe(task_probes={}, workstream_probes=workstream_probes)


def test_from_probe_empty_probe_matches_from_graph() -> None:
    graph = _graph()
    run_dir = Path(tempfile.mkdtemp())
    probe = _empty_probe(graph, run_dir)

    runtimes = WorkstreamRuntimeBuilder.from_probe(graph, probe)
    fresh = WorkstreamRuntimeBuilder.from_graph(graph)

    assert set(runtimes.keys()) == set(fresh.keys())
    for ws_id in graph.workstream_ids():
        assert runtimes[ws_id].status == fresh[ws_id].status
        assert runtimes[ws_id].state.signal_dir is None
        assert runtimes[ws_id].state.worktree_path is None
        assert runtimes[ws_id].state.branch_name is None


def test_from_probe_populates_state_and_artifacts() -> None:
    graph = _graph()
    run_dir = Path(tempfile.mkdtemp())

    ws_a_sig = run_dir / "workstreams" / "feature_a"
    ws_a_sig.mkdir(parents=True)
    (ws_a_sig / "merged").write_text("")
    ws_a_worktree = Path("/repo/.worktrees/demo/feature_a")

    resolved = ResolvedWorkstream(
        workstream_id="feature_a",
        integration_pr_url="https://github.com/org/repo/pull/5",
        target_branch="main",
        target_branch_before_any_merge="abc123",
        merge_occurred=True,
        merged_at=datetime.now(timezone.utc).isoformat(),
    )

    probe = GraphProbe(
        task_probes={},
        workstream_probes={
            "feature_a": WorkstreamProbe(
                workstream_id="feature_a",
                status=WorkstreamStatus.MERGED,
                signal_dir=ws_a_sig,
                worktree_path=ws_a_worktree,
                branch_name="agentrelay/demo/feature_a/integration",
                merge_pr_url="https://github.com/org/repo/pull/5",
                resolved=resolved,
            ),
            "feature_b": WorkstreamProbe(
                workstream_id="feature_b",
                status=WorkstreamStatus.PENDING,
                signal_dir=run_dir / "workstreams" / "feature_b",
                worktree_path=Path("/unused/feature_b"),
                branch_name="agentrelay/demo/feature_b/integration",
                merge_pr_url=None,
                resolved=None,
            ),
        },
    )

    runtimes = WorkstreamRuntimeBuilder.from_probe(graph, probe)

    # feature_a has signal dir → state + artifacts populated.
    assert runtimes["feature_a"].state.signal_dir == ws_a_sig
    assert runtimes["feature_a"].state.worktree_path == ws_a_worktree
    assert (
        runtimes["feature_a"].state.branch_name
        == "agentrelay/demo/feature_a/integration"
    )
    assert (
        runtimes["feature_a"].artifacts.merge_pr_url
        == "https://github.com/org/repo/pull/5"
    )
    assert runtimes["feature_a"].artifacts.target_branch_before_any_merge == "abc123"

    # feature_b has no signal dir → defaults.
    assert runtimes["feature_b"].state.signal_dir is None
    assert runtimes["feature_b"].artifacts.merge_pr_url is None
    assert runtimes["feature_b"].artifacts.target_branch_before_any_merge is None


def test_from_probe_runtime_status_round_trips_from_disk() -> None:
    """Runtime.status reads signal files from disk; the reconstructed runtime
    should expose the same status the probe captured."""
    graph = _graph()
    run_dir = Path(tempfile.mkdtemp())

    ws_a_sig = run_dir / "workstreams" / "feature_a"
    ws_a_sig.mkdir(parents=True)
    (ws_a_sig / "merged").write_text("")

    probe = GraphProbe(
        task_probes={},
        workstream_probes={
            "feature_a": WorkstreamProbe(
                workstream_id="feature_a",
                status=WorkstreamStatus.MERGED,
                signal_dir=ws_a_sig,
                worktree_path=Path("/repo/.worktrees/demo/feature_a"),
                branch_name="agentrelay/demo/feature_a/integration",
                merge_pr_url=None,
                resolved=None,
            ),
            "feature_b": WorkstreamProbe(
                workstream_id="feature_b",
                status=WorkstreamStatus.PENDING,
                signal_dir=run_dir / "workstreams" / "feature_b",
                worktree_path=Path("/unused"),
                branch_name="agentrelay/demo/feature_b/integration",
                merge_pr_url=None,
                resolved=None,
            ),
        },
    )

    runtimes = WorkstreamRuntimeBuilder.from_probe(graph, probe)

    assert runtimes["feature_a"].status == WorkstreamStatus.MERGED
    assert runtimes["feature_b"].status == WorkstreamStatus.PENDING


def test_from_probe_returns_fresh_runtime_objects_each_call() -> None:
    graph = _graph()
    probe = _empty_probe(graph, Path(tempfile.mkdtemp()))

    runtimes_1 = WorkstreamRuntimeBuilder.from_probe(graph, probe)
    runtimes_2 = WorkstreamRuntimeBuilder.from_probe(graph, probe)

    for ws_id in graph.workstream_ids():
        assert runtimes_1[ws_id] is not runtimes_2[ws_id]
        assert runtimes_1[ws_id].state is not runtimes_2[ws_id].state
        assert runtimes_1[ws_id].artifacts is not runtimes_2[ws_id].artifacts
