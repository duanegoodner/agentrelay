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
    save_agent_log,
    save_pr_summary,
    send_prompt,
    write_context,
    write_merged_signal,
    write_task_context,
)


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


def _build_task_prompt(task: AgentTask, graph_branch: str) -> str:
    if task.role == AgentRole.TEST_WRITER:
        return _build_test_writer_prompt(task, graph_branch)
    if task.role == AgentRole.TEST_REVIEWER:
        return _build_test_reviewer_prompt(task, graph_branch)
    if task.role == AgentRole.IMPLEMENTER:
        return _build_implementer_prompt(task, graph_branch)
    return _build_generic_prompt(task, graph_branch)


def _build_generic_prompt(task: AgentTask, graph_branch: str) -> str:
    context_note = ""
    if task.dependencies:
        context_note = (
            "Before starting, read your context file to understand what "
            "prerequisite tasks produced:\n"
            '    pixi run python -c "'
            "from agentrelaysmall import WorktreeTaskRunner; "
            "r = WorktreeTaskRunner.from_config(); "
            "ctx = r.get_context(); "
            'print(ctx if ctx else "No context")'
            '"\n\n'
        )

    short_desc = task.description[:60]
    return (
        f"You are a worktree agent for the agentrelaysmall project.\n\n"
        f"Your task: {task.description}\n\n"
        f"{context_note}"
        f"Complete these steps in order:\n\n"
        f"1. Do the work described in your task.\n\n"
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
    return (
        f"You are a worktree agent for the agentrelaysmall project.\n\n"
        f"Your role: TEST WRITER\n\n"
        f"Your task: {task.description}\n\n"
        f"Complete these steps in order:\n\n"
        f"1. Write a pytest test file covering the described feature. "
        f"Place it at an appropriate path in the target module's test directory.\n\n"
        f"2. Write a stub module — function/class signatures only, "
        f"all bodies must raise NotImplementedError. "
        f"The stub must provide enough API surface for the tests to import "
        f"and be collected. Do NOT implement the feature.\n\n"
        f"3. Verify tests collect without import errors:\n"
        f"       pixi run pytest --collect-only\n\n"
        f"4. Stage, commit, and push:\n"
        f"       git add -A\n"
        f'       git commit -m "{task.id}: {short_desc}"\n'
        f"       git push -u origin HEAD\n\n"
        f"5. Create a PR and signal completion:\n"
        f'       PR_URL=$(gh pr create --title "{task.id}" --body "$(cat <<\'PRBODY\'\n'
        f"## Summary\n"
        f"<1-3 sentences describing the tests written and stub created>\n\n"
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
    return (
        f"You are a worktree agent for the agentrelaysmall project.\n\n"
        f"Your role: TEST REVIEWER\n\n"
        f"Your task: {task.description}\n\n"
        f"The test file(s) and stub module from the test-writer task are already "
        f"merged into the graph integration branch and available in your worktree.\n\n"
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
    return (
        f"You are a worktree agent for the agentrelaysmall project.\n\n"
        f"Your role: IMPLEMENTER\n\n"
        f"Your task: {task.description}\n\n"
        f"The test file(s), stub module, and review file are already merged into the "
        f"graph integration branch and available in your worktree.\n\n"
        f"Complete these steps in order:\n\n"
        f"1. Read the test file(s) and {review_file} to understand what is expected "
        f"and any reviewer feedback.\n\n"
        f"2. Implement the feature by replacing the NotImplementedError stubs with "
        f"working code. Add supporting modules as needed.\n\n"
        f"3. Run the tests and fix any failures. Repeat until all tests pass:\n"
        f"       pixi run pytest\n\n"
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
    print(f"[graph] dispatching {task.id}: {task.description[:60]}")
    try:
        create_worktree(task, graph.name, graph.worktrees_root, graph.target_repo_root)
        print(f"[graph] worktree at {task.state.worktree_path}")

        signal_dir = graph.signal_dir(task.id)

        context_content = _build_context_content(task)
        if context_content:
            write_context(signal_dir, context_content)
            print(f"[graph] wrote context.md for {task.id}")

        write_task_context(task, graph.name, graph.target_repo_root)

        effective_model = task.model or graph.model
        pane_id = launch_agent(
            task, graph.tmux_session, model=effective_model, signal_dir=signal_dir
        )
        print(f"[graph] {task.id} agent pane: {pane_id}")

        send_prompt(pane_id, _build_task_prompt(task, graph.graph_branch()))
        print(f"[graph] prompt sent to {task.id}")

        result = await poll_for_completion(task, graph.name, graph.target_repo_root)
        print(f"[graph] {task.id} sentinel: {result}")

        if result == "done":
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
