"""Tests for task_runtime_builder: graph -> initial runtime map."""

import tempfile
from pathlib import Path

from agentrelay.orchestrator.builders import TaskRuntimeBuilder
from agentrelay.orchestrator.probe import GraphProbe, TaskProbe
from agentrelay.task import AgentRole, Task
from agentrelay.task_graph import TaskGraph
from agentrelay.task_runtime import TaskStatus


def _task(task_id: str, dependencies: tuple[str, ...] = ()) -> Task:
    return Task(id=task_id, role=AgentRole.GENERIC, dependencies=dependencies)


def _graph() -> TaskGraph:
    task_a = _task("a")
    task_b = _task("b", dependencies=("a",))
    task_c = _task("c", dependencies=("a",))
    return TaskGraph.from_tasks([task_c, task_b, task_a], name="demo")


def test_from_graph_builds_runtime_for_each_task() -> None:
    graph = _graph()

    runtimes = TaskRuntimeBuilder.from_graph(graph)

    assert tuple(runtimes.keys()) == graph.task_ids()
    assert set(runtimes.keys()) == {"a", "b", "c"}


def test_runtime_task_object_identity_matches_graph() -> None:
    graph = _graph()

    runtimes = TaskRuntimeBuilder.from_graph(graph)

    for task_id in graph.task_ids():
        assert runtimes[task_id].task is graph.task(task_id)


def test_runtime_defaults_state_artifacts_and_agent() -> None:
    graph = _graph()
    runtimes = TaskRuntimeBuilder.from_graph(graph)

    for runtime in runtimes.values():
        assert runtime.status == TaskStatus.PENDING
        assert runtime.state.worktree_path is None
        assert runtime.state.branch_name is None
        assert runtime.state.error is None
        assert runtime.state.attempt_num == 0
        assert runtime.artifacts.pr_url is None
        assert runtime.artifacts.concerns == []
        assert runtime.artifacts.agent_address is None


def test_runtime_mutation_isolated_per_task_state() -> None:
    graph = _graph()
    runtimes = TaskRuntimeBuilder.from_graph(graph)

    runtimes["a"].state.signal_dir = Path(tempfile.mkdtemp())
    runtimes["a"].mark_running()
    runtimes["a"].state.worktree_path = Path("/tmp/worktree-a")

    assert runtimes["b"].status == TaskStatus.PENDING
    assert runtimes["b"].state.worktree_path is None
    assert runtimes["c"].status == TaskStatus.PENDING
    assert runtimes["c"].state.worktree_path is None


def test_runtime_mutation_isolated_per_task_artifacts() -> None:
    graph = _graph()
    runtimes = TaskRuntimeBuilder.from_graph(graph)

    runtimes["a"].artifacts.concerns.append("first concern")
    runtimes["a"].artifacts.pr_url = "https://example.com/pr/1"

    assert runtimes["b"].artifacts.concerns == []
    assert runtimes["b"].artifacts.pr_url is None
    assert runtimes["c"].artifacts.concerns == []
    assert runtimes["c"].artifacts.pr_url is None


def test_from_graph_returns_fresh_runtime_objects_each_call() -> None:
    graph = _graph()

    runtimes_1 = TaskRuntimeBuilder.from_graph(graph)
    runtimes_2 = TaskRuntimeBuilder.from_graph(graph)

    for task_id in graph.task_ids():
        assert runtimes_1[task_id] is not runtimes_2[task_id]
        assert runtimes_1[task_id].state is not runtimes_2[task_id].state
        assert runtimes_1[task_id].artifacts is not runtimes_2[task_id].artifacts


def test_from_graph_runtimes_can_track_different_lifecycle_states() -> None:
    graph = _graph()
    runtimes = TaskRuntimeBuilder.from_graph(graph)

    for rt in runtimes.values():
        rt.state.signal_dir = Path(tempfile.mkdtemp())

    runtimes["a"].mark_pr_merged()
    runtimes["b"].mark_running()
    runtimes["c"].mark_failed("test error")

    assert runtimes["a"].status == TaskStatus.PR_MERGED
    assert runtimes["b"].status == TaskStatus.RUNNING
    assert runtimes["c"].status == TaskStatus.FAILED


# ── from_probe ──


def _empty_probe(graph: TaskGraph, run_dir: Path) -> GraphProbe:
    """Build a probe where no task has a signal directory (all PENDING)."""
    task_probes = {
        task_id: TaskProbe(
            task_id=task_id,
            status=TaskStatus.PENDING,
            signal_dir=run_dir / "signals" / task_id,
            attempt_num=0,
            branch_name=f"agentrelay/demo/{task_id}",
            pr_url=None,
            resolved=None,
        )
        for task_id in graph.task_ids()
    }
    return GraphProbe(task_probes=task_probes, workstream_probes={})


def test_from_probe_empty_probe_matches_from_graph() -> None:
    graph = _graph()
    run_dir = Path(tempfile.mkdtemp())
    probe = _empty_probe(graph, run_dir)

    runtimes = TaskRuntimeBuilder.from_probe(graph, probe)
    fresh = TaskRuntimeBuilder.from_graph(graph)

    assert set(runtimes.keys()) == set(fresh.keys())
    for task_id in graph.task_ids():
        assert runtimes[task_id].status == fresh[task_id].status
        assert runtimes[task_id].state.signal_dir is None
        assert runtimes[task_id].state.branch_name is None
        assert runtimes[task_id].state.attempt_num == 0
        assert runtimes[task_id].artifacts.pr_url is None


def test_from_probe_populates_state_from_probe() -> None:
    graph = _graph()
    run_dir = Path(tempfile.mkdtemp())

    # Create signal_dir on disk for task "a" so from_probe populates state.
    task_a_sig = run_dir / "signals" / "a"
    task_a_sig.mkdir(parents=True)
    (task_a_sig / "status").mkdir()
    (task_a_sig / "status" / "pr_merged").write_text("")

    probe = GraphProbe(
        task_probes={
            "a": TaskProbe(
                task_id="a",
                status=TaskStatus.PR_MERGED,
                signal_dir=task_a_sig,
                attempt_num=1,
                branch_name="agentrelay/demo/a",
                pr_url="https://github.com/org/repo/pull/1",
                resolved=None,
            ),
            "b": TaskProbe(
                task_id="b",
                status=TaskStatus.PENDING,
                signal_dir=run_dir / "signals" / "b",
                attempt_num=0,
                branch_name="agentrelay/demo/b",
                pr_url=None,
                resolved=None,
            ),
            "c": TaskProbe(
                task_id="c",
                status=TaskStatus.PENDING,
                signal_dir=run_dir / "signals" / "c",
                attempt_num=0,
                branch_name="agentrelay/demo/c",
                pr_url=None,
                resolved=None,
            ),
        },
        workstream_probes={},
    )

    runtimes = TaskRuntimeBuilder.from_probe(graph, probe)

    # Task "a" has a signal dir → state populated.
    assert runtimes["a"].state.signal_dir == task_a_sig
    assert runtimes["a"].state.branch_name == "agentrelay/demo/a"
    assert runtimes["a"].state.attempt_num == 1
    assert runtimes["a"].artifacts.pr_url == "https://github.com/org/repo/pull/1"

    # Tasks "b"/"c" have no signal dir → defaults.
    assert runtimes["b"].state.signal_dir is None
    assert runtimes["c"].state.signal_dir is None


def test_from_probe_runtime_status_round_trips_from_disk() -> None:
    """Runtime.status reads from disk via signal_dir, so the reconstructed
    runtime should expose the same status the probe captured."""
    graph = _graph()
    run_dir = Path(tempfile.mkdtemp())

    task_a_sig = run_dir / "signals" / "a"
    task_a_sig.mkdir(parents=True)
    (task_a_sig / "status").mkdir()
    (task_a_sig / "status" / "pr_merged").write_text("")

    probe = GraphProbe(
        task_probes={
            "a": TaskProbe(
                task_id="a",
                status=TaskStatus.PR_MERGED,
                signal_dir=task_a_sig,
                attempt_num=0,
                branch_name="agentrelay/demo/a",
                pr_url=None,
                resolved=None,
            ),
            "b": TaskProbe(
                task_id="b",
                status=TaskStatus.PENDING,
                signal_dir=run_dir / "signals" / "b",
                attempt_num=0,
                branch_name="agentrelay/demo/b",
                pr_url=None,
                resolved=None,
            ),
            "c": TaskProbe(
                task_id="c",
                status=TaskStatus.PENDING,
                signal_dir=run_dir / "signals" / "c",
                attempt_num=0,
                branch_name="agentrelay/demo/c",
                pr_url=None,
                resolved=None,
            ),
        },
        workstream_probes={},
    )

    runtimes = TaskRuntimeBuilder.from_probe(graph, probe)

    # runtime.status reads the on-disk signal file via
    # _read_task_status_from_signals, so we verify the contract directly.
    assert runtimes["a"].status == TaskStatus.PR_MERGED
    assert runtimes["b"].status == TaskStatus.PENDING
    assert runtimes["c"].status == TaskStatus.PENDING


def test_from_probe_returns_fresh_runtime_objects_each_call() -> None:
    graph = _graph()
    probe = _empty_probe(graph, Path(tempfile.mkdtemp()))

    runtimes_1 = TaskRuntimeBuilder.from_probe(graph, probe)
    runtimes_2 = TaskRuntimeBuilder.from_probe(graph, probe)

    for task_id in graph.task_ids():
        assert runtimes_1[task_id] is not runtimes_2[task_id]
        assert runtimes_1[task_id].state is not runtimes_2[task_id].state
        assert runtimes_1[task_id].artifacts is not runtimes_2[task_id].artifacts
