"""Tests for task_graph_builder: YAML schema parsing and TaskGraph construction."""

from pathlib import Path

import pytest

from agentrelay.sandbox import ContainerRuntime, SandboxType, TokenTier
from agentrelay.task import (
    AdrVerbosity,
    AgentFramework,
    AgentRole,
    InputFrom,
    TaggedPath,
)
from agentrelay.task_graph.builder import TaskGraphBuilder


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
    assert top.dependencies == ("base", "mid")


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

    assert task.tagged_paths == (
        TaggedPath(path=Path("src/app.py"), category="src"),
        TaggedPath(path=Path("test/test_app.py"), category="test"),
        TaggedPath(path=Path("docs/spec.md"), category="spec"),
    )

    assert task.primary_agent.framework == AgentFramework.CLAUDE_CODE
    assert task.primary_agent.model == "claude-opus-4-6"
    assert task.primary_agent.adr_verbosity == AdrVerbosity.DETAILED
    assert task.primary_agent.environment.session == "proj"

    assert task.review is not None
    assert task.review.agent.framework == AgentFramework.CLAUDE_CODE
    assert task.review.agent.model == "claude-haiku-4-5-20251001"
    assert task.review.agent.adr_verbosity == AdrVerbosity.STANDARD
    assert task.review.agent.environment.session == "reviewers"
    assert task.review.review_on_attempt == 2


def test_from_dict_parses_tagged_paths_list() -> None:
    """tagged_paths list-of-dicts format is parsed to TaggedPath tuples."""
    data = {
        "name": "tagged",
        "tasks": [
            {
                "id": "t1",
                "tagged_paths": [
                    {"path": "src/app.py", "category": "src"},
                    {"path": "test/test_app.py", "category": "test"},
                    {"path": "docs/spec.md", "category": "spec"},
                ],
            }
        ],
    }
    graph = TaskGraphBuilder.from_dict(data)
    task = graph.task("t1")
    assert task.tagged_paths == (
        TaggedPath(path=Path("src/app.py"), category="src"),
        TaggedPath(path=Path("test/test_app.py"), category="test"),
        TaggedPath(path=Path("docs/spec.md"), category="spec"),
    )


def test_from_dict_tagged_paths_empty_list() -> None:
    """tagged_paths as an empty list produces an empty tuple."""
    data = {
        "name": "tagged-empty",
        "tasks": [{"id": "t1", "tagged_paths": []}],
    }
    graph = TaskGraphBuilder.from_dict(data)
    assert graph.task("t1").tagged_paths == ()


def test_from_dict_tagged_paths_custom_category() -> None:
    """tagged_paths supports arbitrary category strings."""
    data = {
        "name": "tagged-custom",
        "tasks": [
            {
                "id": "t1",
                "tagged_paths": [
                    {"path": "stubs/queue.py", "category": "stubs"},
                ],
            }
        ],
    }
    graph = TaskGraphBuilder.from_dict(data)
    assert graph.task("t1").tagged_paths == (
        TaggedPath(path=Path("stubs/queue.py"), category="stubs"),
    )


def test_from_dict_paths_and_tagged_paths_mutually_exclusive() -> None:
    """Specifying both 'paths' and 'tagged_paths' raises ValueError."""
    data = {
        "name": "conflict",
        "tasks": [
            {
                "id": "t1",
                "paths": {"src": ["a.py"]},
                "tagged_paths": [{"path": "a.py", "category": "src"}],
            }
        ],
    }
    with pytest.raises(ValueError, match="mutually exclusive"):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_tagged_paths_rejects_missing_fields() -> None:
    """tagged_paths entries must have both 'path' and 'category'."""
    data = {
        "name": "missing",
        "tasks": [
            {
                "id": "t1",
                "tagged_paths": [{"path": "a.py"}],
            }
        ],
    }
    with pytest.raises(ValueError, match="category.*required"):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_tagged_paths_rejects_unknown_keys() -> None:
    """tagged_paths entries reject unknown keys."""
    data = {
        "name": "unknown",
        "tasks": [
            {
                "id": "t1",
                "tagged_paths": [{"path": "a.py", "category": "src", "extra": True}],
            }
        ],
    }
    with pytest.raises(ValueError, match="unknown key"):
        TaskGraphBuilder.from_dict(data)


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


def test_from_yaml_reads_workstreams_and_task_mapping(tmp_path: Path) -> None:
    yaml_path = tmp_path / "graph_workstreams.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                "name: from-yaml-workstreams",
                "max_workstream_depth: 2",
                "workstreams:",
                "  - id: feature_a",
                "  - id: feature_b",
                "    parent_workstream_id: feature_a",
                "tasks:",
                "  - id: task_a",
                "    workstream_id: feature_a",
                "  - id: task_b",
                "    dependencies: [task_a]",
                "    workstream_id: feature_b",
            ]
        )
    )
    graph = TaskGraphBuilder.from_yaml(yaml_path)

    assert graph.name == "from-yaml-workstreams"
    assert graph.max_workstream_depth == 2
    assert graph.task("task_a").workstream_id == "feature_a"
    assert graph.task("task_b").workstream_id == "feature_b"
    assert graph.child_workstream_ids("feature_a") == ("feature_b",)


def test_from_dict_parses_workstreams_and_task_mapping() -> None:
    data = {
        "name": "workstreams",
        "workstreams": [
            {"id": "feature_a", "base_branch": "main", "merge_target_branch": "main"},
            {
                "id": "feature_b",
                "parent_workstream_id": "feature_a",
                "base_branch": "feature_a",
                "merge_target_branch": "feature_a",
            },
        ],
        "tasks": [
            {"id": "a", "workstream_id": "feature_a"},
            {"id": "b", "dependencies": ["a"], "workstream_id": "feature_b"},
        ],
    }

    graph = TaskGraphBuilder.from_dict(data)

    assert graph.workstream_ids() == ("feature_a", "feature_b")
    assert graph.task("a").workstream_id == "feature_a"
    assert graph.task("b").workstream_id == "feature_b"
    assert graph.tasks_in_workstream("feature_a") == ("a",)
    assert graph.tasks_in_workstream("feature_b") == ("b",)
    feature_b = graph.workstream("feature_b")
    assert feature_b.parent_workstream_id == "feature_a"
    assert feature_b.base_branch == "feature_a"
    assert feature_b.merge_target_branch == "feature_a"


def test_from_dict_task_workstream_id_defaults_to_default() -> None:
    graph = TaskGraphBuilder.from_dict(_minimal_graph_dict())
    assert graph.task("task_a").workstream_id == "default"


def test_from_dict_unknown_task_workstream_id_raises() -> None:
    data = {
        "name": "g",
        "workstreams": [{"id": "feature_a"}],
        "tasks": [{"id": "t1", "workstream_id": "missing"}],
    }
    with pytest.raises(
        ValueError,
        match="Unknown workstream id\\(s\\) referenced by tasks: missing",
    ):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_workstreams_must_be_non_empty_list() -> None:
    with pytest.raises(ValueError, match="graph.workstreams"):
        TaskGraphBuilder.from_dict(
            {"name": "g", "tasks": [{"id": "t1"}], "workstreams": {}}
        )
    with pytest.raises(ValueError, match="graph.workstreams"):
        TaskGraphBuilder.from_dict(
            {"name": "g", "tasks": [{"id": "t1"}], "workstreams": []}
        )


def test_from_dict_rejects_unknown_workstream_keys() -> None:
    data = {
        "name": "g",
        "workstreams": [{"id": "w1", "mystery": 1}],
        "tasks": [{"id": "t1", "workstream_id": "w1"}],
    }
    with pytest.raises(ValueError, match="contains unknown key\\(s\\): mystery"):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_duplicate_workstream_id_raises() -> None:
    data = {
        "name": "g",
        "workstreams": [{"id": "dup"}, {"id": "dup"}],
        "tasks": [{"id": "t1", "workstream_id": "dup"}],
    }
    with pytest.raises(ValueError, match="duplicate workstream id 'dup'"):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_max_workstream_depth_can_override_default() -> None:
    data = {
        "name": "g",
        "max_workstream_depth": 2,
        "workstreams": [
            {"id": "a"},
            {"id": "b", "parent_workstream_id": "a"},
            {"id": "c", "parent_workstream_id": "b"},
        ],
        "tasks": [{"id": "t1", "workstream_id": "c"}],
    }
    graph = TaskGraphBuilder.from_dict(data)
    assert graph.max_workstream_depth == 2


def test_from_dict_workstream_auto_merge_true() -> None:
    data = {
        "name": "g",
        "workstreams": [{"id": "ws", "auto_merge": True}],
        "tasks": [{"id": "t1", "workstream_id": "ws"}],
    }
    graph = TaskGraphBuilder.from_dict(data)
    assert graph.workstream("ws").auto_merge is True


def test_from_dict_workstream_auto_merge_false() -> None:
    data = {
        "name": "g",
        "workstreams": [{"id": "ws", "auto_merge": False}],
        "tasks": [{"id": "t1", "workstream_id": "ws"}],
    }
    graph = TaskGraphBuilder.from_dict(data)
    assert graph.workstream("ws").auto_merge is False


def test_from_dict_workstream_auto_merge_defaults_to_false() -> None:
    data = {
        "name": "g",
        "workstreams": [{"id": "ws"}],
        "tasks": [{"id": "t1", "workstream_id": "ws"}],
    }
    graph = TaskGraphBuilder.from_dict(data)
    assert graph.workstream("ws").auto_merge is False


def test_from_dict_workstream_auto_merge_non_bool_raises() -> None:
    data = {
        "name": "g",
        "workstreams": [{"id": "ws", "auto_merge": "yes"}],
        "tasks": [{"id": "t1", "workstream_id": "ws"}],
    }
    with pytest.raises(ValueError, match="auto_merge.*must be a boolean"):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_invalid_max_workstream_depth_raises() -> None:
    data = {
        "name": "g",
        "max_workstream_depth": 0,
        "tasks": [{"id": "t1"}],
    }
    with pytest.raises(ValueError, match="graph.max_workstream_depth"):
        TaskGraphBuilder.from_dict(data)


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


# ── Isolation config parsing + four-level inheritance ──


def test_from_dict_no_isolation_leaves_all_none() -> None:
    """Graphs without isolation config produce None on all isolation fields."""
    graph = TaskGraphBuilder.from_dict(_minimal_graph_dict())
    task = graph.task("task_a")
    assert task.isolation is None
    assert task.primary_agent.isolation is None


def test_from_dict_graph_isolation_inherited_by_agents() -> None:
    """Graph-level isolation is inherited by all task agents."""
    data = {
        "name": "g",
        "isolation": {"sandbox": "oci", "token_tier": "elevated"},
        "tasks": [{"id": "t1"}],
    }
    graph = TaskGraphBuilder.from_dict(data)
    task = graph.task("t1")

    assert task.isolation is not None
    assert task.isolation.sandbox_type == SandboxType.OCI
    assert task.isolation.token_tier == TokenTier.ELEVATED

    assert task.primary_agent.isolation is not None
    assert task.primary_agent.isolation.sandbox_type == SandboxType.OCI
    assert task.primary_agent.isolation.token_tier == TokenTier.ELEVATED


def test_from_dict_graph_isolation_inherited_by_workstream() -> None:
    """Graph-level isolation is inherited by workstreams."""
    data = {
        "name": "g",
        "isolation": {"sandbox": "oci"},
        "workstreams": [{"id": "ws"}],
        "tasks": [{"id": "t1", "workstream_id": "ws"}],
    }
    graph = TaskGraphBuilder.from_dict(data)
    ws = graph.workstream("ws")

    assert ws.isolation is not None
    assert ws.isolation.sandbox_type == SandboxType.OCI
    assert ws.isolation.token_tier == TokenTier.STANDARD  # default


def test_from_dict_workstream_isolation_overrides_graph() -> None:
    """Workstream-level isolation overrides graph for set fields."""
    data = {
        "name": "g",
        "isolation": {"sandbox": "oci", "token_tier": "standard"},
        "workstreams": [{"id": "ws", "isolation": {"token_tier": "elevated"}}],
        "tasks": [{"id": "t1", "workstream_id": "ws"}],
    }
    graph = TaskGraphBuilder.from_dict(data)
    task = graph.task("t1")

    # Workstream overrides token_tier, inherits sandbox from graph
    assert task.primary_agent.isolation is not None
    assert task.primary_agent.isolation.sandbox_type == SandboxType.OCI
    assert task.primary_agent.isolation.token_tier == TokenTier.ELEVATED


def test_from_dict_task_isolation_overrides_workstream() -> None:
    """Task-level isolation overrides workstream."""
    data = {
        "name": "g",
        "isolation": {"sandbox": "oci"},
        "workstreams": [{"id": "ws", "isolation": {"token_tier": "elevated"}}],
        "tasks": [
            {
                "id": "t1",
                "workstream_id": "ws",
                "isolation": {"token_tier": "read_only"},
            }
        ],
    }
    graph = TaskGraphBuilder.from_dict(data)
    task = graph.task("t1")

    assert task.isolation is not None
    assert task.isolation.sandbox_type == SandboxType.OCI
    assert task.isolation.token_tier == TokenTier.READ_ONLY

    assert task.primary_agent.isolation is not None
    assert task.primary_agent.isolation.token_tier == TokenTier.READ_ONLY


def test_from_dict_agent_isolation_overrides_task() -> None:
    """Agent-level isolation overrides task."""
    data = {
        "name": "g",
        "isolation": {"sandbox": "oci", "token_tier": "standard"},
        "tasks": [
            {
                "id": "t1",
                "isolation": {"token_tier": "read_only"},
                "primary_agent": {
                    "isolation": {"token_tier": "elevated"},
                },
            }
        ],
    }
    graph = TaskGraphBuilder.from_dict(data)
    task = graph.task("t1")

    # Task-level says read_only
    assert task.isolation is not None
    assert task.isolation.token_tier == TokenTier.READ_ONLY

    # Agent-level overrides to elevated
    assert task.primary_agent.isolation is not None
    assert task.primary_agent.isolation.token_tier == TokenTier.ELEVATED
    # Sandbox inherited from graph
    assert task.primary_agent.isolation.sandbox_type == SandboxType.OCI


def test_from_dict_four_level_chain_selective_overrides() -> None:
    """Full four-level chain with selective field overrides at each level."""
    data = {
        "name": "g",
        "isolation": {"sandbox": "oci"},
        "workstreams": [{"id": "ws", "isolation": {"token_tier": "elevated"}}],
        "tasks": [
            {
                "id": "t1",
                "workstream_id": "ws",
                "isolation": {"image": "custom:latest"},
                "primary_agent": {
                    "isolation": {"runtime": "podman"},
                },
            }
        ],
    }
    graph = TaskGraphBuilder.from_dict(data)
    agent_iso = graph.task("t1").primary_agent.isolation

    assert agent_iso is not None
    assert agent_iso.sandbox_type == SandboxType.OCI  # from graph
    assert agent_iso.token_tier == TokenTier.ELEVATED  # from workstream
    assert agent_iso.image == "custom:latest"  # from task
    assert agent_iso.runtime == ContainerRuntime.PODMAN  # from agent


def test_from_dict_partial_isolation_inherits_defaults() -> None:
    """Partial isolation fills unset fields with defaults."""
    data = {
        "name": "g",
        "isolation": {"sandbox": "oci"},
        "tasks": [{"id": "t1"}],
    }
    graph = TaskGraphBuilder.from_dict(data)
    iso = graph.task("t1").primary_agent.isolation

    assert iso is not None
    assert iso.sandbox_type == SandboxType.OCI
    assert iso.token_tier == TokenTier.STANDARD  # default
    assert iso.image is None  # default
    assert iso.runtime is None  # default


def test_from_dict_review_agent_gets_own_isolation_override() -> None:
    """Review agent can have its own isolation override."""
    data = {
        "name": "g",
        "isolation": {"sandbox": "oci", "token_tier": "standard"},
        "tasks": [
            {
                "id": "t1",
                "review": {
                    "agent": {
                        "isolation": {"token_tier": "read_only"},
                    },
                },
            }
        ],
    }
    graph = TaskGraphBuilder.from_dict(data)
    task = graph.task("t1")

    # Primary agent inherits graph
    assert task.primary_agent.isolation is not None
    assert task.primary_agent.isolation.token_tier == TokenTier.STANDARD

    # Review agent overrides token_tier
    assert task.review is not None
    assert task.review.agent.isolation is not None
    assert task.review.agent.isolation.token_tier == TokenTier.READ_ONLY
    assert task.review.agent.isolation.sandbox_type == SandboxType.OCI


def test_from_dict_review_agent_inherits_task_chain_when_no_override() -> None:
    """Review agent inherits the task chain when it has no isolation override."""
    data = {
        "name": "g",
        "isolation": {"sandbox": "oci", "token_tier": "elevated"},
        "tasks": [
            {
                "id": "t1",
                "review": {"agent": {}},
            }
        ],
    }
    graph = TaskGraphBuilder.from_dict(data)
    task = graph.task("t1")

    assert task.review is not None
    assert task.review.agent.isolation is not None
    assert task.review.agent.isolation.sandbox_type == SandboxType.OCI
    assert task.review.agent.isolation.token_tier == TokenTier.ELEVATED


def test_from_dict_isolation_unknown_keys_rejected() -> None:
    """Unknown keys inside isolation mapping are rejected."""
    data = {
        "name": "g",
        "isolation": {"sandbox": "none", "mystery": True},
        "tasks": [{"id": "t1"}],
    }
    with pytest.raises(ValueError, match="contains unknown key\\(s\\): mystery"):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_invalid_sandbox_type_rejected() -> None:
    """Invalid sandbox type string is rejected."""
    data = {
        "name": "g",
        "isolation": {"sandbox": "magic_box"},
        "tasks": [{"id": "t1"}],
    }
    with pytest.raises(ValueError, match="invalid sandbox type"):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_invalid_token_tier_rejected() -> None:
    """Invalid token tier string is rejected."""
    data = {
        "name": "g",
        "isolation": {"token_tier": "super_admin"},
        "tasks": [{"id": "t1"}],
    }
    with pytest.raises(ValueError, match="invalid token tier"):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_sandbox_type_accepts_enum_name() -> None:
    """Sandbox type can be specified via enum name (OCI)."""
    data = {
        "name": "g",
        "isolation": {"sandbox": "OCI"},
        "tasks": [{"id": "t1"}],
    }
    graph = TaskGraphBuilder.from_dict(data)
    assert graph.task("t1").isolation is not None
    assert graph.task("t1").isolation.sandbox_type == SandboxType.OCI


def test_from_dict_token_tier_accepts_enum_name() -> None:
    """Token tier can be specified via enum name (READ_ONLY)."""
    data = {
        "name": "g",
        "isolation": {"token_tier": "READ_ONLY"},
        "tasks": [{"id": "t1"}],
    }
    graph = TaskGraphBuilder.from_dict(data)
    assert graph.task("t1").isolation is not None
    assert graph.task("t1").isolation.token_tier == TokenTier.READ_ONLY


def test_from_dict_isolation_with_image_and_runtime() -> None:
    """Isolation config can include image and runtime fields."""
    data = {
        "name": "g",
        "isolation": {
            "sandbox": "oci",
            "image": "agentrelay-agent:v1",
            "runtime": "podman",
        },
        "tasks": [{"id": "t1"}],
    }
    graph = TaskGraphBuilder.from_dict(data)
    iso = graph.task("t1").primary_agent.isolation
    assert iso is not None
    assert iso.image == "agentrelay-agent:v1"
    assert iso.runtime == ContainerRuntime.PODMAN


def test_from_dict_invalid_runtime_rejected() -> None:
    """Invalid container runtime string is rejected."""
    data = {
        "name": "g",
        "isolation": {"runtime": "lxc"},
        "tasks": [{"id": "t1"}],
    }
    with pytest.raises(ValueError, match="invalid container runtime"):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_runtime_accepts_enum_name() -> None:
    """Container runtime can be specified via enum name (PODMAN)."""
    data = {
        "name": "g",
        "isolation": {"runtime": "PODMAN"},
        "tasks": [{"id": "t1"}],
    }
    graph = TaskGraphBuilder.from_dict(data)
    assert graph.task("t1").isolation is not None
    assert graph.task("t1").isolation.runtime == ContainerRuntime.PODMAN


def test_from_dict_no_isolation_with_workstreams() -> None:
    """Graphs with workstreams but no isolation produce None isolation."""
    data = {
        "name": "g",
        "workstreams": [{"id": "ws"}],
        "tasks": [{"id": "t1", "workstream_id": "ws"}],
    }
    graph = TaskGraphBuilder.from_dict(data)
    assert graph.workstream("ws").isolation is None
    assert graph.task("t1").isolation is None
    assert graph.task("t1").primary_agent.isolation is None


# ── inputs_from tests ──


def test_from_dict_inputs_from_single_mapping() -> None:
    """Single inputs_from dict is parsed correctly."""
    data = {
        "name": "g",
        "tasks": [
            {"id": "upstream"},
            {
                "id": "downstream",
                "dependencies": ["upstream"],
                "inputs_from": {"task": "upstream", "category": "stubs"},
            },
        ],
    }
    graph = TaskGraphBuilder.from_dict(data)
    task = graph.task("downstream")
    assert task.inputs_from == (InputFrom(task="upstream", category="stubs"),)


def test_from_dict_inputs_from_list_of_mappings() -> None:
    """List of inputs_from dicts is parsed in order."""
    data = {
        "name": "g",
        "tasks": [
            {"id": "spec"},
            {"id": "test", "dependencies": ["spec"]},
            {
                "id": "impl",
                "dependencies": ["spec", "test"],
                "inputs_from": [
                    {"task": "spec", "category": "stubs"},
                    {"task": "test", "category": "tests"},
                ],
            },
        ],
    }
    graph = TaskGraphBuilder.from_dict(data)
    task = graph.task("impl")
    assert task.inputs_from == (
        InputFrom(task="spec", category="stubs"),
        InputFrom(task="test", category="tests"),
    )


def test_from_dict_inputs_from_without_category() -> None:
    """Category is optional; omitting it produces None."""
    data = {
        "name": "g",
        "tasks": [
            {"id": "upstream"},
            {
                "id": "downstream",
                "dependencies": ["upstream"],
                "inputs_from": {"task": "upstream"},
            },
        ],
    }
    graph = TaskGraphBuilder.from_dict(data)
    assert graph.task("downstream").inputs_from == (
        InputFrom(task="upstream", category=None),
    )


def test_from_dict_inputs_from_absent_defaults_to_empty() -> None:
    """Tasks without inputs_from have an empty tuple."""
    data = _minimal_graph_dict()
    graph = TaskGraphBuilder.from_dict(data)
    assert graph.task("task_a").inputs_from == ()


def test_from_dict_inputs_from_unknown_task_raises() -> None:
    """Referencing a task ID that doesn't exist raises ValueError."""
    data = {
        "name": "g",
        "tasks": [
            {"id": "a"},
            {
                "id": "b",
                "dependencies": ["a"],
                "inputs_from": {"task": "nonexistent"},
            },
        ],
    }
    with pytest.raises(ValueError, match="unknown task id 'nonexistent'"):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_inputs_from_not_a_dependency_raises() -> None:
    """Referencing a task that exists but is not a dependency raises ValueError."""
    data = {
        "name": "g",
        "tasks": [
            {"id": "a"},
            {"id": "b"},
            {
                "id": "c",
                "dependencies": ["b"],
                "inputs_from": {"task": "a"},
            },
        ],
    }
    with pytest.raises(ValueError, match="not a dependency.*of task 'c'"):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_inputs_from_transitive_dependency_ok() -> None:
    """inputs_from referencing a transitive dependency is allowed."""
    data = {
        "name": "g",
        "tasks": [
            {"id": "a"},
            {"id": "b", "dependencies": ["a"]},
            {
                "id": "c",
                "dependencies": ["b"],
                "inputs_from": {"task": "a", "category": "stubs"},
            },
        ],
    }
    graph = TaskGraphBuilder.from_dict(data)
    assert graph.task("c").inputs_from == (InputFrom(task="a", category="stubs"),)


def test_from_dict_inputs_from_rejects_unknown_keys() -> None:
    """Extra keys in inputs_from mapping are rejected."""
    data = {
        "name": "g",
        "tasks": [
            {"id": "a"},
            {
                "id": "b",
                "dependencies": ["a"],
                "inputs_from": {"task": "a", "category": "stubs", "extra": True},
            },
        ],
    }
    with pytest.raises(ValueError, match="unknown key.*extra"):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_inputs_from_invalid_type_raises() -> None:
    """String instead of mapping/list raises ValueError."""
    data = {
        "name": "g",
        "tasks": [
            {"id": "a"},
            {
                "id": "b",
                "dependencies": ["a"],
                "inputs_from": "upstream",
            },
        ],
    }
    with pytest.raises(ValueError, match="must be a mapping or list"):
        TaskGraphBuilder.from_dict(data)


def test_from_dict_inputs_from_missing_task_key_raises() -> None:
    """inputs_from mapping without 'task' key raises ValueError."""
    data = {
        "name": "g",
        "tasks": [
            {"id": "a"},
            {
                "id": "b",
                "dependencies": ["a"],
                "inputs_from": {"category": "stubs"},
            },
        ],
    }
    with pytest.raises(ValueError, match="task.*is required"):
        TaskGraphBuilder.from_dict(data)
