"""Tests for agentrelay.v2.task: Task specs, config, and enums."""

import pytest

from agentrelay.environments import TmuxEnvironment
from agentrelay.sandbox import IsolationConfig, SandboxType, TokenTier
from agentrelay.task import (
    AdrVerbosity,
    AgentConfig,
    AgentFramework,
    AgentRole,
    ReviewConfig,
    TaggedPath,
    Task,
)
from agentrelay.task_runtime import TaskStatus

# ── Tests for enums ──


class TestAdrVerbosity:
    """Tests for AdrVerbosity enum."""

    def test_all_values_exist(self) -> None:
        """All expected verbosity levels are defined."""
        assert AdrVerbosity.NONE.value == "none"
        assert AdrVerbosity.STANDARD.value == "standard"
        assert AdrVerbosity.DETAILED.value == "detailed"
        assert AdrVerbosity.EDUCATIONAL.value == "educational"

    def test_is_string_enum(self) -> None:
        """AdrVerbosity values are string-comparable."""
        assert AdrVerbosity.STANDARD == "standard"
        assert AdrVerbosity.NONE != "standard"

    def test_all_values_are_strings(self) -> None:
        """All verbosity values are accessible as strings."""
        for v in AdrVerbosity:
            assert isinstance(v.value, str)


class TestAgentFramework:
    """Tests for AgentFramework enum."""

    def test_claude_code_exists(self) -> None:
        """CLAUDE_CODE framework is defined."""
        assert AgentFramework.CLAUDE_CODE.value == "claude_code"

    def test_is_string_enum(self) -> None:
        """AgentFramework values are string-comparable."""
        assert AgentFramework.CLAUDE_CODE == "claude_code"

    def test_extensible_comment_present(self) -> None:
        """Comments indicate future framework extensions."""
        # Just verifying the enum exists and is usable
        assert AgentFramework.CLAUDE_CODE is not None


class TestAgentRole:
    """Tests for AgentRole enum."""

    def test_all_roles_exist(self) -> None:
        """All expected roles are defined."""
        assert AgentRole.SPEC_WRITER.value == "spec_writer"
        assert AgentRole.TEST_WRITER.value == "test_writer"
        assert AgentRole.TEST_REVIEWER.value == "test_reviewer"
        assert AgentRole.IMPLEMENTER.value == "implementer"
        assert AgentRole.GENERIC.value == "generic"

    def test_is_string_enum(self) -> None:
        """AgentRole values are string-comparable."""
        assert AgentRole.SPEC_WRITER == "spec_writer"
        assert AgentRole.IMPLEMENTER != "spec_writer"

    def test_no_merger_role(self) -> None:
        """MERGER is not a task role (handled at graph level)."""
        all_roles = {r.value for r in AgentRole}
        assert "merger" not in all_roles

    def test_all_values_are_strings(self) -> None:
        """All role values are strings."""
        for role in AgentRole:
            assert isinstance(role.value, str)


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_all_statuses_exist(self) -> None:
        """All expected statuses are defined."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.PR_CREATED.value == "pr_created"
        assert TaskStatus.PR_MERGED.value == "pr_merged"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"

    def test_is_string_enum(self) -> None:
        """TaskStatus values are string-comparable."""
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.RUNNING != "pending"

    def test_status_progression(self) -> None:
        """Statuses represent a logical execution flow."""
        # PENDING -> RUNNING -> PR_CREATED -> PR_MERGED (PR-backed)
        # PENDING -> RUNNING -> COMPLETED (PR-less)
        # or PENDING -> RUNNING -> FAILED
        statuses = list(TaskStatus)
        assert len(statuses) == 6


# ── Tests for AgentEnvironment ──


class TestAgentEnvironment:
    """Tests for AgentEnvironment type alias."""

    def test_environment_type_is_tmux(self) -> None:
        """AgentEnvironment type alias currently represents TmuxEnvironment."""
        # For now, AgentEnvironment only includes TmuxEnvironment.
        # When more environments are added, this will become a union.
        env = TmuxEnvironment()
        assert isinstance(env, TmuxEnvironment)


class TestTmuxEnvironment:
    """Tests for TmuxEnvironment."""

    def test_default_session(self) -> None:
        """TmuxEnvironment defaults session to empty string."""
        env = TmuxEnvironment()
        assert env.session == ""

    def test_custom_session(self) -> None:
        """TmuxEnvironment can specify custom session."""
        env = TmuxEnvironment(session="custom_session")
        assert env.session == "custom_session"

    def test_is_frozen(self) -> None:
        """TmuxEnvironment is immutable."""
        env = TmuxEnvironment(session="test")
        with pytest.raises(AttributeError):
            env.session = "new_session"  # type: ignore


# ── Tests for TaggedPath ──


class TestTaggedPath:
    """Tests for TaggedPath configuration."""

    def test_construction(self) -> None:
        """TaggedPath stores path and category."""
        from pathlib import Path

        tp = TaggedPath(path=Path("src/main.py"), category="src")
        assert tp.path == Path("src/main.py")
        assert tp.category == "src"

    def test_is_frozen(self) -> None:
        """TaggedPath is immutable."""
        from pathlib import Path

        tp = TaggedPath(path=Path("src/main.py"), category="src")
        with pytest.raises(AttributeError):
            tp.path = Path("other.py")  # type: ignore

    def test_is_hashable(self) -> None:
        """TaggedPath can be hashed (used as dict keys)."""
        from pathlib import Path

        tp1 = TaggedPath(path=Path("src/main.py"), category="src")
        tp2 = TaggedPath(path=Path("src/main.py"), category="src")
        assert hash(tp1) == hash(tp2)

    def test_equality(self) -> None:
        """TaggedPaths with same content are equal."""
        from pathlib import Path

        tp1 = TaggedPath(path=Path("src/main.py"), category="src")
        tp2 = TaggedPath(path=Path("src/main.py"), category="src")
        assert tp1 == tp2

    def test_different_category_not_equal(self) -> None:
        """TaggedPaths with different categories are not equal."""
        from pathlib import Path

        tp1 = TaggedPath(path=Path("src/main.py"), category="src")
        tp2 = TaggedPath(path=Path("src/main.py"), category="test")
        assert tp1 != tp2


# ── Tests for AgentConfig ──


class TestAgentConfig:
    """Tests for AgentConfig."""

    def test_default_framework(self) -> None:
        """AgentConfig defaults to CLAUDE_CODE framework."""
        config = AgentConfig()
        assert config.framework == AgentFramework.CLAUDE_CODE

    def test_default_model_is_none(self) -> None:
        """AgentConfig defaults to no specific model (use framework default)."""
        config = AgentConfig()
        assert config.model is None

    def test_custom_framework(self) -> None:
        """AgentConfig can specify a different framework."""
        config = AgentConfig(framework=AgentFramework.CLAUDE_CODE)
        assert config.framework == AgentFramework.CLAUDE_CODE

    def test_custom_model(self) -> None:
        """AgentConfig can specify a model."""
        config = AgentConfig(model="claude-opus-4-6")
        assert config.model == "claude-opus-4-6"

    def test_full_config(self) -> None:
        """AgentConfig can specify both framework and model."""
        config = AgentConfig(
            framework=AgentFramework.CLAUDE_CODE,
            model="claude-haiku-4-5-20251001",
        )
        assert config.framework == AgentFramework.CLAUDE_CODE
        assert config.model == "claude-haiku-4-5-20251001"

    def test_is_frozen(self) -> None:
        """AgentConfig is immutable."""
        config = AgentConfig(model="claude-opus-4-6")
        with pytest.raises(AttributeError):
            config.model = "claude-haiku-4-5-20251001"  # type: ignore

    def test_is_hashable(self) -> None:
        """AgentConfig can be hashed."""
        config1 = AgentConfig(model="claude-opus-4-6")
        config2 = AgentConfig(model="claude-opus-4-6")
        assert hash(config1) == hash(config2)

    def test_equality(self) -> None:
        """AgentConfigs with same values are equal."""
        config1 = AgentConfig(model="claude-opus-4-6")
        config2 = AgentConfig(model="claude-opus-4-6")
        assert config1 == config2

    def test_default_adr_verbosity(self) -> None:
        """AgentConfig defaults adr_verbosity to NONE."""
        config = AgentConfig()
        assert config.adr_verbosity == AdrVerbosity.NONE

    def test_custom_adr_verbosity(self) -> None:
        """AgentConfig can specify custom adr_verbosity."""
        config_standard = AgentConfig(adr_verbosity=AdrVerbosity.STANDARD)
        assert config_standard.adr_verbosity == AdrVerbosity.STANDARD

        config_detailed = AgentConfig(adr_verbosity=AdrVerbosity.DETAILED)
        assert config_detailed.adr_verbosity == AdrVerbosity.DETAILED

        config_educational = AgentConfig(adr_verbosity=AdrVerbosity.EDUCATIONAL)
        assert config_educational.adr_verbosity == AdrVerbosity.EDUCATIONAL

    def test_default_environment(self) -> None:
        """AgentConfig defaults environment to TmuxEnvironment."""
        config = AgentConfig()
        assert isinstance(config.environment, TmuxEnvironment)
        assert config.environment.session == ""

    def test_custom_environment(self) -> None:
        """AgentConfig can specify custom environment."""
        env = TmuxEnvironment(session="custom")
        config = AgentConfig(environment=env)
        assert config.environment == env
        assert config.environment.session == "custom"

    def test_full_config_with_all_fields(self) -> None:
        """AgentConfig with all fields round-trips correctly."""
        env = TmuxEnvironment(session="test_session")
        config = AgentConfig(
            framework=AgentFramework.CLAUDE_CODE,
            model="claude-opus-4-6",
            adr_verbosity=AdrVerbosity.DETAILED,
            environment=env,
        )
        assert config.framework == AgentFramework.CLAUDE_CODE
        assert config.model == "claude-opus-4-6"
        assert config.adr_verbosity == AdrVerbosity.DETAILED
        assert config.environment == env

    def test_default_isolation_is_none(self) -> None:
        """AgentConfig defaults isolation to None."""
        config = AgentConfig()
        assert config.isolation is None

    def test_custom_isolation(self) -> None:
        """AgentConfig can specify an IsolationConfig."""
        iso = IsolationConfig(
            sandbox_type=SandboxType.OCI,
            token_tier=TokenTier.ELEVATED,
        )
        config = AgentConfig(isolation=iso)
        assert config.isolation == iso
        assert config.isolation.token_tier == TokenTier.ELEVATED


# ── Tests for ReviewConfig ──


class TestReviewConfig:
    """Tests for ReviewConfig."""

    def test_default_review_on_attempt(self) -> None:
        """ReviewConfig defaults review_on_attempt to 1."""
        config = ReviewConfig(agent=AgentConfig())
        assert config.review_on_attempt == 1

    def test_custom_review_on_attempt(self) -> None:
        """ReviewConfig can specify custom review attempt number."""
        config = ReviewConfig(
            agent=AgentConfig(),
            review_on_attempt=2,
        )
        assert config.review_on_attempt == 2

    def test_agent_config_required(self) -> None:
        """ReviewConfig requires an AgentConfig."""
        agent = AgentConfig(model="claude-opus-4-6")
        config = ReviewConfig(agent=agent)
        assert config.agent == agent

    def test_is_frozen(self) -> None:
        """ReviewConfig is immutable."""
        config = ReviewConfig(agent=AgentConfig())
        with pytest.raises(AttributeError):
            config.review_on_attempt = 2  # type: ignore

    def test_equality(self) -> None:
        """ReviewConfigs with same values are equal."""
        agent = AgentConfig(model="claude-opus-4-6")
        config1 = ReviewConfig(agent=agent, review_on_attempt=1)
        config2 = ReviewConfig(agent=agent, review_on_attempt=1)
        assert config1 == config2


# ── Tests for Task ──


class TestTask:
    """Tests for Task specification."""

    def test_minimal_task(self) -> None:
        """A Task can be created with just id and role."""
        task = Task(id="my_task", role=AgentRole.GENERIC)
        assert task.id == "my_task"
        assert task.role == AgentRole.GENERIC
        assert task.description is None
        assert task.tagged_paths == ()
        assert task.dependencies == ()
        assert task.completion_gate is None
        assert task.max_gate_attempts is None
        assert task.review is None
        assert task.workstream_id == "default"

    def test_task_with_description(self) -> None:
        """Task can have a description."""
        task = Task(
            id="write_tests",
            role=AgentRole.TEST_WRITER,
            description="Write unit tests for the parser",
        )
        assert task.description == "Write unit tests for the parser"

    def test_task_with_paths(self) -> None:
        """Task can specify file paths."""
        from pathlib import Path

        tagged = (
            TaggedPath(path=Path("parser.py"), category="src"),
            TaggedPath(path=Path("test_parser.py"), category="test"),
        )
        task = Task(
            id="implement",
            role=AgentRole.IMPLEMENTER,
            tagged_paths=tagged,
        )
        assert task.tagged_paths == tagged

    def test_task_with_dependencies(self) -> None:
        """Task can specify dependency IDs."""
        task = Task(
            id="implement",
            role=AgentRole.IMPLEMENTER,
            dependencies=("spec", "tests"),
        )
        assert task.dependencies == ("spec", "tests")
        assert len(task.dependencies) == 2

    def test_task_with_completion_gate(self) -> None:
        """Task can specify a completion gate (shell command)."""
        task = Task(
            id="test_run",
            role=AgentRole.IMPLEMENTER,
            completion_gate="pixi run pytest",
        )
        assert task.completion_gate == "pixi run pytest"

    def test_task_with_max_gate_attempts(self) -> None:
        """Task can specify max gate attempts."""
        task = Task(
            id="flaky_test",
            role=AgentRole.IMPLEMENTER,
            max_gate_attempts=3,
        )
        assert task.max_gate_attempts == 3

    def test_task_with_primary_agent(self) -> None:
        """Task can specify primary agent configuration."""
        agent_config = AgentConfig(model="claude-opus-4-6")
        task = Task(
            id="complex_task",
            role=AgentRole.IMPLEMENTER,
            primary_agent=agent_config,
        )
        assert task.primary_agent == agent_config

    def test_task_with_review(self) -> None:
        """Task can specify review configuration."""
        review_config = ReviewConfig(
            agent=AgentConfig(model="claude-opus-4-6"),
            review_on_attempt=1,
        )
        task = Task(
            id="careful_task",
            role=AgentRole.IMPLEMENTER,
            review=review_config,
        )
        assert task.review == review_config

    def test_task_with_custom_workstream_id(self) -> None:
        """Task can specify a non-default workstream ID."""
        task = Task(
            id="feature_a_impl",
            role=AgentRole.IMPLEMENTER,
            workstream_id="feature_a",
        )
        assert task.workstream_id == "feature_a"

    def test_task_with_all_fields(self) -> None:
        """Task can be created with all fields specified."""
        from pathlib import Path

        review_agent = AgentConfig(model="claude-opus-4-6")
        review_config = ReviewConfig(agent=review_agent, review_on_attempt=1)
        tagged = (
            TaggedPath(path=Path("main.py"), category="src"),
            TaggedPath(path=Path("test_main.py"), category="test"),
        )

        task = Task(
            id="impl",
            role=AgentRole.IMPLEMENTER,
            description="Implement the feature",
            tagged_paths=tagged,
            dependencies=("spec",),
            completion_gate="pytest",
            max_gate_attempts=5,
            primary_agent=AgentConfig(model="claude-sonnet-4-6"),
            review=review_config,
            workstream_id="feature_a",
        )

        assert task.id == "impl"
        assert task.role == AgentRole.IMPLEMENTER
        assert task.description == "Implement the feature"
        assert task.tagged_paths == tagged
        assert task.dependencies == ("spec",)
        assert task.completion_gate == "pytest"
        assert task.max_gate_attempts == 5
        assert task.review == review_config
        assert task.workstream_id == "feature_a"

    def test_task_is_frozen(self) -> None:
        """Task is immutable."""
        task = Task(id="my_task", role=AgentRole.GENERIC)
        with pytest.raises(AttributeError):
            task.id = "new_id"  # type: ignore

    def test_task_is_hashable(self) -> None:
        """Task can be hashed (used in sets, as dict keys)."""
        task1 = Task(id="task1", role=AgentRole.GENERIC)
        task2 = Task(id="task1", role=AgentRole.GENERIC)
        assert hash(task1) == hash(task2)

    def test_task_equality(self) -> None:
        """Tasks with same content are equal."""
        task1 = Task(
            id="task1",
            role=AgentRole.GENERIC,
            description="A generic task",
        )
        task2 = Task(
            id="task1",
            role=AgentRole.GENERIC,
            description="A generic task",
        )
        assert task1 == task2

    def test_task_inequality(self) -> None:
        """Tasks with different id are not equal."""
        task1 = Task(id="task1", role=AgentRole.GENERIC)
        task2 = Task(id="task2", role=AgentRole.GENERIC)
        assert task1 != task2

    def test_dependency_chain(self) -> None:
        """Tasks can form a dependency chain via IDs."""
        task3 = Task(
            id="task3",
            role=AgentRole.IMPLEMENTER,
            dependencies=("task1", "task2"),
        )

        assert len(task3.dependencies) == 2
        assert "task1" in task3.dependencies
        assert "task2" in task3.dependencies

    def test_task_as_dict_key(self) -> None:
        """Tasks can be used as dictionary keys (they are hashable)."""
        task = Task(id="key_task", role=AgentRole.GENERIC)
        d = {task: "value"}
        assert d[task] == "value"

    def test_task_in_set(self) -> None:
        """Tasks can be stored in sets (they are hashable)."""
        task1 = Task(id="task1", role=AgentRole.GENERIC)
        task2 = Task(id="task2", role=AgentRole.GENERIC)
        task_set = {task1, task2}
        assert len(task_set) == 2
        assert task1 in task_set

    def test_default_agent_config(self) -> None:
        """Task uses default AgentConfig when not specified."""
        task = Task(id="task", role=AgentRole.GENERIC)
        assert task.primary_agent.framework == AgentFramework.CLAUDE_CODE
        assert task.primary_agent.model is None

    def test_default_isolation_is_none(self) -> None:
        """Task defaults isolation to None."""
        task = Task(id="task", role=AgentRole.GENERIC)
        assert task.isolation is None

    def test_task_with_isolation(self) -> None:
        """Task can specify an IsolationConfig."""
        iso = IsolationConfig(
            sandbox_type=SandboxType.OCI,
            token_tier=TokenTier.STANDARD,
        )
        task = Task(id="task", role=AgentRole.GENERIC, isolation=iso)
        assert task.isolation == iso
        assert task.isolation.sandbox_type == SandboxType.OCI
