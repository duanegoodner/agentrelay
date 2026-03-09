"""Tests for workstream_runtime_builder: graph -> initial workstream runtimes."""

from pathlib import Path

from agentrelay.task import AgentRole, Task
from agentrelay.task_graph import TaskGraph
from agentrelay.workstream import WorkstreamSpec
from agentrelay.workstream.runtime import WorkstreamStatus
from agentrelay.workstream.runtime_builder import WorkstreamRuntimeBuilder


def _task(
    task_id: str,
    dependencies: tuple[Task, ...] = (),
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
    task_b = _task("b", dependencies=(task_a,), workstream_id="feature_b")
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
        assert runtime.state.status == WorkstreamStatus.PENDING
        assert runtime.state.worktree_path is None
        assert runtime.state.branch_name is None
        assert runtime.state.error is None
        assert runtime.state.active_task_id is None
        assert runtime.artifacts.merge_pr_url is None
        assert runtime.artifacts.concerns == []


def test_runtime_mutation_isolated_per_workstream_state() -> None:
    graph = _graph()
    runtimes = WorkstreamRuntimeBuilder.from_graph(graph)

    runtimes["feature_a"].state.status = WorkstreamStatus.ACTIVE
    runtimes["feature_a"].state.worktree_path = Path("/tmp/worktree-feature-a")
    runtimes["feature_a"].state.active_task_id = "a"

    assert runtimes["feature_b"].state.status == WorkstreamStatus.PENDING
    assert runtimes["feature_b"].state.worktree_path is None
    assert runtimes["feature_b"].state.active_task_id is None


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

    runtimes["feature_a"].state.status = WorkstreamStatus.MERGED
    runtimes["feature_b"].state.status = WorkstreamStatus.FAILED

    assert runtimes["feature_a"].state.status == WorkstreamStatus.MERGED
    assert runtimes["feature_b"].state.status == WorkstreamStatus.FAILED
