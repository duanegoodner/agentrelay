"""Tests for task_graph_builder: YAML schema parsing and TaskGraph construction."""

from pathlib import Path

import pytest

from agentrelay.task_graph_builder import TaskGraphBuilder
from agentrelay.task import (
    AgentFramework,
    AgentRole,
    AgentVerbosity,
)


def _minimal_graph_dict() -> dict:
    return {
        "name": "demo",
        "tasks": [
            {
                "id": "task_a",
                "description": "first task",
            }
        ],
    }


def test_from_dict_minimal_graph() -> None:
    graph = TaskGraphBuilder.from_dict(_minimal_graph_dict())

    assert graph.name == "demo"
    assert graph.task_ids() == ("task_a",)
    task = graph.task("task_a")
    assert task.role == AgentRole.GENERIC
    assert task.description == "first task"
    assert task.dependencies == ()


def test_from_dict_dependencies_are_wired_in_order() -> None:
    data = {
        "name": "demo",
        "tasks": [
            {"id": "base"},
            {"id": "mid", "dependencies": ["base"]},
            {"id": "top", "dependencies": ["base", "mid"]},
        ],
    }
    graph = TaskGraphBuilder.from_dict(data)

    assert graph.task_ids() == ("base", "mid", "top")
    top = graph.task("top")
    assert tuple(dep.id for dep in top.dependencies) == ("base", "mid")


def test_from_dict_role_accepts_value_or_enum_name() -> None:
    data = {
        "name": "roles",
        "tasks": [
            {"id": "a", "role": "implementer"},
            {"id": "b", "role": "TEST_WRITER"},
        ],
    }
    graph = TaskGraphBuilder.from_dict(data)

    assert graph.task("a").role == AgentRole.IMPLEMENTER
    assert graph.task("b").role == AgentRole.TEST_WRITER


def test_from_dict_parses_paths_agent_and_review_configs() -> None:
    data = {
        "name": "configs",
        "tasks": [
            {
                "id": "t1",
                "paths": {
                    "src": ["src/app.py"],
                    "test": ["test/test_app.py"],
                    "spec": "docs/spec.md",
                },
                "primary_agent": {
                    "framework": "claude_code",
                    "model": "claude-opus-4-6",
                    "adr_verbosity": "detailed",
                    "environment": {
                        "type": "tmux",
                        "session": "proj",
                    },
                },
                "review": {
                    "agent": {
                        "framework": "CLAUDE_CODE",
                        "model": "claude-haiku-4-5-20251001",
                        "adr_verbosity": "standard",
                        "environment": {"session": "reviewers"},
                    },
                    "review_on_attempt": 2,
                },
            }
        ],
    }

    graph = TaskGraphBuilder.from_dict(data)
    task = graph.task("t1")

    assert task.paths.src == ("src/app.py",)
    assert task.paths.test == ("test/test_app.py",)
    assert task.paths.spec == "docs/spec.md"

    assert task.primary_agent.framework == AgentFramework.CLAUDE_CODE
    assert task.primary_agent.model == "claude-opus-4-6"
    assert task.primary_agent.adr_verbosity == AgentVerbosity.DETAILED
    assert task.primary_agent.environment.session == "proj"

    assert task.review is not None
    assert task.review.agent.framework == AgentFramework.CLAUDE_CODE
    assert task.review.agent.model == "claude-haiku-4-5-20251001"
    assert task.review.agent.adr_verbosity == AgentVerbosity.STANDARD
    assert task.review.agent.environment.session == "reviewers"
    assert task.review.review_on_attempt == 2


def test_from_yaml_reads_file(tmp_path: Path) -> None:
    yaml_path = tmp_path / "graph.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                "name: from-yaml",
                "tasks:",
                "  - id: task_a",
                "  - id: task_b",
                "    dependencies: [task_a]",
            ]
        )
    )
    graph = TaskGraphBuilder.from_yaml(yaml_path)

    assert graph.name == "from-yaml"
    assert graph.task_ids() == ("task_a", "task_b")
    assert graph.dependency_ids("task_b") == ("task_a",)


def test_from_dict_missing_name_raises() -> None:
    with pytest.raises(ValueError, match="graph.name"):
        TaskGraphBuilder.from_dict({"tasks": [{"id": "t1"}]})


def test_from_dict_missing_tasks_raises() -> None:
    with pytest.raises(ValueError, match="graph.tasks"):
        TaskGraphBuilder.from_dict({"name": "g"})


def test_from_dict_tasks_must_be_non_empty_list() -> None:
    with pytest.raises(ValueError, match="tasks"):
        TaskGraphBuilder.from_dict({"name": "g", "tasks": []})


def test_from_dict_duplicate_task_id_raises() -> None:
    data = {
        "name": "g",
        "tasks": [{"id": "same"}, {"id": "same"}],
    }
    with pytest.raises(ValueError, match="duplicate task id 'same'"):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_invalid_role_raises() -> None:
    data = {
        "name": "g",
        "tasks": [{"id": "t1", "role": "not_a_real_role"}],
    }
    with pytest.raises(ValueError, match="invalid role"):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_wrong_dependencies_type_raises() -> None:
    data = {
        "name": "g",
        "tasks": [{"id": "t1", "dependencies": "t0"}],
    }
    with pytest.raises(ValueError, match="dependencies"):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_unknown_dependency_raises() -> None:
    data = {
        "name": "g",
        "tasks": [{"id": "t1", "dependencies": ["missing"]}],
    }
    with pytest.raises(ValueError, match="unknown dependency id 'missing'"):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_cycle_raises() -> None:
    data = {
        "name": "g",
        "tasks": [
            {"id": "a", "dependencies": ["b"]},
            {"id": "b", "dependencies": ["a"]},
        ],
    }
    with pytest.raises(ValueError, match="dependency cycle"):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_rejects_unknown_task_keys() -> None:
    data = {
        "name": "g",
        "tasks": [{"id": "t1", "mystery": 123}],
    }
    with pytest.raises(ValueError, match="contains unknown key\\(s\\): mystery"):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_rejects_unknown_paths_keys() -> None:
    data = {
        "name": "g",
        "tasks": [{"id": "t1", "paths": {"src": [], "other": []}}],
    }
    with pytest.raises(ValueError, match="paths"):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_rejects_non_positive_integers() -> None:
    data = {
        "name": "g",
        "tasks": [{"id": "t1", "max_gate_attempts": 0}],
    }
    with pytest.raises(ValueError, match="max_gate_attempts"):
        TaskGraphBuilder.from_dict(data)


def test_from_yaml_invalid_yaml_raises(tmp_path: Path) -> None:
    yaml_path = tmp_path / "broken.yaml"
    yaml_path.write_text("name: [unterminated")
    with pytest.raises(ValueError, match="Invalid YAML"):
        TaskGraphBuilder.from_yaml(yaml_path)
