"""Tests for run_graph module-level prompt-builder functions."""

from pathlib import Path

from agentrelaysmall.agent_task import AgentRole, AgentTask, TaskPaths
from agentrelaysmall.agent_task_graph import AgentTaskGraph
from agentrelaysmall.run_graph import (
    DEFAULT_GATE_ATTEMPTS,
    _adr_step,
    _build_context_content,
    _build_merger_prompt,
    _build_task_instructions,
    _effective_verbosity,
    _spec_reading_step,
)

# ── helpers ───────────────────────────────────────────────────────────────────

GRAPH_BRANCH = "graph/test-graph"


def make_task(
    task_id: str = "task_001",
    description: str = "do something",
    role: AgentRole = AgentRole.GENERIC,
    dependencies: tuple[AgentTask, ...] = (),
) -> AgentTask:
    return AgentTask(
        id=task_id,
        description=description,
        role=role,
        dependencies=dependencies,
    )


def make_graph(verbosity: str = "standard") -> AgentTaskGraph:
    return AgentTaskGraph(
        name="test-graph",
        tasks={},
        target_repo_root=Path("/tmp"),
        worktrees_root=Path("/tmp/worktrees"),
        verbosity=verbosity,
    )


# ── GENERIC role ──────────────────────────────────────────────────────────────


def test_generic_prompt_contains_task_description():
    task = make_task(description="implement the greet function")
    assert "implement the greet function" in _build_task_instructions(
        task, GRAPH_BRANCH
    )


def test_generic_prompt_contains_task_id():
    task = make_task(task_id="my_task")
    assert "my_task" in _build_task_instructions(task, GRAPH_BRANCH)


def test_generic_prompt_contains_git_add():
    assert "git add" in _build_task_instructions(make_task(), GRAPH_BRANCH)


def test_generic_prompt_contains_gh_pr_create():
    assert "gh pr create" in _build_task_instructions(make_task(), GRAPH_BRANCH)


def test_generic_prompt_contains_mark_done():
    assert "mark_done" in _build_task_instructions(make_task(), GRAPH_BRANCH)


def test_generic_prompt_with_dependencies_contains_context_note():
    dep = make_task(task_id="t1")
    task = make_task(task_id="t2", dependencies=(dep,))
    assert "context" in _build_task_instructions(task, GRAPH_BRANCH).lower()


def test_generic_prompt_without_dependencies_has_no_context_note():
    task = make_task(dependencies=())
    assert "context file" not in _build_task_instructions(task, GRAPH_BRANCH)


def test_generic_prompt_targets_graph_branch():
    task = make_task()
    assert f"--base {GRAPH_BRANCH}" in _build_task_instructions(task, GRAPH_BRANCH)


# ── TEST_WRITER role ──────────────────────────────────────────────────────────


def test_test_writer_prompt_contains_pytest():
    task = make_task(role=AgentRole.TEST_WRITER)
    assert "pytest" in _build_task_instructions(task, GRAPH_BRANCH)


def test_test_writer_prompt_contains_collect_only():
    task = make_task(role=AgentRole.TEST_WRITER)
    assert "--collect-only" in _build_task_instructions(task, GRAPH_BRANCH)


def test_test_writer_prompt_says_do_not_implement():
    task = make_task(role=AgentRole.TEST_WRITER)
    prompt = _build_task_instructions(task, GRAPH_BRANCH).lower()
    assert "do not implement" in prompt or "not implement" in prompt


def test_test_writer_prompt_contains_mark_done():
    task = make_task(role=AgentRole.TEST_WRITER)
    assert "mark_done" in _build_task_instructions(task, GRAPH_BRANCH)


def test_test_writer_prompt_contains_task_description():
    task = make_task(description="add login endpoint", role=AgentRole.TEST_WRITER)
    assert "add login endpoint" in _build_task_instructions(task, GRAPH_BRANCH)


def test_test_writer_prompt_contains_task_id():
    task = make_task(task_id="auth_tests", role=AgentRole.TEST_WRITER)
    assert "auth_tests" in _build_task_instructions(task, GRAPH_BRANCH)


def test_test_writer_prompt_targets_graph_branch():
    task = make_task(role=AgentRole.TEST_WRITER)
    assert f"--base {GRAPH_BRANCH}" in _build_task_instructions(task, GRAPH_BRANCH)


# ── TEST_REVIEWER role ────────────────────────────────────────────────────────


def test_test_reviewer_prompt_contains_review_file():
    task = make_task(task_id="foo_review", role=AgentRole.TEST_REVIEWER)
    assert "foo_review.md" in _build_task_instructions(task, GRAPH_BRANCH)


def test_test_reviewer_prompt_contains_approved():
    task = make_task(role=AgentRole.TEST_REVIEWER)
    assert "APPROVED" in _build_task_instructions(task, GRAPH_BRANCH)


def test_test_reviewer_prompt_contains_concerns():
    task = make_task(role=AgentRole.TEST_REVIEWER)
    assert "CONCERNS" in _build_task_instructions(task, GRAPH_BRANCH)


def test_test_reviewer_prompt_contains_coverage():
    task = make_task(role=AgentRole.TEST_REVIEWER)
    assert "coverage" in _build_task_instructions(task, GRAPH_BRANCH).lower()


def test_test_reviewer_prompt_contains_mark_failed():
    task = make_task(role=AgentRole.TEST_REVIEWER)
    assert "mark_failed" in _build_task_instructions(task, GRAPH_BRANCH)


def test_test_reviewer_prompt_contains_mark_done():
    task = make_task(role=AgentRole.TEST_REVIEWER)
    assert "mark_done" in _build_task_instructions(task, GRAPH_BRANCH)


def test_test_reviewer_prompt_contains_task_description():
    task = make_task(description="validate auth module", role=AgentRole.TEST_REVIEWER)
    assert "validate auth module" in _build_task_instructions(task, GRAPH_BRANCH)


def test_test_reviewer_prompt_does_not_say_implement():
    task = make_task(role=AgentRole.TEST_REVIEWER)
    assert "do not implement" in _build_task_instructions(task, GRAPH_BRANCH).lower()


def test_test_reviewer_prompt_targets_graph_branch():
    task = make_task(role=AgentRole.TEST_REVIEWER)
    assert f"--base {GRAPH_BRANCH}" in _build_task_instructions(task, GRAPH_BRANCH)


# ── IMPLEMENTER role ──────────────────────────────────────────────────────────


def test_implementer_prompt_contains_pytest():
    task = make_task(role=AgentRole.IMPLEMENTER)
    assert "pytest" in _build_task_instructions(task, GRAPH_BRANCH)


def test_implementer_prompt_references_review_file():
    task = make_task(task_id="add_auth_impl", role=AgentRole.IMPLEMENTER)
    assert "add_auth_review.md" in _build_task_instructions(task, GRAPH_BRANCH)


def test_implementer_prompt_contains_stub():
    task = make_task(role=AgentRole.IMPLEMENTER)
    assert "stub" in _build_task_instructions(task, GRAPH_BRANCH).lower()


def test_implementer_prompt_mentions_passing_tests():
    task = make_task(role=AgentRole.IMPLEMENTER)
    assert "pass" in _build_task_instructions(task, GRAPH_BRANCH).lower()


def test_implementer_prompt_contains_mark_done():
    task = make_task(role=AgentRole.IMPLEMENTER)
    assert "mark_done" in _build_task_instructions(task, GRAPH_BRANCH)


def test_implementer_prompt_contains_task_description():
    task = make_task(description="add caching layer", role=AgentRole.IMPLEMENTER)
    assert "add caching layer" in _build_task_instructions(task, GRAPH_BRANCH)


def test_implementer_prompt_contains_task_id():
    task = make_task(task_id="cache_impl", role=AgentRole.IMPLEMENTER)
    assert "cache_impl" in _build_task_instructions(task, GRAPH_BRANCH)


def test_implementer_prompt_targets_graph_branch():
    task = make_task(role=AgentRole.IMPLEMENTER)
    assert f"--base {GRAPH_BRANCH}" in _build_task_instructions(task, GRAPH_BRANCH)


# ── _build_context_content ────────────────────────────────────────────────────


def test_context_content_is_none_when_no_dependencies():
    task = make_task(dependencies=())
    assert _build_context_content(task) is None


def test_context_content_includes_dep_id():
    dep = make_task(task_id="dep_task")
    task = make_task(task_id="main_task", dependencies=(dep,))
    content = _build_context_content(task)
    assert content is not None
    assert "dep_task" in content


def test_context_content_includes_dep_description():
    dep = make_task(task_id="dep_task", description="wrote the tests")
    task = make_task(task_id="main_task", dependencies=(dep,))
    content = _build_context_content(task)
    assert content is not None
    assert "wrote the tests" in content


def test_context_content_mentions_merged_into_main():
    dep = make_task(task_id="dep_task")
    task = make_task(task_id="main_task", dependencies=(dep,))
    content = _build_context_content(task)
    assert content is not None
    assert "merged into main" in content


# ── completion_gate in generic instructions ───────────────────────────────────


def test_generic_instructions_with_completion_gate_mentions_command():
    task = AgentTask(
        id="t1", description="do something", completion_gate="pixi run pytest"
    )
    instructions = _build_task_instructions(task, GRAPH_BRANCH)
    assert "pixi run pytest" in instructions


def test_generic_instructions_without_completion_gate_has_no_gate_step():
    task = make_task()
    instructions = _build_task_instructions(task, GRAPH_BRANCH)
    assert "completion gate" not in instructions.lower()


# ── DEFAULT_GATE_ATTEMPTS and attempt count in instructions ───────────────────


def test_default_gate_attempts_is_five():
    assert DEFAULT_GATE_ATTEMPTS == 5


def test_generic_instructions_show_attempt_count_in_gate_block():
    task = AgentTask(
        id="t1", description="do something", completion_gate="pixi run pytest"
    )
    instructions = _build_task_instructions(task, GRAPH_BRANCH, effective_attempts=3)
    assert "3" in instructions
    assert "attempt" in instructions.lower()


def test_generic_instructions_gate_block_uses_effective_attempts():
    task = AgentTask(
        id="t1", description="do something", completion_gate="pixi run pytest"
    )
    instructions_2 = _build_task_instructions(task, GRAPH_BRANCH, effective_attempts=2)
    instructions_7 = _build_task_instructions(task, GRAPH_BRANCH, effective_attempts=7)
    assert "2" in instructions_2
    assert "7" in instructions_7


# ── task_params substitution and coverage hint ────────────────────────────────


def test_generic_instructions_include_coverage_hint_when_threshold_in_task_params():
    task = AgentTask(
        id="t1",
        description="do something",
        completion_gate="pytest --cov-fail-under={coverage_threshold}",
        task_params={"coverage_threshold": 90},
    )
    instructions = _build_task_instructions(task, GRAPH_BRANCH)
    assert "coverage" in instructions.lower()
    assert "term-missing" in instructions


def test_generic_instructions_no_coverage_hint_when_no_task_params():
    task = AgentTask(
        id="t1", description="do something", completion_gate="pixi run pytest"
    )
    instructions = _build_task_instructions(task, GRAPH_BRANCH)
    assert "term-missing" not in instructions


def test_generic_instructions_substitute_task_params_in_gate_command():
    task = AgentTask(
        id="t1",
        description="do something",
        completion_gate="pytest --cov-fail-under={coverage_threshold} -q",
        task_params={"coverage_threshold": 85},
    )
    instructions = _build_task_instructions(task, GRAPH_BRANCH)
    assert "85" in instructions
    assert "{coverage_threshold}" not in instructions


# ── review_model and review_on_attempt in generic instructions ────────────────


def test_generic_instructions_include_review_step_when_review_model_set():
    task = AgentTask(
        id="t1",
        description="do something",
        review_model="claude-sonnet-4-6",
    )
    instructions = _build_task_instructions(task, GRAPH_BRANCH)
    assert "claude-sonnet-4-6" in instructions
    assert "review" in instructions.lower()


def test_generic_instructions_review_step_before_gate_when_review_on_attempt_1():
    task = AgentTask(
        id="t1",
        description="do something",
        completion_gate="pixi run pytest",
        review_model="claude-sonnet-4-6",
        review_on_attempt=1,
    )
    instructions = _build_task_instructions(task, GRAPH_BRANCH)
    # review step appears before the gate block (before "For each attempt:")
    review_pos = instructions.lower().find("review subagent")
    gate_pos = instructions.lower().find("for each attempt")
    assert review_pos != -1
    assert gate_pos != -1
    assert review_pos < gate_pos


def test_generic_instructions_review_step_inside_gate_when_review_on_attempt_2():
    task = AgentTask(
        id="t1",
        description="do something",
        completion_gate="pixi run pytest",
        review_model="claude-sonnet-4-6",
        review_on_attempt=2,
    )
    instructions = _build_task_instructions(task, GRAPH_BRANCH)
    assert "attempt 2" in instructions.lower()
    # conditional review is inside the gate block
    gate_pos = instructions.lower().find("for each attempt")
    review_pos = instructions.lower().find("review subagent")
    assert review_pos != -1
    assert gate_pos != -1
    assert review_pos > gate_pos


def test_generic_instructions_no_review_step_when_review_model_none():
    task = make_task()
    instructions = _build_task_instructions(task, GRAPH_BRANCH)
    assert "self-review" not in instructions.lower()
    assert "subagent" not in instructions.lower()


# ── gate exit-code authority and output capture ───────────────────────────────


def test_generic_instructions_gate_mentions_exit_code():
    task = AgentTask(
        id="t1", description="do something", completion_gate="pixi run pytest"
    )
    instructions = _build_task_instructions(task, GRAPH_BRANCH)
    assert "exit" in instructions.lower()


def test_generic_instructions_gate_mentions_gate_last_output():
    task = AgentTask(
        id="t1", description="do something", completion_gate="pixi run pytest"
    )
    instructions = _build_task_instructions(task, GRAPH_BRANCH)
    assert "gate_last_output.txt" in instructions


# ── _spec_reading_step ────────────────────────────────────────────────────────


def test_spec_reading_step_with_src_paths_returns_nonempty():
    task = AgentTask(id="t1", paths=TaskPaths(src=("src/foo.py", "src/bar.py")))
    result = _spec_reading_step(task)
    assert result != ""
    assert "src/foo.py" in result
    assert "src/bar.py" in result


def test_spec_reading_step_with_spec_path_includes_spec_path():
    task = AgentTask(id="t1", paths=TaskPaths(spec="specs/foo.md"))
    result = _spec_reading_step(task)
    assert result != ""
    assert "specs/foo.md" in result


def test_spec_reading_step_with_neither_returns_empty():
    task = AgentTask(id="t1")
    assert _spec_reading_step(task) == ""


# ── SPEC_WRITER role ──────────────────────────────────────────────────────────


def test_spec_writer_prompt_contains_role_header():
    task = AgentTask(
        id="spec_001",
        role=AgentRole.SPEC_WRITER,
        paths=TaskPaths(src=("src/foo.py",)),
    )
    assert "SPEC WRITER" in _build_task_instructions(task, GRAPH_BRANCH)


def test_spec_writer_prompt_contains_notimplementederror():
    task = AgentTask(
        id="spec_001",
        role=AgentRole.SPEC_WRITER,
        paths=TaskPaths(src=("src/foo.py",)),
    )
    assert "NotImplementedError" in _build_task_instructions(task, GRAPH_BRANCH)


def test_spec_writer_prompt_says_do_not_implement():
    task = AgentTask(
        id="spec_001",
        role=AgentRole.SPEC_WRITER,
        paths=TaskPaths(src=("src/foo.py",)),
    )
    assert "do not implement" in _build_task_instructions(task, GRAPH_BRANCH).lower()


def test_spec_writer_prompt_with_spec_path_mentions_spec_file():
    task = AgentTask(
        id="spec_001",
        role=AgentRole.SPEC_WRITER,
        paths=TaskPaths(src=("src/foo.py",), spec="specs/foo.md"),
    )
    assert "specs/foo.md" in _build_task_instructions(task, GRAPH_BRANCH)


def test_spec_writer_prompt_without_spec_path_no_supplementary_mention():
    task = AgentTask(
        id="spec_001",
        role=AgentRole.SPEC_WRITER,
        paths=TaskPaths(src=("src/foo.py",)),
    )
    prompt = _build_task_instructions(task, GRAPH_BRANCH)
    assert "supplementary" not in prompt.lower()


# ── TEST_WRITER with src_paths / test_paths ───────────────────────────────────


def test_test_writer_with_src_paths_contains_src_paths():
    task = AgentTask(
        id="tw_001",
        role=AgentRole.TEST_WRITER,
        paths=TaskPaths(src=("src/foo.py",), test=("tests/test_foo.py",)),
    )
    assert "src/foo.py" in _build_task_instructions(task, GRAPH_BRANCH)


def test_test_writer_with_test_paths_contains_test_paths():
    task = AgentTask(
        id="tw_001",
        role=AgentRole.TEST_WRITER,
        paths=TaskPaths(src=("src/foo.py",), test=("tests/test_foo.py",)),
    )
    assert "tests/test_foo.py" in _build_task_instructions(task, GRAPH_BRANCH)


def test_test_writer_with_src_paths_does_not_say_create_stubs():
    task = AgentTask(
        id="tw_001",
        role=AgentRole.TEST_WRITER,
        paths=TaskPaths(src=("src/foo.py",), test=("tests/test_foo.py",)),
    )
    prompt = _build_task_instructions(task, GRAPH_BRANCH).lower()
    assert "write a stub" not in prompt
    assert "create a stub" not in prompt


# ── IMPLEMENTER with src_paths + test_paths ───────────────────────────────────


def test_implementer_with_src_paths_contains_src_paths():
    task = AgentTask(
        id="impl_001",
        role=AgentRole.IMPLEMENTER,
        paths=TaskPaths(src=("src/foo.py",), test=("tests/test_foo.py",)),
    )
    assert "src/foo.py" in _build_task_instructions(task, GRAPH_BRANCH)


def test_implementer_with_test_paths_contains_test_paths():
    task = AgentTask(
        id="impl_001",
        role=AgentRole.IMPLEMENTER,
        paths=TaskPaths(src=("src/foo.py",), test=("tests/test_foo.py",)),
    )
    assert "tests/test_foo.py" in _build_task_instructions(task, GRAPH_BRANCH)


def test_implementer_with_src_paths_mentions_preserve_docstrings():
    task = AgentTask(
        id="impl_001",
        role=AgentRole.IMPLEMENTER,
        paths=TaskPaths(src=("src/foo.py",), test=("tests/test_foo.py",)),
    )
    prompt = _build_task_instructions(task, GRAPH_BRANCH).lower()
    assert "preserve" in prompt
    assert "docstring" in prompt


# ── GENERIC with spec-reading step ────────────────────────────────────────────


def test_generic_with_spec_path_contains_spec_reading_step():
    task = AgentTask(id="t1", paths=TaskPaths(spec="specs/foo.md"))
    prompt = _build_task_instructions(task, GRAPH_BRANCH)
    assert "specs/foo.md" in prompt
    assert "Before starting" in prompt


def test_generic_without_src_paths_or_spec_path_no_spec_reading_step():
    task = make_task()
    prompt = _build_task_instructions(task, GRAPH_BRANCH)
    assert "API contract" not in prompt


# ── _build_merger_prompt ──────────────────────────────────────────────────────


def test_merger_prompt_implementer_contains_docstring_check():
    task = AgentTask(
        id="impl_001",
        role=AgentRole.IMPLEMENTER,
        paths=TaskPaths(src=("src/foo.py",), test=("tests/test_foo.py",)),
    )
    prompt = _build_merger_prompt(
        task, "https://github.com/o/r/pull/42", Path("/tmp/h.md")
    )
    assert "docstring" in prompt.lower()
    assert "materially" in prompt.lower()
    assert "src/foo.py" in prompt


def test_merger_prompt_non_implementer_no_docstring_integrity_check():
    task = AgentTask(
        id="spec_001",
        role=AgentRole.SPEC_WRITER,
        paths=TaskPaths(src=("src/foo.py",)),
    )
    prompt = _build_merger_prompt(
        task, "https://github.com/o/r/pull/99", Path("/tmp/h.md")
    )
    assert "materially" not in prompt.lower()


def test_merger_prompt_contains_role_header():
    task = make_task()
    prompt = _build_merger_prompt(
        task, "https://github.com/o/r/pull/1", Path("/tmp/h.md")
    )
    assert "PR REVIEWER / MERGER" in prompt


def test_merger_prompt_contains_pr_url():
    task = make_task()
    pr_url = "https://github.com/o/r/pull/123"
    prompt = _build_merger_prompt(task, pr_url, Path("/tmp/h.md"))
    assert pr_url in prompt


def test_merger_prompt_contains_history_path():
    task = make_task()
    history = Path("/workflow/mygraph/merge_history.md")
    prompt = _build_merger_prompt(task, "https://github.com/o/r/pull/1", history)
    assert str(history) in prompt


def test_merger_prompt_contains_mark_done():
    task = make_task()
    prompt = _build_merger_prompt(
        task, "https://github.com/o/r/pull/1", Path("/tmp/h.md")
    )
    assert "mark_done" in prompt


def test_merger_prompt_implementer_no_src_paths_no_docstring_check():
    task = AgentTask(id="impl_002", role=AgentRole.IMPLEMENTER)
    prompt = _build_merger_prompt(
        task, "https://github.com/o/r/pull/5", Path("/tmp/h.md")
    )
    assert "materially" not in prompt.lower()


# ── _effective_verbosity ──────────────────────────────────────────────────────


def test_effective_verbosity_task_none_graph_standard_returns_standard():
    task = AgentTask(id="t1", verbosity=None)
    graph = make_graph(verbosity="standard")
    assert _effective_verbosity(task, graph) == "standard"


def test_effective_verbosity_task_educational_graph_standard_returns_educational():
    task = AgentTask(id="t1", verbosity="educational")
    graph = make_graph(verbosity="standard")
    assert _effective_verbosity(task, graph) == "educational"


def test_effective_verbosity_task_none_graph_detailed_returns_detailed():
    task = AgentTask(id="t1", verbosity=None)
    graph = make_graph(verbosity="detailed")
    assert _effective_verbosity(task, graph) == "detailed"


# ── _adr_step ─────────────────────────────────────────────────────────────────


def test_adr_step_standard_verbosity_returns_empty():
    task = AgentTask(id="my_task", role=AgentRole.GENERIC)
    graph = make_graph(verbosity="standard")
    assert _adr_step(task, graph) == ""


def test_adr_step_detailed_verbosity_returns_nonempty_with_decisions_path():
    task = AgentTask(id="my_task", role=AgentRole.GENERIC)
    graph = make_graph(verbosity="detailed")
    result = _adr_step(task, graph)
    assert result != ""
    assert "docs/decisions/my_task.md" in result


def test_adr_step_educational_verbosity_contains_key_concepts():
    task = AgentTask(id="my_task", role=AgentRole.GENERIC)
    graph = make_graph(verbosity="educational")
    result = _adr_step(task, graph)
    assert "Key Concepts" in result
