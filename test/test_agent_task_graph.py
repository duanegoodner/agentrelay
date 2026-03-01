from pathlib import Path

import pytest
import yaml

from agentrelaysmall.agent_task import AgentRole, AgentTask, TaskStatus
from agentrelaysmall.agent_task_graph import (
    AgentTaskGraph,
    AgentTaskGraphBuilder,
    TDDTaskGroup,
)

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


def test_graph_branch_uses_graph_name():
    graph = make_graph(name="my-graph")
    assert graph.graph_branch() == "graph/my-graph"


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
    child = AgentTask(id="child", description="y", dependencies=(dep,))
    graph = make_graph(tasks=[dep, child])
    graph._refresh_ready()
    assert child.state.status == TaskStatus.READY


def test_refresh_ready_does_not_promote_when_dep_pending():
    dep = AgentTask(id="dep", description="x")
    child = AgentTask(id="child", description="y", dependencies=(dep,))
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


# ── next_agent_index ──────────────────────────────────────────────────────────


def test_next_agent_index_starts_at_zero():
    graph = make_graph()
    assert graph.next_agent_index() == 0


def test_next_agent_index_increments():
    graph = make_graph()
    assert graph.next_agent_index() == 0
    assert graph.next_agent_index() == 1
    assert graph.next_agent_index() == 2


def test_next_agent_index_independent_per_graph():
    g1 = make_graph(name="g1")
    g2 = make_graph(name="g2")
    g1.next_agent_index()
    g1.next_agent_index()
    assert g2.next_agent_index() == 0


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
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
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
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
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
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["t2"].dependency_ids == ("t1",)


def test_builder_from_yaml_empty_dependencies(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [{"id": "t1", "description": "first"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["t1"].dependency_ids == ()


def test_builder_from_yaml_sets_target_repo_root(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [{"id": "t1", "description": "x"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
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
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.target_repo_root == other_repo


def test_builder_from_yaml_defaults_to_repo_root_when_no_target_repo(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [{"id": "t1", "description": "x"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.target_repo_root == tmp_path


def test_builder_from_yaml_derives_worktrees_root_from_target_repo(tmp_path):
    """worktrees_root defaults to target_repo_root.parent / 'worktrees'."""
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [{"id": "t1", "description": "x"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.worktrees_root == tmp_path.parent / "worktrees"


def test_builder_from_yaml_custom_worktrees_root_via_yaml(tmp_path):
    """YAML worktrees_root key overrides the default derived path."""
    custom_wt = tmp_path / "custom_wt"
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "worktrees_root": str(custom_wt),
            "tasks": [{"id": "t1", "description": "x"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.worktrees_root == custom_wt


def test_builder_from_yaml_default_tmux_session(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [{"id": "t1", "description": "x"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
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
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tmux_session == "myproject"


def test_builder_from_yaml_default_keep_panes(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [{"id": "t1", "description": "x"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
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
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.keep_panes is True


# ── TDDTaskGroup dataclass ────────────────────────────────────────────────────


def test_tdd_task_group_creation():
    g = TDDTaskGroup(id="foo", description="implement foo")
    assert g.id == "foo"
    assert g.description == "implement foo"
    assert g.dependencies_single_task == ()
    assert g.dependencies_task_group == ()
    assert g.dependency_ids == ()


def test_tdd_task_group_with_single_task_dependency():
    dep = AgentTask(id="setup", description="setup task")
    g = TDDTaskGroup(id="bar", description="bar", dependencies_single_task=(dep,))
    assert g.dependency_ids == ("setup",)


def test_tdd_task_group_with_group_dependency():
    foo = TDDTaskGroup(id="foo", description="foo")
    g = TDDTaskGroup(id="bar", description="bar", dependencies_task_group=(foo,))
    assert g.dependency_ids == ("foo",)


def test_tdd_task_group_with_mixed_dependencies():
    dep_task = AgentTask(id="setup", description="setup")
    dep_group = TDDTaskGroup(id="foo", description="foo")
    g = TDDTaskGroup(
        id="bar",
        description="bar",
        dependencies_single_task=(dep_task,),
        dependencies_task_group=(dep_group,),
    )
    assert g.dependency_ids == ("setup", "foo")


def test_tdd_task_group_is_frozen():
    g = TDDTaskGroup(id="foo", description="d")
    with pytest.raises(AttributeError):
        g.id = "other"  # type: ignore[misc]


# ── from_yaml with tdd_groups ─────────────────────────────────────────────────


def test_tdd_group_expands_to_three_tasks(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tdd_groups": [{"id": "foo", "description": "implement foo feature"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert set(graph.tasks.keys()) == {"foo_tests", "foo_review", "foo_impl"}


def test_tdd_group_roles_are_correct(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tdd_groups": [{"id": "foo", "description": "d"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["foo_tests"].role == AgentRole.TEST_WRITER
    assert graph.tasks["foo_review"].role == AgentRole.TEST_REVIEWER
    assert graph.tasks["foo_impl"].role == AgentRole.IMPLEMENTER


def test_tdd_group_internal_dependencies(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tdd_groups": [{"id": "foo", "description": "d"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["foo_tests"].dependency_ids == ()
    assert graph.tasks["foo_review"].dependency_ids == ("foo_tests",)
    assert graph.tasks["foo_impl"].dependency_ids == ("foo_review",)


def test_tdd_group_description_propagated_to_all_tasks(tmp_path):
    desc = "implement the greet feature with full TDD"
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tdd_groups": [{"id": "greet", "description": desc}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    for task_id in ("greet_tests", "greet_review", "greet_impl"):
        assert graph.tasks[task_id].description == desc


def test_tdd_group_id_set_on_all_expanded_tasks(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tdd_groups": [{"id": "add_auth", "description": "d"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["add_auth_tests"].tdd_group_id == "add_auth"
    assert graph.tasks["add_auth_review"].tdd_group_id == "add_auth"
    assert graph.tasks["add_auth_impl"].tdd_group_id == "add_auth"


def test_tdd_group_dependency_resolves_group_id_to_impl(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tdd_groups": [
                {"id": "foo", "description": "foo feature"},
                {"id": "bar", "description": "bar feature", "dependencies": ["foo"]},
            ],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["bar_tests"].dependency_ids == ("foo_impl",)


def test_tdd_group_dependency_on_raw_task_passes_through(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [{"id": "setup", "description": "initial setup"}],
            "tdd_groups": [
                {"id": "bar", "description": "bar feature", "dependencies": ["setup"]},
            ],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["bar_tests"].dependency_ids == ("setup",)


def test_mixed_yaml_tasks_and_tdd_groups(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [{"id": "setup", "description": "setup step"}],
            "tdd_groups": [{"id": "feature", "description": "the feature"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert set(graph.tasks.keys()) == {
        "setup",
        "feature_tests",
        "feature_review",
        "feature_impl",
    }


def test_plain_task_in_mixed_yaml_has_generic_role(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [{"id": "setup", "description": "setup"}],
            "tdd_groups": [{"id": "feature", "description": "d"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["setup"].role == AgentRole.GENERIC


def test_plain_task_has_none_tdd_group_id(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [{"id": "setup", "description": "setup"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["setup"].tdd_group_id is None


def test_from_yaml_without_tdd_groups_key_still_works(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [{"id": "t1", "description": "do it"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert set(graph.tasks.keys()) == {"t1"}
    assert graph.tasks["t1"].role == AgentRole.GENERIC


def test_from_yaml_with_only_tdd_groups_no_tasks_key(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tdd_groups": [{"id": "foo", "description": "d"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert len(graph.tasks) == 3


# ── model selection ───────────────────────────────────────────────────────────


def test_builder_from_yaml_graph_model_defaults_to_none(tmp_path):
    p = write_yaml(tmp_path, {"name": "g", "tasks": [{"id": "t1", "description": "x"}]})
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.model is None


def test_builder_from_yaml_reads_graph_level_model(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "model": "claude-opus-4-6",
            "tasks": [{"id": "t1", "description": "x"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.model == "claude-opus-4-6"


def test_builder_from_yaml_plain_task_model(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [
                {"id": "t1", "description": "x", "model": "claude-haiku-4-5-20251001"}
            ],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["t1"].model == "claude-haiku-4-5-20251001"


def test_builder_from_yaml_plain_task_default_model_is_none(tmp_path):
    p = write_yaml(
        tmp_path,
        {"name": "g", "tasks": [{"id": "t1", "description": "x"}]},
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["t1"].model is None


# ── completion_gate ───────────────────────────────────────────────────────────


def test_builder_from_yaml_plain_task_default_completion_gate_is_none(tmp_path):
    p = write_yaml(tmp_path, {"name": "g", "tasks": [{"id": "t1", "description": "x"}]})
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["t1"].completion_gate is None


def test_builder_from_yaml_plain_task_completion_gate(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [
                {"id": "t1", "description": "x", "completion_gate": "pixi run pytest"}
            ],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["t1"].completion_gate == "pixi run pytest"


def test_builder_from_yaml_tdd_group_model_applies_to_all_subtasks(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tdd_groups": [
                {"id": "foo", "description": "d", "model": "claude-sonnet-4-6"}
            ],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["foo_tests"].model == "claude-sonnet-4-6"
    assert graph.tasks["foo_review"].model == "claude-sonnet-4-6"
    assert graph.tasks["foo_impl"].model == "claude-sonnet-4-6"


def test_builder_from_yaml_tdd_group_per_role_model_override(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tdd_groups": [
                {
                    "id": "foo",
                    "description": "d",
                    "models": {
                        "tests": "claude-haiku-4-5-20251001",
                        "review": "claude-haiku-4-5-20251001",
                        "impl": "claude-opus-4-6",
                    },
                }
            ],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["foo_tests"].model == "claude-haiku-4-5-20251001"
    assert graph.tasks["foo_review"].model == "claude-haiku-4-5-20251001"
    assert graph.tasks["foo_impl"].model == "claude-opus-4-6"


def test_builder_from_yaml_tdd_group_partial_role_override(tmp_path):
    """Only impl is overridden; tests and review fall back to group-level model."""
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tdd_groups": [
                {
                    "id": "foo",
                    "description": "d",
                    "model": "claude-sonnet-4-6",
                    "models": {"impl": "claude-opus-4-6"},
                }
            ],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["foo_tests"].model == "claude-sonnet-4-6"
    assert graph.tasks["foo_review"].model == "claude-sonnet-4-6"
    assert graph.tasks["foo_impl"].model == "claude-opus-4-6"


def test_multiple_tdd_groups_all_expanded(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tdd_groups": [
                {"id": "alpha", "description": "alpha feature"},
                {"id": "beta", "description": "beta feature"},
            ],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert len(graph.tasks) == 6
    assert set(graph.tasks.keys()) == {
        "alpha_tests",
        "alpha_review",
        "alpha_impl",
        "beta_tests",
        "beta_review",
        "beta_impl",
    }


# ── AgentTaskGraph.max_gate_attempts ──────────────────────────────────────────


def test_graph_max_gate_attempts_defaults_to_none():
    graph = make_graph()
    assert graph.max_gate_attempts is None


def test_graph_max_gate_attempts_can_be_set():
    graph = AgentTaskGraph(
        name="g",
        tasks={},
        target_repo_root=Path("/repo"),
        worktrees_root=Path("/wt"),
        max_gate_attempts=3,
    )
    assert graph.max_gate_attempts == 3


def test_builder_from_yaml_graph_max_gate_attempts_defaults_to_none(tmp_path):
    p = write_yaml(tmp_path, {"name": "g", "tasks": [{"id": "t1", "description": "x"}]})
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.max_gate_attempts is None


def test_builder_from_yaml_reads_graph_level_max_gate_attempts(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "max_gate_attempts": 4,
            "tasks": [{"id": "t1", "description": "x"}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.max_gate_attempts == 4


# ── plain task new fields ─────────────────────────────────────────────────────


def test_builder_from_yaml_plain_task_task_params(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [
                {
                    "id": "t1",
                    "description": "x",
                    "task_params": {"coverage_threshold": 95},
                }
            ],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["t1"].task_params == {"coverage_threshold": 95}


def test_builder_from_yaml_plain_task_task_params_defaults_to_empty(tmp_path):
    p = write_yaml(tmp_path, {"name": "g", "tasks": [{"id": "t1", "description": "x"}]})
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["t1"].task_params == {}


def test_builder_from_yaml_plain_task_review_model(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [
                {"id": "t1", "description": "x", "review_model": "claude-sonnet-4-6"}
            ],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["t1"].review_model == "claude-sonnet-4-6"


def test_builder_from_yaml_plain_task_review_model_defaults_to_none(tmp_path):
    p = write_yaml(tmp_path, {"name": "g", "tasks": [{"id": "t1", "description": "x"}]})
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["t1"].review_model is None


def test_builder_from_yaml_plain_task_max_gate_attempts(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [{"id": "t1", "description": "x", "max_gate_attempts": 2}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["t1"].max_gate_attempts == 2


def test_builder_from_yaml_plain_task_max_gate_attempts_defaults_to_none(tmp_path):
    p = write_yaml(tmp_path, {"name": "g", "tasks": [{"id": "t1", "description": "x"}]})
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["t1"].max_gate_attempts is None


def test_builder_from_yaml_plain_task_review_on_attempt(tmp_path):
    p = write_yaml(
        tmp_path,
        {
            "name": "g",
            "tasks": [{"id": "t1", "description": "x", "review_on_attempt": 2}],
        },
    )
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["t1"].review_on_attempt == 2


def test_builder_from_yaml_plain_task_review_on_attempt_defaults_to_one(tmp_path):
    p = write_yaml(tmp_path, {"name": "g", "tasks": [{"id": "t1", "description": "x"}]})
    graph = AgentTaskGraphBuilder.from_yaml(p, tmp_path)
    assert graph.tasks["t1"].review_on_attempt == 1


# ── write_context (task_launcher) ─────────────────────────────────────────────


def test_write_context_creates_file(tmp_path):
    from agentrelaysmall.task_launcher import write_context

    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "t1"
    signal_dir.mkdir(parents=True)
    write_context(signal_dir, "# Context\nsome info")
    assert (signal_dir / "context.md").read_text() == "# Context\nsome info"
