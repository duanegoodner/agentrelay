"""
Demo driver: runs a single hardcoded AgentTask end-to-end.

Usage (from repo root, with pixi env active):
    python -m agentrelay.run_demo

Requires:
    - A tmux session named 'agentrelay' already running
    - git repo at REPO_ROOT with a 'main' branch
    - claude CLI available in PATH
"""

import asyncio
from pathlib import Path

from agentrelay.archive.agent_task import AgentTask
from agentrelay.archive.task_launcher import (
    close_agent_pane,
    create_worktree,
    launch_agent,
    merge_pr,
    poll_for_completion,
    pull_main,
    read_done_note,
    remove_worktree,
    send_prompt,
    write_merged_signal,
    write_task_context,
)

TMUX_SESSION = "agentrelay"
GRAPH_NAME = "demo"
REPO_ROOT = (
    Path(__file__).resolve().parents[2]
)  # src/agentrelay/run_demo.py → repo root
WORKTREES_ROOT = REPO_ROOT.parent / "worktrees"


TASK_ID = "task_006"


def build_task_prompt(task_id: str) -> str:
    output_path = f"demo_output/{task_id}/hello.py"
    return f"""\
You are a worktree agent for the agentrelay project.

Complete these steps in order:

1. Create the directory `demo_output/{task_id}` and write `hello.py` inside it,
   containing exactly one line:
       print("hello from agentrelay")

2. Stage, commit, and push the file:
       git add {output_path}
       git commit -m "Add {output_path}"
       git push -u origin HEAD

3. Create a PR, capture the URL, and signal completion — run these two commands:
       PR_URL=$(gh pr create --title "Add {output_path}" --body "Automated demo task." --base main)
       pixi run python -c "from agentrelay import WorktreeTaskRunner; r = WorktreeTaskRunner.from_config(); r.mark_done('$PR_URL')"

The pixi.toml in the current directory provides the agentrelay package.

Then stop — do not do anything else.
"""


async def main() -> None:
    task = AgentTask(id=TASK_ID, description="Write hello.py and signal done")
    task_prompt = build_task_prompt(task.id)

    print(f"[demo] repo root: {REPO_ROOT}")
    print(f"[demo] worktrees root: {WORKTREES_ROOT}")

    # 1. Create worktree
    print(f"[demo] creating worktree for {task.id}...")
    create_worktree(task, GRAPH_NAME, WORKTREES_ROOT, REPO_ROOT)
    print(f"[demo] worktree at {task.state.worktree_path}")

    # 2. Write task_context.json so WorktreeTaskRunner can initialise
    graph_branch = f"graph/{GRAPH_NAME}"
    write_task_context(task, GRAPH_NAME, REPO_ROOT, graph_branch, 0, 5)
    print("[demo] wrote task_context.json")

    # 3. Launch Claude Code in a tmux window
    signal_dir = REPO_ROOT / ".workflow" / GRAPH_NAME / "signals" / task.id
    print(f"[demo] launching agent in tmux session '{TMUX_SESSION}'...")
    pane_id = launch_agent(task, TMUX_SESSION, signal_dir=signal_dir)
    print(f"[demo] agent pane: {pane_id}")

    # 4. Send the task prompt (waits for Claude to initialise first)
    print("[demo] sending prompt (waiting for Claude to start)...")
    send_prompt(pane_id, task_prompt)
    print("[demo] prompt sent")

    # 5. Poll for completion
    print("[demo] polling for sentinel...")
    result = await poll_for_completion(task, GRAPH_NAME, REPO_ROOT)
    print(f"[demo] sentinel detected: {result}")

    # 6. Merge the PR (if the agent noted a PR URL in the .done file)
    if result == "done":
        pr_url = read_done_note(task, GRAPH_NAME, REPO_ROOT)
        if pr_url:
            print(f"[demo] merging PR: {pr_url}")
            merge_pr(pr_url)
            write_merged_signal(task, GRAPH_NAME, REPO_ROOT)
            print("[demo] PR merged and .merged signal written")
            if pull_main(REPO_ROOT):
                print("[demo] local main fast-forwarded to origin/main")
            else:
                print(
                    "[demo] WARNING: git pull --ff-only failed — local main is stale. "
                    "Resolve before starting the next task."
                )
        else:
            print("[demo] no PR URL in .done note — skipping merge")

    # 7. Teardown
    print("[demo] closing agent pane and removing worktree...")
    close_agent_pane(task)
    remove_worktree(task, REPO_ROOT)
    print("[demo] done")


if __name__ == "__main__":
    asyncio.run(main())
