"""
Demo driver: runs a single hardcoded AgentTask end-to-end.

Usage (from repo root, with pixi env active):
    python -m agentrelaysmall.run_demo

Requires:
    - A tmux session named 'agentrelaysmall' already running
    - git repo at REPO_ROOT with a 'main' branch
    - claude CLI available in PATH
"""

import asyncio
from pathlib import Path

from agentrelaysmall.agent_task import AgentTask
from agentrelaysmall.task_launcher import (
    create_worktree,
    launch_agent,
    poll_for_completion,
    remove_worktree,
    send_prompt,
    write_task_context,
)

TMUX_SESSION = "agentrelaysmall"
GRAPH_NAME = "demo"
REPO_ROOT = Path(__file__).resolve().parents[3]   # src/agentrelaysmall/run_demo.py → repo root
WORKTREES_ROOT = REPO_ROOT.parent / "worktrees"


TASK_PROMPT = """\
You are a worktree agent for the agentrelaysmall project.

Your task: write a file called `hello.py` in the current directory containing
exactly one line:  print("hello from agentrelaysmall")

When done, signal completion by running this Python snippet:
    from agentrelaysmall import WorktreeTaskRunner
    runner = WorktreeTaskRunner.from_config()
    runner.mark_done("wrote hello.py")

Then stop — do not do anything else.
"""


async def main() -> None:
    task = AgentTask(id="task_001", description="Write hello.py and signal done")

    print(f"[demo] repo root: {REPO_ROOT}")
    print(f"[demo] worktrees root: {WORKTREES_ROOT}")

    # 1. Create worktree
    print(f"[demo] creating worktree for {task.id}...")
    create_worktree(task, GRAPH_NAME, WORKTREES_ROOT)
    print(f"[demo] worktree at {task.state.worktree_path}")

    # 2. Write task_context.json so WorktreeTaskRunner can initialise
    write_task_context(task, GRAPH_NAME, REPO_ROOT)
    print("[demo] wrote task_context.json")

    # 3. Launch Claude Code in a tmux window
    print(f"[demo] launching agent in tmux session '{TMUX_SESSION}'...")
    pane_id = launch_agent(task, TMUX_SESSION)
    print(f"[demo] agent pane: {pane_id}")

    # 4. Send the task prompt (waits for Claude to initialise first)
    print("[demo] sending prompt (waiting for Claude to start)...")
    send_prompt(pane_id, TASK_PROMPT)
    print("[demo] prompt sent")

    # 5. Poll for completion
    print("[demo] polling for sentinel...")
    result = await poll_for_completion(task, GRAPH_NAME, REPO_ROOT)
    print(f"[demo] sentinel detected: {result}")

    # 6. Teardown
    print("[demo] removing worktree and branch...")
    remove_worktree(task)
    print("[demo] done")


if __name__ == "__main__":
    asyncio.run(main())
