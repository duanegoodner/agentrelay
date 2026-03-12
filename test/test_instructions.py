"""Tests for agentrelay.instructions — per-role instruction builders."""

from __future__ import annotations

from agentrelay.instructions import (
    InstructionContext,
    build_context_content,
    build_instructions,
    instruction_context_from_runtime,
)
from agentrelay.task import (
    AgentConfig,
    AgentRole,
    AgentVerbosity,
    ReviewConfig,
    Task,
    TaskPaths,
)
from agentrelay.task_graph import TaskGraph
from agentrelay.task_runtime import TaskRuntime

# ── Helpers ──


def _ctx(
    role: AgentRole = AgentRole.GENERIC,
    description: str = "Do the thing",
    paths: TaskPaths | None = None,
    completion_gate: str | None = None,
    max_gate_attempts: int | None = None,
    review: ReviewConfig | None = None,
    adr_verbosity: AgentVerbosity = AgentVerbosity.NONE,
    dependency_descriptions: dict[str, str | None] | None = None,
    graph_branch: str = "graph/demo",
    graph_name: str | None = "demo",
    effective_gate_attempts: int = 5,
    attempt_num: int = 0,
    agent_api_module: str = "agentrelay",
    dependencies: tuple[str, ...] = (),
) -> InstructionContext:
    """Build an InstructionContext with sensible defaults for testing."""
    task = Task(
        id="test_task",
        role=role,
        description=description,
        paths=paths or TaskPaths(),
        dependencies=dependencies,
        completion_gate=completion_gate,
        max_gate_attempts=max_gate_attempts,
        primary_agent=AgentConfig(adr_verbosity=adr_verbosity),
        review=review,
    )
    return InstructionContext(
        task=task,
        graph_branch=graph_branch,
        graph_name=graph_name,
        dependency_descriptions=dependency_descriptions or {},
        effective_gate_attempts=effective_gate_attempts,
        attempt_num=attempt_num,
        agent_api_module=agent_api_module,
    )


# ── Dispatch tests ──


class TestBuildInstructions:
    """Tests for the top-level build_instructions dispatcher."""

    def test_dispatches_generic(self) -> None:
        """GENERIC role produces generic instructions."""
        result = build_instructions(_ctx(role=AgentRole.GENERIC))
        assert "Your task:" in result
        assert "Do the work described in your task" in result

    def test_dispatches_spec_writer(self) -> None:
        """SPEC_WRITER role produces spec writer instructions."""
        result = build_instructions(_ctx(role=AgentRole.SPEC_WRITER))
        assert "SPEC WRITER" in result
        assert "Do NOT implement any function or method bodies" in result

    def test_dispatches_test_writer(self) -> None:
        """TEST_WRITER role produces test writer instructions."""
        result = build_instructions(_ctx(role=AgentRole.TEST_WRITER))
        assert "TEST WRITER" in result
        assert "do not implement the feature" in result.lower()

    def test_dispatches_test_reviewer(self) -> None:
        """TEST_REVIEWER role produces test reviewer instructions."""
        result = build_instructions(_ctx(role=AgentRole.TEST_REVIEWER))
        assert "TEST REVIEWER" in result
        assert "review file" in result.lower()

    def test_dispatches_implementer(self) -> None:
        """IMPLEMENTER role produces implementer instructions."""
        paths = TaskPaths(src=("src/widget.py",))
        result = build_instructions(_ctx(role=AgentRole.IMPLEMENTER, paths=paths))
        assert "IMPLEMENTER" in result
        assert "preserve all existing docstrings" in result.lower()


# ── Generic builder tests ──


class TestGenericBuilder:
    """Tests for the generic instruction builder."""

    def test_includes_task_description(self) -> None:
        """Task description appears in output."""
        result = build_instructions(_ctx(description="Build the widget"))
        assert "Build the widget" in result

    def test_includes_graph_branch(self) -> None:
        """Graph branch appears in PR creation step."""
        result = build_instructions(_ctx(graph_branch="graph/my-ws"))
        assert "graph/my-ws" in result

    def test_context_note_when_dependencies(self) -> None:
        """Context note appears when task has dependency descriptions."""
        result = build_instructions(_ctx(dependency_descriptions={"dep_a": "Some dep"}))
        assert "context.md" in result

    def test_no_context_note_without_dependencies(self) -> None:
        """No context note when task has no dependencies."""
        result = build_instructions(_ctx())
        assert "context.md" not in result

    def test_spec_reading_step_with_paths(self) -> None:
        """Spec reading preamble appears when src paths exist."""
        paths = TaskPaths(src=("src/foo.py",))
        result = build_instructions(_ctx(paths=paths))
        assert "src/foo.py" in result
        assert "API contract" in result

    def test_no_spec_reading_without_paths(self) -> None:
        """No spec reading preamble when no paths."""
        result = build_instructions(_ctx())
        assert "API contract" not in result


# ── Completion gate tests ──


class TestCompletionGate:
    """Tests for completion gate instruction generation."""

    def test_gate_section_present(self) -> None:
        """Gate section appears when completion_gate is set."""
        result = build_instructions(_ctx(completion_gate="pixi run test"))
        assert "completion gate" in result.lower()
        assert "pixi run test" in result

    def test_gate_section_absent(self) -> None:
        """No gate section when completion_gate is None."""
        result = build_instructions(_ctx())
        assert "completion gate" not in result.lower()

    def test_gate_uses_effective_attempts(self) -> None:
        """Gate section uses effective_gate_attempts from context."""
        result = build_instructions(
            _ctx(completion_gate="pytest", effective_gate_attempts=3)
        )
        assert "3 attempts" in result

    def test_gate_mark_failed_on_exhaustion(self) -> None:
        """Gate instructions include mark_failed after exhausting attempts."""
        result = build_instructions(_ctx(completion_gate="pytest"))
        assert "mark_failed" in result


# ── Review config tests ──


class TestReviewConfig:
    """Tests for self-review instruction generation."""

    def test_review_before_gate_attempt_1(self) -> None:
        """Self-review step before gate when review_on_attempt <= 1."""
        review = ReviewConfig(
            agent=AgentConfig(model="claude-opus-4-6"),
            review_on_attempt=1,
        )
        result = build_instructions(_ctx(review=review, completion_gate="pytest"))
        assert "self-review subagent" in result.lower()
        assert "claude-opus-4-6" in result

    def test_conditional_review_on_later_attempt(self) -> None:
        """Conditional review in gate loop when review_on_attempt >= 2."""
        review = ReviewConfig(
            agent=AgentConfig(model="claude-haiku-4-5-20251001"),
            review_on_attempt=3,
        )
        result = build_instructions(_ctx(review=review, completion_gate="pytest"))
        assert "Attempt 3+" in result
        assert "claude-haiku-4-5-20251001" in result

    def test_no_review_without_config(self) -> None:
        """No review step when review is None."""
        result = build_instructions(_ctx())
        assert "self-review" not in result.lower()


# ── ADR verbosity tests ──


class TestAdrVerbosity:
    """Tests for ADR instruction generation based on verbosity level."""

    def test_none_no_adr(self) -> None:
        """No ADR section for AgentVerbosity.NONE."""
        result = build_instructions(_ctx(adr_verbosity=AgentVerbosity.NONE))
        assert "Architecture Decision Record" not in result

    def test_standard_no_adr(self) -> None:
        """No ADR section for AgentVerbosity.STANDARD."""
        result = build_instructions(_ctx(adr_verbosity=AgentVerbosity.STANDARD))
        assert "Architecture Decision Record" not in result

    def test_detailed_has_adr(self) -> None:
        """ADR section present for AgentVerbosity.DETAILED."""
        result = build_instructions(_ctx(adr_verbosity=AgentVerbosity.DETAILED))
        assert "Architecture Decision Record" in result
        assert "## Context" in result
        assert "## Decision" in result

    def test_educational_has_extra_sections(self) -> None:
        """Educational ADR includes Key Concepts and Alternatives."""
        result = build_instructions(_ctx(adr_verbosity=AgentVerbosity.EDUCATIONAL))
        assert "Key Concepts" in result
        assert "Alternatives Considered" in result


# ── Spec writer tests ──


class TestSpecWriterBuilder:
    """Tests for spec writer instruction specifics."""

    def test_includes_src_paths(self) -> None:
        """Source file paths appear in stub creation instructions."""
        paths = TaskPaths(src=("src/widget.py", "src/gadget.py"))
        result = build_instructions(_ctx(role=AgentRole.SPEC_WRITER, paths=paths))
        assert "src/widget.py" in result
        assert "src/gadget.py" in result

    def test_includes_spec_path(self) -> None:
        """Spec file path appears when provided."""
        paths = TaskPaths(src=("src/foo.py",), spec="specs/foo.md")
        result = build_instructions(_ctx(role=AgentRole.SPEC_WRITER, paths=paths))
        assert "specs/foo.md" in result

    def test_no_spec_path(self) -> None:
        """No spec step when spec is None."""
        paths = TaskPaths(src=("src/foo.py",))
        result = build_instructions(_ctx(role=AgentRole.SPEC_WRITER, paths=paths))
        assert "supplementary" not in result.lower()

    def test_importability_check(self) -> None:
        """Includes importability verification step."""
        result = build_instructions(_ctx(role=AgentRole.SPEC_WRITER))
        assert "importable" in result.lower()

    def test_no_implementation(self) -> None:
        """Explicitly forbids implementing function bodies."""
        result = build_instructions(_ctx(role=AgentRole.SPEC_WRITER))
        assert "Do NOT implement" in result


# ── Test writer tests ──


class TestTestWriterBuilder:
    """Tests for test writer instruction specifics."""

    def test_includes_test_paths(self) -> None:
        """Test file paths appear in instructions."""
        paths = TaskPaths(test=("test/test_widget.py",))
        result = build_instructions(_ctx(role=AgentRole.TEST_WRITER, paths=paths))
        assert "test/test_widget.py" in result

    def test_stub_note_with_src_paths(self) -> None:
        """Warns not to overwrite stubs when src paths provided."""
        paths = TaskPaths(src=("src/widget.py",), test=("test/test_widget.py",))
        result = build_instructions(_ctx(role=AgentRole.TEST_WRITER, paths=paths))
        assert "do NOT create or overwrite" in result

    def test_collect_only_verification(self) -> None:
        """Includes pytest --collect-only step."""
        result = build_instructions(_ctx(role=AgentRole.TEST_WRITER))
        assert "--collect-only" in result


# ── Test reviewer tests ──


class TestTestReviewerBuilder:
    """Tests for test reviewer instruction specifics."""

    def test_review_file_name(self) -> None:
        """Review file name derived from task ID."""
        result = build_instructions(_ctx(role=AgentRole.TEST_REVIEWER))
        assert "test_task.md" in result

    def test_verdict_sections(self) -> None:
        """Includes verdict, coverage, and comments sections."""
        result = build_instructions(_ctx(role=AgentRole.TEST_REVIEWER))
        assert "## Verdict" in result
        assert "## Coverage assessment" in result
        assert "## Comments" in result

    def test_mark_failed_option(self) -> None:
        """Includes option to mark_failed for broken tests."""
        result = build_instructions(_ctx(role=AgentRole.TEST_REVIEWER))
        assert "fundamentally broken" in result
        assert "mark_failed" in result


# ── Implementer tests ──


class TestImplementerBuilder:
    """Tests for implementer instruction specifics."""

    def test_review_file_derivation(self) -> None:
        """Review file name derived by removing _impl suffix."""
        ctx = _ctx(role=AgentRole.IMPLEMENTER)
        # task_id is "test_task", so review file is "test_task_review.md"
        result = build_instructions(ctx)
        assert "test_task_review.md" in result

    def test_docstring_preservation_warning(self) -> None:
        """Includes docstring preservation requirement for src paths."""
        paths = TaskPaths(src=("src/widget.py",))
        result = build_instructions(_ctx(role=AgentRole.IMPLEMENTER, paths=paths))
        assert "preserve all existing docstrings" in result.lower()

    def test_run_tests_with_test_paths(self) -> None:
        """Run tests step includes specific test paths."""
        paths = TaskPaths(src=("src/widget.py",), test=("test/test_widget.py",))
        result = build_instructions(_ctx(role=AgentRole.IMPLEMENTER, paths=paths))
        assert "pixi run pytest test/test_widget.py" in result

    def test_concern_recording(self) -> None:
        """Includes record_concern command."""
        result = build_instructions(_ctx(role=AgentRole.IMPLEMENTER))
        assert "record_concern" in result


# ── Context content tests ──


class TestBuildContextContent:
    """Tests for build_context_content."""

    def test_returns_none_without_dependencies(self) -> None:
        """Returns None when no dependency descriptions."""
        result = build_context_content(_ctx())
        assert result is None

    def test_returns_markdown_with_dependencies(self) -> None:
        """Returns markdown with dependency IDs and descriptions."""
        ctx = _ctx(
            dependency_descriptions={
                "dep_a": "Build widget",
                "dep_b": "Test widget",
            }
        )
        result = build_context_content(ctx)
        assert result is not None
        assert "## dep_a" in result
        assert "Build widget" in result
        assert "## dep_b" in result
        assert "Test widget" in result
        assert "prerequisite tasks" in result.lower()

    def test_handles_none_description(self) -> None:
        """Handles None description for a dependency."""
        ctx = _ctx(dependency_descriptions={"dep_a": None})
        result = build_context_content(ctx)
        assert result is not None
        assert "## dep_a" in result


# ── Agent API module tests ──


class TestAgentApiModule:
    """Tests for agent_api_module parameterization."""

    def test_default_module(self) -> None:
        """Default agent_api_module is 'agentrelay'."""
        result = build_instructions(_ctx())
        assert "from agentrelay import WorktreeTaskRunner" in result

    def test_custom_module(self) -> None:
        """Custom agent_api_module appears in signal commands."""
        result = build_instructions(_ctx(agent_api_module="myproject.runner"))
        assert "from myproject.runner import WorktreeTaskRunner" in result
        assert "from agentrelay import" not in result


# ── Factory tests ──


class TestInstructionContextFromRuntime:
    """Tests for the instruction_context_from_runtime factory."""

    def test_extracts_dependency_descriptions(self) -> None:
        """Factory looks up dependency descriptions from TaskGraph."""
        dep_task = Task(
            id="dep_a",
            role=AgentRole.GENERIC,
            description="Build the dependency",
        )
        main_task = Task(
            id="main_task",
            role=AgentRole.GENERIC,
            description="Use the dependency",
            dependencies=("dep_a",),
        )
        graph = TaskGraph.from_tasks([dep_task, main_task], name="test-graph")
        runtime = TaskRuntime(task=main_task)

        ctx = instruction_context_from_runtime(
            runtime, graph, graph_branch="graph/test"
        )

        assert ctx.dependency_descriptions == {"dep_a": "Build the dependency"}
        assert ctx.graph_name == "test-graph"
        assert ctx.graph_branch == "graph/test"

    def test_extracts_attempt_num(self) -> None:
        """Factory copies attempt_num from runtime state."""
        task = Task(id="t", role=AgentRole.GENERIC)
        graph = TaskGraph.from_tasks([task])
        runtime = TaskRuntime(task=task)
        runtime.state.attempt_num = 3

        ctx = instruction_context_from_runtime(runtime, graph, graph_branch="graph/x")

        assert ctx.attempt_num == 3

    def test_passes_effective_gate_attempts(self) -> None:
        """Factory passes through effective_gate_attempts parameter."""
        task = Task(id="t", role=AgentRole.GENERIC)
        graph = TaskGraph.from_tasks([task])
        runtime = TaskRuntime(task=task)

        ctx = instruction_context_from_runtime(
            runtime,
            graph,
            graph_branch="graph/x",
            effective_gate_attempts=10,
        )

        assert ctx.effective_gate_attempts == 10

    def test_passes_agent_api_module(self) -> None:
        """Factory passes through agent_api_module parameter."""
        task = Task(id="t", role=AgentRole.GENERIC)
        graph = TaskGraph.from_tasks([task])
        runtime = TaskRuntime(task=task)

        ctx = instruction_context_from_runtime(
            runtime,
            graph,
            graph_branch="graph/x",
            agent_api_module="custom.module",
        )

        assert ctx.agent_api_module == "custom.module"
