import asyncio
import json
import subprocess
import time
from pathlib import Path

from agentrelaysmall.agent_task import AgentTask


def create_worktree(
    task: AgentTask,
    graph_name: str,
    worktrees_root: Path,
    base_branch: str = "main",
) -> Path:
    worktree_path = worktrees_root / graph_name / task.id
    branch_name = f"task/{graph_name}/{task.id}"
    subprocess.run(
        ["git", "worktree", "add", "-b", branch_name, str(worktree_path), base_branch],
        check=True,
    )
    task.state.worktree_path = worktree_path
    task.state.branch_name = branch_name
    return worktree_path


def write_task_context(task: AgentTask, graph_name: str, repo_root: Path) -> None:
    signal_dir = repo_root / ".workflow" / graph_name / "signals" / task.id
    context = {
        "task_id": task.id,
        "graph_name": graph_name,
        "signal_dir": str(signal_dir),
    }
    assert task.state.worktree_path is not None, "worktree_path must be set before writing context"
    (task.state.worktree_path / "task_context.json").write_text(
        json.dumps(context, indent=2)
    )


def launch_agent(task: AgentTask, tmux_session: str) -> str:
    assert task.state.worktree_path is not None, "worktree_path must be set before launching agent"
    pane_id = (
        subprocess.check_output(
            [
                "tmux", "new-window",
                "-t", tmux_session,
                "-n", task.id,
                "-P", "-F", "#{pane_id}",
                "-c", str(task.state.worktree_path),
            ]
        )
        .decode()
        .strip()
    )
    task.state.tmux_session = tmux_session
    task.state.pane_id = pane_id
    subprocess.run(["tmux", "send-keys", "-t", pane_id, "claude", "Enter"])
    return pane_id


def send_prompt(pane_id: str, prompt: str, startup_delay: float = 5.0) -> None:
    time.sleep(startup_delay)
    subprocess.run(["tmux", "send-keys", "-t", pane_id, prompt, "Enter"])


def remove_worktree(task: AgentTask) -> None:
    assert task.state.worktree_path is not None, "worktree_path must be set before removing"
    assert task.state.branch_name is not None, "branch_name must be set before removing"
    subprocess.run(
        ["git", "worktree", "remove", str(task.state.worktree_path)],
        check=True,
    )
    subprocess.run(
        ["git", "branch", "-d", task.state.branch_name],
        check=True,
    )


async def poll_for_completion(
    task: AgentTask,
    graph_name: str,
    repo_root: Path,
    poll_interval: float = 2.0,
) -> str:
    signal_dir = repo_root / ".workflow" / graph_name / "signals" / task.id
    while True:
        if (signal_dir / ".done").exists():
            return "done"
        if (signal_dir / ".failed").exists():
            return "failed"
        await asyncio.sleep(poll_interval)
