"""Graph orchestrator: drives multiple AgentTasks based on a YAML graph definition.

Usage (from repo root, with pixi env active):
    python -m agentrelay.run_graph graphs/demo.yaml
    python -m agentrelay.run_graph graphs/demo.yaml --tmux-session myproject
    python -m agentrelay.run_graph graphs/demo.yaml --keep-panes

Requires:
    - A tmux session already running (default name: 'agentrelay', or set via
      --tmux-session or the 'tmux_session' key in the graph YAML)
    - git repo at repo root with a 'main' branch
    - claude CLI available in PATH
"""

import argparse
import asyncio
from datetime import date
from pathlib import Path

from agentrelay.prototypes.v01.agent_task import AgentRole, AgentTask, TaskStatus
from agentrelay.prototypes.v01.agent_task_graph import (
    AgentTaskGraph,
    AgentTaskGraphBuilder,
)
from agentrelay.prototypes.v01.task_launcher import (
    append_concerns_to_pr,
    close_agent_pane,
    close_pane_by_id,
    create_final_pr,
    create_graph_branch,
    create_worktree,
    launch_agent,
    launch_agent_in_dir,
    merge_history_path,
    merge_pr,
    neutralize_pixi_lock_in_pr,
    pixi_toml_changed_in_pr,
    poll_for_completion,
    poll_for_completion_at,
    pull_graph_branch,
    read_design_concerns,
    read_done_note,
    read_done_note_at,
    record_gate_failure,
    record_run_start,
    remove_worktree,
    run_completion_gate,
    save_agent_log,
    save_pr_summary,
    send_prompt,
    write_adr_index_to_graph_branch,
    write_context,
    write_instructions,
    write_merged_signal,
    write_merger_task_context,
    write_task_context,
)

BOOTSTRAP_PROMPT = (
    "Read $AGENTRELAY_SIGNAL_DIR/instructions.md and follow the steps exactly."
)

DEFAULT_GATE_ATTEMPTS = 5


def _effective_verbosity(task: AgentTask, graph: AgentTaskGraph) -> str:
    """Return effective verbosity for a task, inheriting from graph if task is unset."""
    return task.verbosity or graph.verbosity or "standard"


def _adr_step(task: AgentTask, graph: AgentTaskGraph | None) -> str:
    """Return an ADR-writing step if verbosity is above 'standard', else empty string."""
    if graph is None:
        return ""
    verbosity = _effective_verbosity(task, graph)
    if verbosity == "standard":
        return ""
    today = date.today().isoformat()
    adr_path = f"docs/decisions/{task.id}.md"
    extra_sections = ""
    if verbosity == "educational":
        extra_sections = (
            "\n\n## Key Concepts\n"
            "Explain domain concepts that a reader unfamiliar with this area would need.\n\n"
            "## Alternatives Considered\n"
            "What else did you evaluate? Why did you choose this approach over the alternatives?"
        )
    return (
        f"Write an ADR (Architecture Decision Record) to {adr_path}.\n"
        f"Create the parent directory if needed: mkdir -p docs/decisions\n"
        f"The file must contain this YAML front matter followed by the sections below:\n"
        f"---\n"
        f"task_id: {task.id}\n"
        f"graph: {graph.name}\n"
        f"role: {task.role.value}\n"
        f"date: {today}\n"
        f"verbosity: {verbosity}\n"
        f"---\n\n"
        f"## Context\n"
        f"What situation or codebase state did you find? What constraints existed?\n\n"
        f"## Decision\n"
        f"What did you choose to do and what were the key reasons?\n\n"
        f"## Consequences\n"
        f"What are the trade-offs? What should future contributors know?"
        f"{extra_sections}\n\n"
        f"Then stage the ADR file before committing:\n"
        f"    git add {adr_path}\n"
    )


def _spec_reading_step(task: AgentTask) -> str:
    """Return a spec-reading preamble if the task has src_paths or spec_path."""
    if not task.paths.src and not task.paths.spec:
        return ""
    parts = ["Before starting, read the following to understand the API contract:\n"]
    if task.paths.src:
        paths_str = " ".join(task.paths.src)
        parts.append(
            f"  Source stubs (docstrings are the authoritative spec): {paths_str}\n"
        )
    if task.paths.spec:
        parts.append(f"  Supplementary spec file: {task.paths.spec}\n")
    parts.append("\n")
    return "".join(parts)


def validate_task_paths(task: AgentTask, worktree_path: Path) -> None:
    """Validate that expected files/dirs exist in the worktree before agent launch.

    Raises ValueError with a descriptive message if any required path is missing.
    MERGER and GENERIC roles are not validated.
    """
    role = task.role
    if role == AgentRole.SPEC_WRITER:
        for src_path in task.paths.src:
            parent = (worktree_path / src_path).parent
            if not parent.exists():
                raise ValueError(
                    f"[validate] {task.id}: expected parent directory "
                    f"'{src_path}' parent in worktree but not found"
                )
        if task.paths.spec:
            parent = (worktree_path / task.paths.spec).parent
            if not parent.exists():
                raise ValueError(
                    f"[validate] {task.id}: expected parent directory for "
                    f"spec_path '{task.paths.spec}' in worktree but not found"
                )
    elif role == AgentRole.TEST_WRITER:
        for src_path in task.paths.src:
            full_path = worktree_path / src_path
            if not full_path.exists():
                raise ValueError(
                    f"[validate] {task.id}: expected src_path '{src_path}' "
                    f"in worktree but not found"
                )
        for test_path in task.paths.test:
            parent = (worktree_path / test_path).parent
            if not parent.exists():
                raise ValueError(
                    f"[validate] {task.id}: expected parent directory for "
                    f"test_path '{test_path}' in worktree but not found"
                )
    elif role == AgentRole.IMPLEMENTER:
        for src_path in task.paths.src:
            full_path = worktree_path / src_path
            if not full_path.exists():
                raise ValueError(
                    f"[validate] {task.id}: expected src_path '{src_path}' "
                    f"in worktree but not found"
                )
        for test_path in task.paths.test:
            full_path = worktree_path / test_path
            if not full_path.exists():
                raise ValueError(
                    f"[validate] {task.id}: expected test_path '{test_path}' "
                    f"in worktree but not found"
                )
    # MERGER and GENERIC: no validation


def _resolve_gate(task: AgentTask) -> str:
    """Substitute task_params {key} placeholders in the completion gate command."""
    cmd = task.completion_gate or ""
    for key, val in task.task_params.items():
        cmd = cmd.replace(f"{{{key}}}", str(val))
    return cmd


def _build_context_content(task: AgentTask) -> str | None:
    """Produce context.md content summarising completed dependency tasks."""
    if not task.dependencies:
        return None
    lines = ["# Context from prerequisite tasks\n"]
    for dep in task.dependencies:
        lines.append(f"## {dep.id}\n")
        lines.append(f"Description: {dep.description}\n")
        lines.append(
            f"The files produced by this task are available in your worktree "
            f"(already merged into main before your branch was created).\n"
        )
    return "\n".join(lines)


def _build_spec_writer_prompt(
    task: AgentTask, graph_branch: str, graph: AgentTaskGraph | None = None
) -> str:
    short_desc = task.description[:60]
    src_paths_str = " ".join(task.paths.src) if task.paths.src else "(see description)"

    steps: list[str] = []
    steps.append(
        f"1. For each file in {src_paths_str}:\n"
        f"   - Create the file with a module-level docstring describing the module's purpose\n"
        f"   - Add all function/class signatures with full Python type annotations\n"
        f"   - Write comprehensive Google-style docstrings on each function: "
        f"Args, Returns, Raises, Examples (with doctestable >>> lines where appropriate)\n"
        f"   - Set all bodies to: raise NotImplementedError\n"
        f"   The docstrings ARE the spec — write them to be authoritative and complete.\n"
        f"   Create any parent directories as needed."
    )

    step_num = 2
    if task.paths.spec:
        steps.append(
            f"{step_num}. Write a brief spec file at {task.paths.spec} that serves as a "
            f"high-level index/narrative pointing to the source files for detailed specs. "
            f"This is supplementary only. Do NOT duplicate the docstring content. "
            f"Create any parent directories as needed."
        )
        step_num += 1

    steps.append(
        f"{step_num}. Verify the stub module(s) are importable "
        f'(e.g. `pixi run python -c "import <module>"`). Fix any import errors.'
    )
    step_num += 1

    adr_text = _adr_step(task, graph)
    if adr_text:
        steps.append(f"{step_num}. {adr_text}")
        step_num += 1

    all_paths = list(task.paths.src)
    if task.paths.spec:
        all_paths.append(task.paths.spec)
    git_add_paths = " ".join(all_paths) if all_paths else "-A"

    steps.append(
        f"{step_num}. Stage, commit, and push:\n"
        f"       git add {git_add_paths}\n"
        f'       git commit -m "{task.id}: {short_desc}"\n'
        f"       git push -u origin HEAD"
    )
    step_num += 1

    steps.append(
        f"{step_num}. Create a PR with a meaningful body, capture the URL, and signal completion:\n"
        f'       PR_URL=$(gh pr create --title "{task.id}" --body "$(cat <<\'PRBODY\'\n'
        f"## Summary\n"
        f"<1-3 sentences describing the stubs and spec written>\n\n"
        f"## Files changed\n"
        f"<bullet list of the key files you created or modified>\n"
        f'PRBODY\n)" --base {graph_branch})\n'
        f'       pixi run python -c "from agentrelay import WorktreeTaskRunner; '
        f"r = WorktreeTaskRunner.from_config(); "
        f"r.mark_done('$PR_URL')\""
    )

    steps_text = "\n\n".join(steps)
    return (
        f"You are a worktree agent for the agentrelay project.\n\n"
        f"Your role: SPEC WRITER\n\n"
        f"Your task: {task.description}\n\n"
        f"Complete these steps in order:\n\n"
        f"{steps_text}\n\n"
        f"The pixi.toml in the current directory provides the agentrelay package.\n\n"
        f"Do NOT implement any function or method bodies.\n\n"
        f"Then stop.\n"
    )


def _build_merger_prompt(
    reviewed_task: AgentTask,
    pr_url: str,
    history_path: Path,
) -> str:
    """Build instructions for the MERGER agent that reviews a PR before merge."""
    task_id = reviewed_task.id

    docstring_step = ""
    if reviewed_task.role == AgentRole.IMPLEMENTER and reviewed_task.paths.src:
        src_paths_str = " ".join(reviewed_task.paths.src)
        docstring_step = (
            f"3. Docstring integrity check (IMPLEMENTER task):\n"
            f"   For each source file in {src_paths_str}:\n"
            f"   - Verify that docstrings were not materially altered.\n"
            f"   - Additive changes are acceptable (new Examples, Notes, clarifications).\n"
            f"   - NOT acceptable: changed signatures, altered Args/Returns/Raises sections, "
            f"weakened constraints.\n"
            f"   - Quote specific lines from the diff that are acceptable or concerning.\n\n"
        )
        quality_step_num = 4
    else:
        quality_step_num = 3

    return (
        f"You are a merge reviewer for the agentrelay project.\n\n"
        f"Your role: PR REVIEWER / MERGER\n\n"
        f"Your task: Review PR {pr_url} (task {task_id}) before it is merged.\n\n"
        f"Complete these steps in order:\n\n"
        f"1. If {history_path} exists, read it for context from previous merge reviews.\n\n"
        f"2. Run these commands to examine the changes:\n"
        f"       gh pr diff {pr_url}\n"
        f"       gh pr view {pr_url}\n\n"
        f"{docstring_step}"
        f"{quality_step_num}. Briefly assess code quality: "
        f"do the gate-tested files look correct? Any obvious issues?\n\n"
        f"{quality_step_num + 1}. Append your findings to {history_path} in this format:\n"
        f"   ## Review: {task_id} — <ISO timestamp>\n"
        f"   PR: {pr_url}\n"
        f"   Verdict: APPROVED / REJECTED\n"
        f"   Notes: <your findings>\n\n"
        f"   Use `date -Iseconds` for the ISO timestamp. "
        f"Create parent directories if needed.\n\n"
        f"{quality_step_num + 2}. Signal done with your verdict:\n"
        f"   Approved:\n"
        f'       pixi run python -c "from agentrelay import WorktreeTaskRunner; '
        f"r = WorktreeTaskRunner.from_config(); "
        f"r.mark_done('approved')\"\n"
        f"   Rejected (include reason in the note):\n"
        f'       pixi run python -c "from agentrelay import WorktreeTaskRunner; '
        f"r = WorktreeTaskRunner.from_config(); "
        f"r.mark_done('rejected: <reason>')\"\n"
        f"   Always use mark_done, never mark_failed — the verdict is in the done note.\n\n"
        f"Then stop.\n"
    )


def _launch_merger(
    reviewed_task: AgentTask,
    pr_url: str,
    graph: "AgentTaskGraph",
    tmux_session: str,
) -> str:
    """Launch a MERGER agent to review a PR. Returns the tmux pane_id."""
    merger_task_id = f"merger_{reviewed_task.id}"
    merger_signal_dir = (
        graph.target_repo_root
        / ".workflow"
        / graph.name
        / "merge_reviews"
        / reviewed_task.id
    )
    history_path = merge_history_path(graph.name, graph.target_repo_root)

    write_merger_task_context(
        merger_task_id=merger_task_id,
        graph_name=graph.name,
        graph_branch=graph.graph_branch(),
        src=list(reviewed_task.paths.src),
        signal_dir=merger_signal_dir,
    )

    instructions = _build_merger_prompt(
        reviewed_task=reviewed_task,
        pr_url=pr_url,
        history_path=history_path,
    )
    write_instructions(merger_signal_dir, instructions)

    pane_id = launch_agent_in_dir(
        cwd=graph.target_repo_root,
        task_id=merger_task_id,
        tmux_session=tmux_session,
        signal_dir=merger_signal_dir,
        model=graph.model,
    )
    print(f"[graph] wrote merger instructions for {reviewed_task.id}")
    return pane_id


def _build_task_instructions(
    task: AgentTask,
    graph_branch: str,
    effective_attempts: int = DEFAULT_GATE_ATTEMPTS,
    graph: AgentTaskGraph | None = None,
) -> str:
    if task.role == AgentRole.SPEC_WRITER:
        return _build_spec_writer_prompt(task, graph_branch, graph)
    if task.role == AgentRole.TEST_WRITER:
        return _build_test_writer_prompt(task, graph_branch, graph)
    if task.role == AgentRole.TEST_REVIEWER:
        return _build_test_reviewer_prompt(task, graph_branch, graph)
    if task.role == AgentRole.IMPLEMENTER:
        return _build_implementer_prompt(task, graph_branch, graph)
    return _build_generic_instructions(task, graph_branch, effective_attempts, graph)


def _build_generic_instructions(
    task: AgentTask,
    graph_branch: str,
    effective_attempts: int = DEFAULT_GATE_ATTEMPTS,
    graph: AgentTaskGraph | None = None,
) -> str:
    context_note = ""
    if task.dependencies:
        context_note = (
            "Before starting, if the file at $AGENTRELAY_SIGNAL_DIR/context.md "
            "exists, read it — it describes what prerequisite tasks produced.\n\n"
        )

    gate_step = ""
    if task.completion_gate:
        resolved_gate = _resolve_gate(task)
        coverage_hint = ""
        if "coverage_threshold" in task.task_params:
            coverage_hint = (
                f"   Coverage failures: rerun with --cov-report=term-missing to see\n"
                f"   uncovered lines, then add tests targeting those specific gaps.\n\n"
            )
        conditional_review = ""
        if task.review_model and task.review_on_attempt >= 2:
            conditional_review = (
                f"  (Attempt {task.review_on_attempt}+) Before running the gate on attempt "
                f"{task.review_on_attempt} or later, spawn a self-review subagent:\n"
                f'    - Use the Task tool with model="{task.review_model}"\n'
                f"    - Pass it your task description, work done, and any previous gate output\n"
                f"    - Ask it to identify what's failing and suggest fixes\n"
                f"    - Incorporate its feedback before running the gate\n"
            )
        gate_step = (
            f"Before calling mark_done(), you must pass the completion gate.\n"
            f"You have up to {effective_attempts} attempts. Each gate run counts as one attempt.\n\n"
            f"Gate command:\n"
            f"    {resolved_gate}\n\n"
            f"The gate command's exit code is the only accepted truth. If it exits\n"
            f"non-zero, the attempt has failed — regardless of what you observed during\n"
            f"your work session. Do not let prior test runs or your own assessment\n"
            f"override a non-zero gate exit.\n\n"
            f"For each attempt:\n"
            f"{conditional_review}"
            f"1. Run the gate command, saving its output and checking the exit code:\n"
            f'       {resolved_gate} > "$AGENTRELAY_SIGNAL_DIR/gate_last_output.txt" 2>&1\n'
            f"       gate_exit=$?\n"
            f'       cat "$AGENTRELAY_SIGNAL_DIR/gate_last_output.txt"\n'
            f"2. Record the attempt:\n"
            f'       python -c "\\\n'
            f"from agentrelay.worktree_task_runner import WorktreeTaskRunner;\\\n"
            f"WorktreeTaskRunner.from_config().record_gate_attempt(N, PASSED)\\\n"
            f'"\n'
            f"   Replace N with the attempt number (1, 2, ...) and PASSED with True or False.\n"
            f"3. If gate_exit is 0 (passed), proceed to mark_done().\n"
            f"4. If gate_exit is non-zero (failed), diagnose the output, fix the issue, and retry.\n\n"
            f"{coverage_hint}"
            f"After {effective_attempts} failed attempts, call mark_failed() with a summary of what\n"
            f"you tried. The full output of the last gate run is already saved to\n"
            f"$AGENTRELAY_SIGNAL_DIR/gate_last_output.txt.\n"
            f"Do NOT call mark_done() until gate_exit is 0.\n\n"
        )

    review_step = ""
    if task.review_model and task.review_on_attempt <= 1:
        review_step = (
            f"Before running the completion gate, spawn a self-review subagent:\n"
            f'  - Use the Task tool with model="{task.review_model}"\n'
            f"  - Pass it your full task description and the work you've done\n"
            f"  - Ask it to verify correctness, edge cases, and alignment with the description\n"
            f"  - Incorporate any feedback before running the completion gate\n\n"
        )

    short_desc = task.description[:60]
    spec_step = _spec_reading_step(task)
    adr_text = _adr_step(task, graph)
    adr_section = f"2. {adr_text}\n\n" if adr_text else ""
    commit_num = 3 if adr_text else 2
    pr_num = 4 if adr_text else 3
    return (
        f"You are a worktree agent for the agentrelay project.\n\n"
        f"Your task: {task.description}\n\n"
        f"{context_note}"
        f"{review_step}"
        f"Complete these steps in order:\n\n"
        f"{spec_step}"
        f"1. Do the work described in your task.\n\n"
        f"{gate_step}"
        f"{adr_section}"
        f"{commit_num}. Stage, commit, and push:\n"
        f"       git add -A\n"
        f'       git commit -m "{task.id}: {short_desc}"\n'
        f"       git push -u origin HEAD\n\n"
        f"{pr_num}. Create a PR with a meaningful body, capture the URL, and signal completion:\n"
        f'       PR_URL=$(gh pr create --title "{task.id}" --body "$(cat <<\'PRBODY\'\n'
        f"## Summary\n"
        f"<1-3 sentences describing what you did and why>\n\n"
        f"## Files changed\n"
        f"<bullet list of the key files you created or modified>\n"
        f'PRBODY\n)" --base {graph_branch})\n'
        f'       pixi run python -c "from agentrelay import WorktreeTaskRunner; '
        f"r = WorktreeTaskRunner.from_config(); "
        f"r.mark_done('$PR_URL')\"\n\n"
        f"The pixi.toml in the current directory provides the agentrelay package.\n\n"
        f"Then stop — do not do anything else.\n"
    )


def _build_test_writer_prompt(
    task: AgentTask, graph_branch: str, graph: AgentTaskGraph | None = None
) -> str:
    short_desc = task.description[:60]
    spec_step = _spec_reading_step(task)

    if task.paths.test:
        test_paths_str = " ".join(task.paths.test)
        write_step = f"1. Write pytest test files at: {test_paths_str}\n"
    else:
        write_step = (
            f"1. Write a pytest test file covering the described feature. "
            f"Place it at an appropriate path in the target module's test directory.\n"
        )

    if task.paths.src:
        src_paths_str = " ".join(task.paths.src)
        stub_note = (
            f"   The stub module(s) at {src_paths_str} already exist — "
            f"do NOT create or overwrite them. Write test file(s) that import from those stubs.\n"
        )
    else:
        stub_note = ""

    adr_text = _adr_step(task, graph)
    adr_section = f"3. {adr_text}\n\n" if adr_text else ""
    commit_num = 4 if adr_text else 3
    pr_num = 5 if adr_text else 4

    return (
        f"You are a worktree agent for the agentrelay project.\n\n"
        f"Your role: TEST WRITER\n\n"
        f"Your task: {task.description}\n\n"
        f"{spec_step}"
        f"Complete these steps in order:\n\n"
        f"{write_step}"
        f"{stub_note}\n"
        f"2. Verify tests collect without import errors:\n"
        f"       pixi run pytest --collect-only\n\n"
        f"{adr_section}"
        f"{commit_num}. Stage, commit, and push:\n"
        f"       git add -A\n"
        f'       git commit -m "{task.id}: {short_desc}"\n'
        f"       git push -u origin HEAD\n\n"
        f"{pr_num}. Create a PR and signal completion:\n"
        f'       PR_URL=$(gh pr create --title "{task.id}" --body "$(cat <<\'PRBODY\'\n'
        f"## Summary\n"
        f"<1-3 sentences describing the tests written>\n\n"
        f"## Files changed\n"
        f"<bullet list of key files>\n"
        f'PRBODY\n)" --base {graph_branch})\n'
        f'       pixi run python -c "from agentrelay import WorktreeTaskRunner; '
        f"r = WorktreeTaskRunner.from_config(); "
        f"r.mark_done('$PR_URL')\"\n\n"
        f"The pixi.toml in the current directory provides the agentrelay package.\n\n"
        f"Then stop — do not implement the feature.\n"
    )


def _build_test_reviewer_prompt(
    task: AgentTask, graph_branch: str, graph: AgentTaskGraph | None = None
) -> str:
    short_desc = task.description[:60]
    review_file = f"{task.id}.md"
    spec_step = _spec_reading_step(task)
    adr_text = _adr_step(task, graph)
    adr_section = f"4. {adr_text}\n\n" if adr_text else ""
    commit_num = 5 if adr_text else 4
    pr_num = 6 if adr_text else 5
    return (
        f"You are a worktree agent for the agentrelay project.\n\n"
        f"Your role: TEST REVIEWER\n\n"
        f"Your task: {task.description}\n\n"
        f"The test file(s) and stub module from the test-writer task are already "
        f"merged into the graph integration branch and available in your worktree.\n\n"
        f"{spec_step}"
        f"Complete these steps in order:\n\n"
        f"1. Read the test file(s) and stub module.\n\n"
        f"2. Write a review file named {review_file} with the following sections:\n"
        f"   ## Verdict\n"
        f"   APPROVED or CONCERNS\n\n"
        f"   ## Coverage assessment\n"
        f"   Which aspects of the feature are tested; what is missing.\n\n"
        f"   ## Comments\n"
        f"   Specific notes on individual tests or the stub API.\n\n"
        f"3. If the tests are fundamentally broken (import errors, wrong assertions, "
        f"untestable structure), signal failure and stop:\n"
        f'       pixi run python -c "from agentrelay import WorktreeTaskRunner; '
        f"r = WorktreeTaskRunner.from_config(); "
        f"r.mark_failed('Tests are fundamentally broken: <reason>')\"\n\n"
        f"{adr_section}"
        f"{commit_num}. Otherwise stage, commit, and push {review_file}:\n"
        f"       git add {review_file}\n"
        f'       git commit -m "{task.id}: {short_desc}"\n'
        f"       git push -u origin HEAD\n\n"
        f"{pr_num}. Create a PR and signal completion:\n"
        f'       PR_URL=$(gh pr create --title "{task.id}" --body "$(cat <<\'PRBODY\'\n'
        f"## Summary\n"
        f"<verdict and 1-2 sentence summary of the review>\n\n"
        f"## Files changed\n"
        f"- {review_file}\n"
        f'PRBODY\n)" --base {graph_branch})\n'
        f'       pixi run python -c "from agentrelay import WorktreeTaskRunner; '
        f"r = WorktreeTaskRunner.from_config(); "
        f"r.mark_done('$PR_URL')\"\n\n"
        f"The pixi.toml in the current directory provides the agentrelay package.\n\n"
        f"Then stop — do not implement the feature.\n"
    )


def _build_implementer_prompt(
    task: AgentTask, graph_branch: str, graph: AgentTaskGraph | None = None
) -> str:
    short_desc = task.description[:60]
    review_file = task.id.removesuffix("_impl") + "_review.md"
    spec_step = _spec_reading_step(task)

    if task.paths.src:
        src_paths_str = " ".join(task.paths.src)
        impl_step = (
            f"2. Implement the feature by replacing the NotImplementedError stubs in "
            f"{src_paths_str} with working code.\n"
            f"   When implementing, you MUST preserve all existing docstrings in "
            f"{src_paths_str} exactly. You may add Examples or Notes to a docstring "
            f"if they were absent, but do NOT alter the Args, Returns, or Raises sections, "
            f"do NOT change signatures, and do NOT remove or weaken any documented behaviour "
            f"or constraints. The docstrings are the specification contract — they are "
            f"reviewed by a merge agent after you submit your PR.\n"
            f"   Add supporting modules as needed.\n"
        )
    else:
        impl_step = (
            f"2. Implement the feature by replacing the NotImplementedError stubs with "
            f"working code. Add supporting modules as needed.\n"
        )

    if task.paths.test:
        test_paths_str = " ".join(task.paths.test)
        run_tests_step = (
            f"3. Run the tests and fix any failures. Repeat until all tests pass:\n"
            f"       pixi run pytest {test_paths_str}\n"
        )
    else:
        run_tests_step = (
            f"3. Run the tests and fix any failures. Repeat until all tests pass:\n"
            f"       pixi run pytest\n"
        )

    adr_text = _adr_step(task, graph)
    adr_section = f"5. {adr_text}\n\n" if adr_text else ""
    commit_num = 6 if adr_text else 5
    pr_num = 7 if adr_text else 6

    return (
        f"You are a worktree agent for the agentrelay project.\n\n"
        f"Your role: IMPLEMENTER\n\n"
        f"Your task: {task.description}\n\n"
        f"The test file(s), stub module, and review file are already merged into the "
        f"graph integration branch and available in your worktree.\n\n"
        f"{spec_step}"
        f"Complete these steps in order:\n\n"
        f"1. Read the test file(s) and {review_file} to understand what is expected "
        f"and any reviewer feedback.\n\n"
        f"{impl_step}\n"
        f"{run_tests_step}\n"
        f"4. If during implementation you encountered concerns about the spec, tests, or "
        f"architecture — whether or not you succeeded — document each one:\n"
        f'       python -c "from agentrelay import WorktreeTaskRunner; \\\n'
        f"WorktreeTaskRunner.from_config().record_concern('your concern here')\"\n"
        f"   Do this for every distinct concern. If you have no concerns, skip this step.\n\n"
        f"{adr_section}"
        f"{commit_num}. Stage, commit, and push:\n"
        f"       git add -A\n"
        f'       git commit -m "{task.id}: {short_desc}"\n'
        f"       git push -u origin HEAD\n\n"
        f"{pr_num}. Create a PR and signal completion:\n"
        f'       PR_URL=$(gh pr create --title "{task.id}" --body "$(cat <<\'PRBODY\'\n'
        f"## Summary\n"
        f"<1-3 sentences describing the implementation>\n\n"
        f"## Files changed\n"
        f"<bullet list of key files>\n"
        f'PRBODY\n)" --base {graph_branch})\n'
        f'       pixi run python -c "from agentrelay import WorktreeTaskRunner; '
        f"r = WorktreeTaskRunner.from_config(); "
        f"r.mark_done('$PR_URL')\"\n\n"
        f"The pixi.toml in the current directory provides the agentrelay package.\n\n"
        f"Then stop.\n"
    )


async def _run_task(graph: AgentTaskGraph, task: AgentTask) -> None:
    """Run one task end-to-end: create worktree, dispatch agent, merge PR, teardown."""
    agent_index = graph.next_agent_index()
    task.state.agent_index = agent_index
    effective_attempts = (
        task.max_gate_attempts or graph.max_gate_attempts or DEFAULT_GATE_ATTEMPTS
    )
    print(f"[graph] dispatching {task.id}[a{agent_index}]: {task.description[:60]}")
    try:
        create_worktree(task, graph.name, graph.worktrees_root, graph.target_repo_root)
        print(f"[graph] worktree at {task.state.worktree_path}")

        try:
            validate_task_paths(task, task.state.worktree_path)  # type: ignore[arg-type]
        except ValueError as e:
            print(f"[graph] {task.id} path validation failed: {e}")
            task.state.status = TaskStatus.FAILED
            return

        signal_dir = graph.signal_dir(task.id)

        context_content = _build_context_content(task)
        if context_content:
            write_context(signal_dir, context_content)
            print(f"[graph] wrote context.md for {task.id}")

        write_task_context(
            task,
            graph.name,
            graph.target_repo_root,
            graph.graph_branch(),
            agent_index,
            effective_attempts,
        )

        instructions = _build_task_instructions(
            task, graph.graph_branch(), effective_attempts, graph
        )
        write_instructions(signal_dir, instructions)
        print(f"[graph] wrote instructions.md for {task.id}[a{agent_index}]")

        effective_model = task.model or graph.model
        pane_id = launch_agent(
            task, graph.tmux_session, model=effective_model, signal_dir=signal_dir
        )
        print(f"[graph] {task.id}[a{agent_index}] agent pane: {pane_id}")

        send_prompt(pane_id, BOOTSTRAP_PROMPT)
        print(f"[graph] bootstrap prompt sent to {task.id}[a{agent_index}]")

        result = await poll_for_completion(task, graph.name, graph.target_repo_root)
        print(f"[graph] {task.id}[a{agent_index}] sentinel: {result}")

        if result == "done":
            pr_url = read_done_note(task, graph.name, graph.target_repo_root)

            if task.completion_gate:
                gate_passed = run_completion_gate(
                    _resolve_gate(task),
                    task.state.worktree_path,  # type: ignore[arg-type]
                )
                if not gate_passed:
                    print(
                        f"[graph] {task.id}[a{agent_index}] completion gate FAILED: "
                        f"{task.completion_gate}"
                    )
                    if pr_url:
                        save_pr_summary(pr_url, graph.signal_dir(task.id))
                    record_gate_failure(
                        task_id=task.id,
                        pr_url=pr_url or "",
                        gate_cmd=_resolve_gate(task),
                        graph_name=graph.name,
                        target_repo_root=graph.target_repo_root,
                    )
                    task.state.status = TaskStatus.FAILED
                    return
                print(f"[graph] {task.id}[a{agent_index}] completion gate passed")

            concerns = read_design_concerns(signal_dir)
            if concerns:
                print(f"[graph] {task.id} design concerns recorded")
                if pr_url:
                    append_concerns_to_pr(pr_url, concerns)

            if pr_url:
                save_pr_summary(pr_url, graph.signal_dir(task.id))
                pixi_changed = pixi_toml_changed_in_pr(pr_url)
                if pixi_changed:
                    print(
                        f"[graph] pixi.toml changed in {task.id} — neutralizing pixi.lock in branch"
                    )
                    neutralize_pixi_lock_in_pr(task)

                merger_signal_dir = (
                    graph.target_repo_root
                    / ".workflow"
                    / graph.name
                    / "merge_reviews"
                    / task.id
                )
                merger_pane = _launch_merger(task, pr_url, graph, graph.tmux_session)
                send_prompt(merger_pane, BOOTSTRAP_PROMPT)
                print(f"[graph] {task.id} MERGER agent launched in pane {merger_pane}")

                merger_result = await poll_for_completion_at(merger_signal_dir)
                print(
                    f"[graph] {task.id}[a{agent_index}] merger sentinel: {merger_result}"
                )

                verdict = read_done_note_at(merger_signal_dir)
                if not graph.keep_panes:
                    close_pane_by_id(merger_pane)

                if not verdict or not verdict.startswith("approved"):
                    print(f"[graph] {task.id} MERGER rejected: {verdict}")
                    task.state.status = TaskStatus.FAILED
                    return

                print(f"[graph] {task.id} MERGER approved — proceeding with merge")
                print(
                    f"[graph] merging task PR for {task.id} into {graph.graph_branch()}: {pr_url}"
                )
                merge_pr(pr_url)
                write_merged_signal(task, graph.name, graph.target_repo_root)
                print(f"[graph] {task.id} merged into {graph.graph_branch()}")
                if pull_graph_branch(graph.name, graph.target_repo_root):
                    print(
                        f"[graph] {graph.graph_branch()} fast-forwarded after {task.id}"
                    )
                else:
                    print(
                        f"[graph] WARNING: pull of {graph.graph_branch()} failed after {task.id} — "
                        "resolve before dependent tasks start"
                    )
            task.state.status = TaskStatus.DONE
        else:
            print(f"[graph] {task.id} failed")
            task.state.status = TaskStatus.FAILED

    except Exception as e:
        print(f"[graph] ERROR in {task.id}: {e}")
        task.state.status = TaskStatus.FAILED

    finally:
        save_agent_log(task, graph.signal_dir(task.id))
        if not graph.keep_panes:
            close_agent_pane(task)
        if task.state.worktree_path and task.state.branch_name:
            remove_worktree(task, graph.target_repo_root)
        print(f"[graph] teardown complete for {task.id}")

    # Unblock any tasks that were waiting on this one
    graph._refresh_ready()


async def _run_graph_loop(graph: AgentTaskGraph) -> None:
    record_run_start(graph.name, graph.target_repo_root)
    graph.hydrate_from_signals()
    graph._refresh_ready()

    print(f"[graph] creating integration branch {graph.graph_branch()}")
    create_graph_branch(graph.name, graph.target_repo_root)

    running: set[asyncio.Task[None]] = set()

    while not graph.is_complete():
        # Dispatch all newly ready tasks
        for task in graph.ready_tasks():
            task.state.status = TaskStatus.RUNNING
            t: asyncio.Task[None] = asyncio.create_task(_run_task(graph, task))
            running.add(t)
            t.add_done_callback(running.discard)

        if running:
            await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
        elif not graph.is_complete():
            # No running tasks, nothing ready, not done — dependency cycle or all failed
            print(
                "[graph] WARNING: no runnable tasks; possible cycle or all tasks failed"
            )
            break

    # Final status report
    print("\n[graph] === final status ===")
    all_done = True
    for task in graph.tasks.values():
        summary_path = graph.signal_dir(task.id) / "summary.md"
        summary_note = f"  summary → {summary_path}" if summary_path.exists() else ""
        print(
            f"  {task.id}: {task.state.status.value}{('  ' + summary_note) if summary_note else ''}"
        )
        if task.state.status != TaskStatus.DONE:
            all_done = False

    if all_done:
        print(
            f"\n[graph] all tasks done — creating final PR: {graph.graph_branch()} → main"
        )
        write_adr_index_to_graph_branch(
            graph.name, graph.target_repo_root, graph.worktrees_root
        )
        final_pr_url = create_final_pr(graph.name, graph.target_repo_root)
        if final_pr_url:
            print(f"[graph] final PR: {final_pr_url}")
            print(
                f"[graph] merge {final_pr_url} when ready, then run reset_graph to clean up."
            )
    else:
        print(
            f"\n[graph] one or more tasks failed — skipping final PR. "
            f"Review failures and rerun or reset."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run an agentrelay graph from a YAML definition."
    )
    parser.add_argument("graph", help="Path to graph YAML file")
    parser.add_argument(
        "--tmux-session",
        default=None,
        metavar="SESSION",
        help="Override tmux session name (default: value from YAML or 'agentrelay')",
    )
    parser.add_argument(
        "--keep-panes",
        action="store_true",
        help="Leave agent tmux windows open after tasks complete (useful for debugging)",
    )
    args = parser.parse_args()

    graph_path = Path(args.graph)
    if not graph_path.is_absolute():
        graph_path = Path.cwd() / graph_path

    repo_root = Path.cwd()
    print(f"[graph] loading graph from {graph_path}")

    graph = AgentTaskGraphBuilder.from_yaml(graph_path, repo_root)
    if args.tmux_session:
        graph.tmux_session = args.tmux_session
    if args.keep_panes:
        graph.keep_panes = True
    print(
        f"[graph] loaded '{graph.name}' with {len(graph.tasks)} task(s): {list(graph.tasks)}"
    )
    print(f"[graph] target repo: {graph.target_repo_root}")
    print(f"[graph] worktrees root: {graph.worktrees_root}")
    print(f"[graph] integration branch: {graph.graph_branch()}")
    print(f"[graph] tmux session: {graph.tmux_session}")
    print(f"[graph] keep panes: {graph.keep_panes}")

    asyncio.run(_run_graph_loop(graph))


if __name__ == "__main__":
    main()
