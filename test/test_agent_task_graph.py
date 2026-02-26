from pathlib import Path

import pytest
import yaml

from agentrelaysmall.agent_task import AgentTask, TaskStatus
from agentrelaysmall.agent_task_graph import AgentTaskGraph, AgentTaskGraphBuilder

# ── helpers ───────────────────────────────────────────────────────────────────


def make_graph(
    tasks: list[AgentTask] | None = None,
    target_repo_root: Path | None = None,
    worktrees_root: Path | None = None,
    name: str = "demo",
) -> AgentTaskGraph:
    if tasks is None:
        tasks = [AgentTask(id="task_001", description="do something")]
    if target_repo_root is None:
        target_repo_root = Path("/repo")
    if worktrees_root is None:
        worktrees_root = Path("/worktrees")
    return AgentTaskGraph(
        name=name,
        tasks={t.id: t for t in tasks},
        target_repo_root=target_repo_root,
        worktrees_root=worktrees_root,
    )


# ── path computation ──────────────────────────────────────────────────────────


def test_signal_dir_uses_graph_name_and_task_id():
    graph = make_graph(name="my-graph", target_repo_root=Path("/repo"))
    assert graph.signal_dir("task_001") == Path(
        "/repo/.workflow/my-graph/signals/task_001"
    )


def test_worktree_path_uses_graph_name_and_task_id():
    graph = make_graph(name="my-graph", worktrees_root=Path("/wt"))
    assert graph.worktree_path("task_001") == Path("/wt/my-graph/task_001")


def test_branch_name_uses_graph_name_and_task_id():
    graph = make_graph(name="my-graph")
    assert graph.branch_name("task_001") == "task/my-graph/task_001"


# ── _refresh_ready ────────────────────────────────────────────────────────────


def test_refresh_ready_promotes_task_with_no_deps():
    t = AgentTask(id="task_001", description="x")
    graph = make_graph(tasks=[t])
    assert t.state.status == TaskStatus.PENDING
    graph._refresh_ready()
    assert t.state.status == TaskStatus.READY


def test_refresh_ready_promotes_when_all_deps_done():
    dep = AgentTask(id="dep", description="x")
    dep.state.status = TaskStatus.DONE
    child = AgentTask(id="child", description="y", dependencies=("dep",))
    graph = make_graph(tasks=[dep, child])
    graph._refresh_ready()
    assert child.state.status == TaskStatus.READY


def test_refresh_ready_does_not_promote_when_dep_pending():
    dep = AgentTask(id="dep", description="x")
    child = AgentTask(id="child", description="y", dependencies=("dep",))
    graph = make_graph(tasks=[dep, child])
    graph._refresh_ready()
    assert child.state.status == TaskStatus.PENDING


def test_refresh_ready_does_not_change_already_done():
    t = AgentTask(id="task_001", description="x")
    t.state.status = TaskStatus.DONE
    graph = make_graph(tasks=[t])
    graph._refresh_ready()
    assert t.state.status == TaskStatus.DONE


# ── ready_tasks / running_tasks ───────────────────────────────────────────────


def test_ready_tasks_returns_only_ready():
    t1 = AgentTask(id="t1", description="x")
    t1.state.status = TaskStatus.READY
    t2 = AgentTask(id="t2", description="y")
    t2.state.status = TaskStatus.RUNNING
    graph = make_graph(tasks=[t1, t2])
    assert graph.ready_tasks() == [t1]


def test_running_tasks_returns_only_running():
    t1 = AgentTask(id="t1", description="x")
    t1.state.status = TaskStatus.RUNNING
    t2 = AgentTask(id="t2", description="y")
    t2.state.status = TaskStatus.DONE
    graph = make_graph(tasks=[t1, t2])
    assert graph.running_tasks() == [t1]


# ── is_complete ───────────────────────────────────────────────────────────────


def test_is_complete_when_all_done():
    t1 = AgentTask(id="t1", description="x")
    t1.state.status = TaskStatus.DONE
    t2 = AgentTask(id="t2", description="y")
    t2.state.status = TaskStatus.DONE
    graph = make_graph(tasks=[t1, t2])
    assert graph.is_complete() is True


def test_is_complete_when_mix_done_and_failed():
    t1 = AgentTask(id="t1", description="x")
    t1.state.status = TaskStatus.DONE
    t2 = AgentTask(id="t2", description="y")
    t2.state.status = TaskStatus.FAILED
    graph = make_graph(tasks=[t1, t2])
    assert graph.is_complete() is True


def test_is_complete_false_when_any_not_terminal():
    t1 = AgentTask(id="t1", description="x")
    t1.state.status = TaskStatus.DONE
    t2 = AgentTask(id="t2", description="y")
    t2.state.status = TaskStatus.RUNNING
    graph = make_graph(tasks=[t1, t2])
    assert graph.is_complete() is False


# ── hydrate_from_signals ──────────────────────────────────────────────────────


def test_hydrate_sets_done_from_merged(tmp_path):
    t = AgentTask(id="task_001", description="x")
    graph = make_graph(tasks=[t], target_repo_root=tmp_path)
    sig_dir = graph.signal_dir("task_001")
    sig_dir.mkdir(parents=True)
    (sig_dir / ".merged").write_text("2024-01-01T00:00:00+00:00")
    graph.hydrate_from_signals()
    assert t.state.status == TaskStatus.DONE


def test_hydrate_sets_failed_from_failed_signal(tmp_path):
    t = AgentTask(id="task_001", description="x")
    graph = make_graph(tasks=[t], target_repo_root=tmp_path)
    sig_dir = graph.signal_dir("task_001")
    sig_dir.mkdir(parents=True)
    (sig_dir / ".failed").write_text("2024-01-01T00:00:00+00:00\nreason")
    graph.hydrate_from_signals()
    assert t.state.status == TaskStatus.FAILED


def test_hydrate_leaves_pending_when_no_signals(tmp_path):
    t = AgentTask(id="task_001", description="x")
    graph = make_graph(tasks=[t], target_repo_root=tmp_path)
    graph.hydrate_from_signals()
    assert t.state.status == TaskStatus.PENDING


def test_hydrate_merged_takes_precedence_over_failed(tmp_path):
    t = AgentTask(id="task_001", description="x")
    graph = make_graph(tasks=[t], target_repo_root=tmp_path)
    sig_dir = graph.signal_dir("task_001")
    sig_dir.mkdir(parents=True)
    (sig_dir / ".merged").write_text("2024-01-01T00:00:00+00:00")
    (sig_dir / ".failed").write_text("earlier failure")
    graph.hydrate_from_signals()
    assert t.state.status == TaskStatus.DONE


# ── AgentTaskGraphBuilder ─────────────────────────────────────────────────────


def write_yaml(tmp_path: Path, content: dict) -> Path:
    p = tmp_path / "graph.yaml"
    p.write_text(yaml.dump(content))
    return p


def test_builder_from_yaml_sets_graph_name(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "my-graph",
            "tasks": [{"id": "t1", "description": "do it", "dependencies": []}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path, tmp_path / "wt")
    assert graph.name == "my-graph"


def test_builder_from_yaml_creates_tasks(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [
                {"id": "t1", "description": "first"},
                {"id": "t2", "description": "second", "dependencies": ["t1"]},
            ],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path, tmp_path / "wt")
    assert set(graph.tasks.keys()) == {"t1", "t2"}


def test_builder_from_yaml_sets_dependencies(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [
                {"id": "t1", "description": "first"},
                {"id": "t2", "description": "second", "dependencies": ["t1"]},
            ],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path, tmp_path / "wt")
    assert graph.tasks["t2"].dependencies == ("t1",)


def test_builder_from_yaml_empty_dependencies(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [{"id": "t1", "description": "first"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path, tmp_path / "wt")
    assert graph.tasks["t1"].dependencies == ()


def test_builder_from_yaml_sets_target_repo_root(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [{"id": "t1", "description": "x"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path, tmp_path / "wt")
    assert graph.target_repo_root == tmp_path


def test_builder_from_yaml_reads_target_repo_from_yaml(tmp_path):
    other_repo = tmp_path / "other"
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "target_repo": str(other_repo),
            "tasks": [{"id": "t1", "description": "x"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path, tmp_path / "wt")
    assert graph.target_repo_root == other_repo


def test_builder_from_yaml_defaults_to_repo_root_when_no_target_repo(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [{"id": "t1", "description": "x"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path, tmp_path / "wt")
    assert graph.target_repo_root == tmp_path


def test_builder_from_yaml_sets_worktrees_root(tmp_path):
    wt = tmp_path / "wt"
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [{"id": "t1", "description": "x"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path, wt)
    assert graph.worktrees_root == wt


def test_builder_from_yaml_default_tmux_session(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [{"id": "t1", "description": "x"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path, tmp_path / "wt")
    assert graph.tmux_session == "agentrelaysmall"


def test_builder_from_yaml_custom_tmux_session(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tmux_session": "myproject",
            "tasks": [{"id": "t1", "description": "x"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path, tmp_path / "wt")
    assert graph.tmux_session == "myproject"


def test_builder_from_yaml_default_keep_panes(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [{"id": "t1", "description": "x"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path, tmp_path / "wt")
    assert graph.keep_panes is False


def test_builder_from_yaml_keep_panes_true(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "keep_panes": True,
            "tasks": [{"id": "t1", "description": "x"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path, tmp_path / "wt")
    assert graph.keep_panes is True


# ── write_context (task_launcher) ─────────────────────────────────────────────


def test_write_context_creates_file(tmp_path):
    from agentrelaysmall.agent_task import AgentTask
    from agentrelaysmall.task_launcher import write_context

    task = AgentTask(id="t1", description="x")
    task.state.worktree_path = tmp_path
    write_context(task, "# Context\nsome info")
    assert (tmp_path / "context.md").read_text() == "# Context\nsome info"


def test_write_context_requires_worktree_path():
    from agentrelaysmall.agent_task import AgentTask
    from agentrelaysmall.task_launcher import write_context

    task = AgentTask(id="t1", description="x")
    with pytest.raises(AssertionError):
        write_context(task, "content")
