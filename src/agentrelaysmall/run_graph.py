"""Graph orchestrator: drives multiple AgentTasks based on a YAML graph definition.

Usage (from repo root, with pixi env active):
    python -m agentrelaysmall.run_graph graphs/demo.yaml
    python -m agentrelaysmall.run_graph graphs/demo.yaml --tmux-session myproject
    python -m agentrelaysmall.run_graph graphs/demo.yaml --keep-panes

Requires:
    - A tmux session already running (default name: 'agentrelaysmall', or set via
      --tmux-session or the 'tmux_session' key in the graph YAML)
    - git repo at repo root with a 'main' branch
    - claude CLI available in PATH
"""

import argparse
import asyncio
from pathlib import Path

from agentrelaysmall.agent_task import AgentRole, AgentTask, TaskStatus
from agentrelaysmall.agent_task_graph import AgentTaskGraph, AgentTaskGraphBuilder
from agentrelaysmall.task_launcher import (
    close_agent_pane,
    create_final_pr,
    create_graph_branch,
    create_worktree,
    launch_agent,
    merge_pr,
    neutralize_pixi_lock_in_pr,
    pixi_toml_changed_in_pr,
    poll_for_completion,
    pull_graph_branch,
    read_done_note,
    record_run_start,
    remove_worktree,
    run_completion_gate,
    save_agent_log,
    save_pr_summary,
    send_prompt,
    write_context,
    write_instructions,
    write_merged_signal,
    write_task_context,
)

BOOTSTRAP_PROMPT = (
    "Read $AGENTRELAY_SIGNAL_DIR/instructions.md and follow the steps exactly."
)

DEFAULT_GATE_ATTEMPTS = 5


def _effective_verbosity(task: AgentTask, graph: AgentTaskGraph) -> str:
    """Return effective verbosity for a task, inheriting from graph if task is unset."""
    return task.verbosity or graph.verbosity or "standard"


def _spec_reading_step(task: AgentTask) -> str:
    """Return a spec-reading preamble if the task has src_paths or spec_path."""
    if not task.src_paths and not task.spec_path:
        return ""
    parts = ["Before starting, read the following to understand the API contract:\n"]
    if task.src_paths:
        paths_str = " ".join(task.src_paths)
        parts.append(
            f"  Source stubs (docstrings are the authoritative spec): {paths_str}\n"
        )
    if task.spec_path:
        parts.append(f"  Supplementary spec file: {task.spec_path}\n")
    parts.append("\n")
    return "".join(parts)


def validate_task_paths(task: AgentTask, worktree_path: Path) -> None:
    """Validate that expected files/dirs exist in the worktree before agent launch.

    Raises ValueError with a descriptive message if any required path is missing.
    MERGER and GENERIC roles are not validated.
    """
    role = task.role
    if role == AgentRole.SPEC_WRITER:
        for src_path in task.src_paths:
            parent = (worktree_path / src_path).parent
            if not parent.exists():
                raise ValueError(
                    f"[validate] {task.id}: expected parent directory "
                    f"'{src_path}' parent in worktree but not found"
                )
        if task.spec_path:
            parent = (worktree_path / task.spec_path).parent
            if not parent.exists():
                raise ValueError(
                    f"[validate] {task.id}: expected parent directory for "
                    f"spec_path '{task.spec_path}' in worktree but not found"
                )
    elif role == AgentRole.TEST_WRITER:
        for src_path in task.src_paths:
            full_path = worktree_path / src_path
            if not full_path.exists():
                raise ValueError(
                    f"[validate] {task.id}: expected src_path '{src_path}' "
                    f"in worktree but not found"
                )
        for test_path in task.test_paths:
            parent = (worktree_path / test_path).parent
            if not parent.exists():
                raise ValueError(
                    f"[validate] {task.id}: expected parent directory for "
                    f"test_path '{test_path}' in worktree but not found"
                )
    elif role == AgentRole.IMPLEMENTER:
        for src_path in task.src_paths:
            full_path = worktree_path / src_path
            if not full_path.exists():
                raise ValueError(
                    f"[validate] {task.id}: expected src_path '{src_path}' "
                    f"in worktree but not found"
                )
        for test_path in task.test_paths:
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


def _build_spec_writer_prompt(task: AgentTask, graph_branch: str) -> str:
    short_desc = task.description[:60]
    src_paths_str = " ".join(task.src_paths) if task.src_paths else "(see description)"

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
    if task.spec_path:
        steps.append(
            f"{step_num}. Write a brief spec file at {task.spec_path} that serves as a "
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

    all_paths = list(task.src_paths)
    if task.spec_path:
        all_paths.append(task.spec_path)
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
        f'       pixi run python -c "from agentrelaysmall import WorktreeTaskRunner; '
        f"r = WorktreeTaskRunner.from_config(); "
        f"r.mark_done('$PR_URL')\""
    )

    steps_text = "\n\n".join(steps)
    return (
        f"You are a worktree agent for the agentrelaysmall project.\n\n"
        f"Your role: SPEC WRITER\n\n"
        f"Your task: {task.description}\n\n"
        f"Complete these steps in order:\n\n"
        f"{steps_text}\n\n"
        f"The pixi.toml in the current directory provides the agentrelaysmall package.\n\n"
        f"Do NOT implement any function or method bodies.\n\n"
        f"Then stop.\n"
    )


def _build_task_instructions(
    task: AgentTask, graph_branch: str, effective_attempts: int = DEFAULT_GATE_ATTEMPTS
) -> str:
    if task.role == AgentRole.SPEC_WRITER:
        return _build_spec_writer_prompt(task, graph_branch)
    if task.role == AgentRole.TEST_WRITER:
        return _build_test_writer_prompt(task, graph_branch)
    if task.role == AgentRole.TEST_REVIEWER:
        return _build_test_reviewer_prompt(task, graph_branch)
    if task.role == AgentRole.IMPLEMENTER:
        return _build_implementer_prompt(task, graph_branch)
    return _build_generic_instructions(task, graph_branch, effective_attempts)


def _build_generic_instructions(
    task: AgentTask, graph_branch: str, effective_attempts: int = DEFAULT_GATE_ATTEMPTS
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
            f"from agentrelaysmall.worktree_task_runner import WorktreeTaskRunner;\\\n"
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
    return (
        f"You are a worktree agent for the agentrelaysmall project.\n\n"
        f"Your task: {task.description}\n\n"
        f"{context_note}"
        f"{review_step}"
        f"Complete these steps in order:\n\n"
        f"{spec_step}"
        f"1. Do the work described in your task.\n\n"
        f"{gate_step}"
        f"2. Stage, commit, and push:\n"
        f"       git add -A\n"
        f'       git commit -m "{task.id}: {short_desc}"\n'
        f"       git push -u origin HEAD\n\n"
        f"3. Create a PR with a meaningful body, capture the URL, and signal completion:\n"
        f'       PR_URL=$(gh pr create --title "{task.id}" --body "$(cat <<\'PRBODY\'\n'
        f"## Summary\n"
        f"<1-3 sentences describing what you did and why>\n\n"
        f"## Files changed\n"
        f"<bullet list of the key files you created or modified>\n"
        f'PRBODY\n)" --base {graph_branch})\n'
        f'       pixi run python -c "from agentrelaysmall import WorktreeTaskRunner; '
        f"r = WorktreeTaskRunner.from_config(); "
        f"r.mark_done('$PR_URL')\"\n\n"
        f"The pixi.toml in the current directory provides the agentrelaysmall package.\n\n"
        f"Then stop — do not do anything else.\n"
    )


def _build_test_writer_prompt(task: AgentTask, graph_branch: str) -> str:
    short_desc = task.description[:60]
    spec_step = _spec_reading_step(task)

    if task.test_paths:
        test_paths_str = " ".join(task.test_paths)
        write_step = f"1. Write pytest test files at: {test_paths_str}\n"
    else:
        write_step = (
            f"1. Write a pytest test file covering the described feature. "
            f"Place it at an appropriate path in the target module's test directory.\n"
        )

    if task.src_paths:
        src_paths_str = " ".join(task.src_paths)
        stub_note = (
            f"   The stub module(s) at {src_paths_str} already exist — "
            f"do NOT create or overwrite them. Write test file(s) that import from those stubs.\n"
        )
    else:
        stub_note = ""

    return (
        f"You are a worktree agent for the agentrelaysmall project.\n\n"
        f"Your role: TEST WRITER\n\n"
        f"Your task: {task.description}\n\n"
        f"{spec_step}"
        f"Complete these steps in order:\n\n"
        f"{write_step}"
        f"{stub_note}\n"
        f"2. Verify tests collect without import errors:\n"
        f"       pixi run pytest --collect-only\n\n"
        f"3. Stage, commit, and push:\n"
        f"       git add -A\n"
        f'       git commit -m "{task.id}: {short_desc}"\n'
        f"       git push -u origin HEAD\n\n"
        f"4. Create a PR and signal completion:\n"
        f'       PR_URL=$(gh pr create --title "{task.id}" --body "$(cat <<\'PRBODY\'\n'
        f"## Summary\n"
        f"<1-3 sentences describing the tests written>\n\n"
        f"## Files changed\n"
        f"<bullet list of key files>\n"
        f'PRBODY\n)" --base {graph_branch})\n'
        f'       pixi run python -c "from agentrelaysmall import WorktreeTaskRunner; '
        f"r = WorktreeTaskRunner.from_config(); "
        f"r.mark_done('$PR_URL')\"\n\n"
        f"The pixi.toml in the current directory provides the agentrelaysmall package.\n\n"
        f"Then stop — do not implement the feature.\n"
    )


def _build_test_reviewer_prompt(task: AgentTask, graph_branch: str) -> str:
    short_desc = task.description[:60]
    review_file = f"{task.id}.md"
    spec_step = _spec_reading_step(task)
    return (
        f"You are a worktree agent for the agentrelaysmall project.\n\n"
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
        f'       pixi run python -c "from agentrelaysmall import WorktreeTaskRunner; '
        f"r = WorktreeTaskRunner.from_config(); "
        f"r.mark_failed('Tests are fundamentally broken: <reason>')\"\n\n"
        f"4. Otherwise stage, commit, and push {review_file}:\n"
        f"       git add {review_file}\n"
        f'       git commit -m "{task.id}: {short_desc}"\n'
        f"       git push -u origin HEAD\n\n"
        f"5. Create a PR and signal completion:\n"
        f'       PR_URL=$(gh pr create --title "{task.id}" --body "$(cat <<\'PRBODY\'\n'
        f"## Summary\n"
        f"<verdict and 1-2 sentence summary of the review>\n\n"
        f"## Files changed\n"
        f"- {review_file}\n"
        f'PRBODY\n)" --base {graph_branch})\n'
        f'       pixi run python -c "from agentrelaysmall import WorktreeTaskRunner; '
        f"r = WorktreeTaskRunner.from_config(); "
        f"r.mark_done('$PR_URL')\"\n\n"
        f"The pixi.toml in the current directory provides the agentrelaysmall package.\n\n"
        f"Then stop — do not implement the feature.\n"
    )


def _build_implementer_prompt(task: AgentTask, graph_branch: str) -> str:
    short_desc = task.description[:60]
    review_file = task.id.removesuffix("_impl") + "_review.md"
    spec_step = _spec_reading_step(task)

    if task.src_paths:
        src_paths_str = " ".join(task.src_paths)
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

    if task.test_paths:
        test_paths_str = " ".join(task.test_paths)
        run_tests_step = (
            f"3. Run the tests and fix any failures. Repeat until all tests pass:\n"
            f"       pixi run pytest {test_paths_str}\n"
        )
    else:
        run_tests_step = (
            f"3. Run the tests and fix any failures. Repeat until all tests pass:\n"
            f"       pixi run pytest\n"
        )

    return (
        f"You are a worktree agent for the agentrelaysmall project.\n\n"
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
        f"4. Stage, commit, and push:\n"
        f"       git add -A\n"
        f'       git commit -m "{task.id}: {short_desc}"\n'
        f"       git push -u origin HEAD\n\n"
        f"5. Create a PR and signal completion:\n"
        f'       PR_URL=$(gh pr create --title "{task.id}" --body "$(cat <<\'PRBODY\'\n'
        f"## Summary\n"
        f"<1-3 sentences describing the implementation>\n\n"
        f"## Files changed\n"
        f"<bullet list of key files>\n"
        f'PRBODY\n)" --base {graph_branch})\n'
        f'       pixi run python -c "from agentrelaysmall import WorktreeTaskRunner; '
        f"r = WorktreeTaskRunner.from_config(); "
        f"r.mark_done('$PR_URL')\"\n\n"
        f"The pixi.toml in the current directory provides the agentrelaysmall package.\n\n"
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
            task, graph.graph_branch(), effective_attempts
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
                    task.state.status = TaskStatus.FAILED
                    return
                print(f"[graph] {task.id}[a{agent_index}] completion gate passed")

            pr_url = read_done_note(task, graph.name, graph.target_repo_root)
            if pr_url:
                pixi_changed = pixi_toml_changed_in_pr(pr_url)
                if pixi_changed:
                    print(
                        f"[graph] pixi.toml changed in {task.id} — neutralizing pixi.lock in branch"
                    )
                    neutralize_pixi_lock_in_pr(task)
                print(
                    f"[graph] merging task PR for {task.id} into {graph.graph_branch()}: {pr_url}"
                )
                save_pr_summary(pr_url, graph.signal_dir(task.id))
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
        description="Run an agentrelaysmall graph from a YAML definition."
    )
    parser.add_argument("graph", help="Path to graph YAML file")
    parser.add_argument(
        "--tmux-session",
        default=None,
        metavar="SESSION",
        help="Override tmux session name (default: value from YAML or 'agentrelaysmall')",
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
