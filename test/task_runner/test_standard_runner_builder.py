"""Tests for build_standard_runner builder function."""

from pathlib import Path

from agentrelay.task import AgentRole, Task
from agentrelay.task_graph import TaskGraph
from agentrelay.task_runner import (
    StandardTaskRunner,
    build_standard_runner,
)
from agentrelay.task_runner.implementations import (
    GhTaskMerger,
    SignalCompletionChecker,
    TmuxTaskKickoff,
    TmuxTaskLauncher,
    WorktreeTaskPreparer,
    WorktreeTaskTeardown,
)
from agentrelay.task_runtime import TaskRuntime


def _graph_with_deps() -> TaskGraph:
    task_a = Task(id="a", role=AgentRole.GENERIC, description="task A")
    task_b = Task(
        id="b",
        role=AgentRole.GENERIC,
        description="task B",
        dependencies=("a",),
    )
    return TaskGraph.from_tasks((task_a, task_b))


def test_build_returns_standard_task_runner() -> None:
    graph = _graph_with_deps()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        graph=graph,
    )
    assert isinstance(runner, StandardTaskRunner)


def test_preparer_dispatch_returns_worktree_task_preparer() -> None:
    graph = _graph_with_deps()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        graph=graph,
    )
    runtime = TaskRuntime(task=graph.task("b"))
    preparer = runner._preparer(runtime)
    assert isinstance(preparer, WorktreeTaskPreparer)


def test_preparer_computes_dependency_descriptions() -> None:
    graph = _graph_with_deps()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        graph=graph,
    )
    runtime = TaskRuntime(task=graph.task("b"))
    preparer = runner._preparer(runtime)
    assert isinstance(preparer, WorktreeTaskPreparer)
    assert preparer.dependency_descriptions == {"a": "task A"}


def test_launcher_dispatch_returns_tmux_launcher() -> None:
    graph = _graph_with_deps()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        graph=graph,
    )
    runtime = TaskRuntime(task=graph.task("a"))
    assert isinstance(runner._launcher(runtime), TmuxTaskLauncher)


def test_kickoff_dispatch_returns_tmux_kickoff() -> None:
    graph = _graph_with_deps()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        graph=graph,
    )
    runtime = TaskRuntime(task=graph.task("a"))
    assert isinstance(runner._kickoff(runtime), TmuxTaskKickoff)


def test_completion_checker_dispatch_returns_signal_checker() -> None:
    graph = _graph_with_deps()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        graph=graph,
        poll_interval=5.0,
    )
    runtime = TaskRuntime(task=graph.task("a"))
    checker = runner._completion_checker(runtime)
    assert isinstance(checker, SignalCompletionChecker)
    assert checker.poll_interval == 5.0


def test_merger_dispatch_returns_gh_merger() -> None:
    graph = _graph_with_deps()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        graph=graph,
    )
    runtime = TaskRuntime(task=graph.task("a"))
    merger = runner._merger(runtime)
    assert isinstance(merger, GhTaskMerger)
    assert merger.repo_path == Path("/repo")


def test_teardown_dispatch_returns_worktree_teardown() -> None:
    graph = _graph_with_deps()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        graph=graph,
        keep_panes=True,
    )
    runtime = TaskRuntime(task=graph.task("a"))
    teardown = runner._teardown(runtime)
    assert isinstance(teardown, WorktreeTaskTeardown)
    assert teardown.keep_panes is True
