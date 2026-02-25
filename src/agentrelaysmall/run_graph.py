"""Graph orchestrator: drives multiple AgentTasks based on a YAML graph definition.

Usage (from repo root, with pixi env active):
    python -m agentrelaysmall.run_graph graphs/demo.yaml

Requires:
    - A tmux session named 'agentrelaysmall' already running
    - git repo at repo root with a 'main' branch
    - claude CLI available in PATH
"""

import asyncio
import sys
from pathlib import Path

from agentrelaysmall.agent_task import AgentTask, TaskStatus
from agentrelaysmall.agent_task_graph import AgentTaskGraph, AgentTaskGraphBuilder
from agentrelaysmall.task_launcher import (
    close_agent_pane,
    create_worktree,
    launch_agent,
    merge_pr,
    pixi_toml_changed_in_pr,
    poll_for_completion,
    pull_main,
    read_done_note,
    remove_worktree,
    run_pixi_install,
    save_agent_log,
    send_prompt,
    write_context,
    write_merged_signal,
    write_task_context,
)

TMUX_SESSION = "agentrelaysmall"
REPO_ROOT = Path(__file__).resolve().parents[2]   # src/agentrelaysmall/run_graph.py → repo root
WORKTREES_ROOT = REPO_ROOT.parent / "worktrees"


def _build_context_content(graph: AgentTaskGraph, task: AgentTask) -> str | None:
    """Produce context.md content summarising completed dependency tasks."""
    if not task.dependencies:
        return None
    lines = ["# Context from prerequisite tasks\n"]
    for dep_id in task.dependencies:
        dep = graph.tasks[dep_id]
        lines.append(f"## {dep_id}\n")
        lines.append(f"Description: {dep.description}\n")
        lines.append(
            f"The files produced by this task are available in your worktree "
            f"(already merged into main before your branch was created).\n"
        )
    return "\n".join(lines)


def _build_task_prompt(task: AgentTask) -> str:
    context_note = ""
    if task.dependencies:
        context_note = (
            "Before starting, read your context file to understand what "
            "prerequisite tasks produced:\n"
            "    pixi run python -c \""
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
        f"3. Create a PR, capture the URL, and signal completion:\n"
        f'       PR_URL=$(gh pr create --title "{task.id}" --body "Automated task." --base main)\n'
        f'       pixi run python -c "from agentrelaysmall import WorktreeTaskRunner; '
        f"r = WorktreeTaskRunner.from_config(); "
        f'r.mark_done(\'$PR_URL\')"\n\n'
        f"The pixi.toml in the current directory provides the agentrelaysmall package.\n\n"
        f"Then stop — do not do anything else.\n"
    )


async def _run_task(graph: AgentTaskGraph, task: AgentTask) -> None:
    """Run one task end-to-end: create worktree, dispatch agent, merge PR, teardown."""
    print(f"[graph] dispatching {task.id}: {task.description[:60]}")
    try:
        create_worktree(task, graph.name, graph.worktrees_root, graph.target_repo_root)
        print(f"[graph] worktree at {task.state.worktree_path}")

        context_content = _build_context_content(graph, task)
        if context_content:
            write_context(task, context_content)
            print(f"[graph] wrote context.md for {task.id}")

        write_task_context(task, graph.name, graph.target_repo_root)

        pane_id = launch_agent(task, TMUX_SESSION)
        print(f"[graph] {task.id} agent pane: {pane_id}")

        send_prompt(pane_id, _build_task_prompt(task))
        print(f"[graph] prompt sent to {task.id}")

        result = await poll_for_completion(task, graph.name, graph.target_repo_root)
        print(f"[graph] {task.id} sentinel: {result}")

        if result == "done":
            pr_url = read_done_note(task, graph.name, graph.target_repo_root)
            if pr_url:
                print(f"[graph] merging PR for {task.id}: {pr_url}")
                merge_pr(pr_url)
                write_merged_signal(task, graph.name, graph.target_repo_root)
                print(f"[graph] {task.id} merged")
                if pull_main(graph.target_repo_root):
                    print(f"[graph] main fast-forwarded after {task.id}")
                    if pixi_toml_changed_in_pr(pr_url):
                        print(f"[graph] WARNING: pixi.toml changed in {task.id} — running pixi install")
                        if run_pixi_install(graph.target_repo_root):
                            print(f"[graph] pixi install succeeded")
                        else:
                            print(f"[graph] ERROR: pixi install failed — env may be out of sync")
                else:
                    print(
                        f"[graph] WARNING: pull --ff-only failed after {task.id} — "
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
        close_agent_pane(task)
        if task.state.worktree_path and task.state.branch_name:
            remove_worktree(task, graph.target_repo_root)
        print(f"[graph] teardown complete for {task.id}")

    # Unblock any tasks that were waiting on this one
    graph._refresh_ready()


async def _run_graph_loop(graph: AgentTaskGraph) -> None:
    graph.hydrate_from_signals()
    graph._refresh_ready()

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
            print("[graph] WARNING: no runnable tasks; possible cycle or all tasks failed")
            break

    # Final status report
    print("\n[graph] === final status ===")
    for task in graph.tasks.values():
        print(f"  {task.id}: {task.state.status.value}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m agentrelaysmall.run_graph <graph.yaml>")
        sys.exit(1)

    graph_path = Path(sys.argv[1])
    if not graph_path.is_absolute():
        graph_path = Path.cwd() / graph_path

    print(f"[graph] loading graph from {graph_path}")
    print(f"[graph] repo root: {REPO_ROOT}")
    print(f"[graph] worktrees root: {WORKTREES_ROOT}")

    graph = AgentTaskGraphBuilder.from_yaml(graph_path, REPO_ROOT, WORKTREES_ROOT)
    print(f"[graph] loaded '{graph.name}' with {len(graph.tasks)} task(s): {list(graph.tasks)}")

    asyncio.run(_run_graph_loop(graph))


if __name__ == "__main__":
    main()
