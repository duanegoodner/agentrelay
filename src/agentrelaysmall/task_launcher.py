import asyncio
import json
import os
import subprocess
import time
from datetime import datetime, timezone
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
    # Export the orchestrator's PATH so Claude's bash subshells can find
    # tools (gh, pixi, etc.) that live outside the default non-interactive PATH
    env_path = os.environ.get("PATH", "")
    subprocess.run([
        "tmux", "send-keys", "-t", pane_id,
        f'export PATH="{env_path}" && claude --dangerously-skip-permissions',
        "Enter",
    ])
    return pane_id


def send_prompt(
    pane_id: str,
    prompt: str,
    startup_delay: float = 6.0,
    submit_delay: float = 0.5,
) -> None:
    # Wait for Claude to finish initialising
    time.sleep(startup_delay)
    # Send prompt text first, then wait before submitting — ensures Claude
    # has registered the full text in its input buffer before Enter is sent
    subprocess.run(["tmux", "send-keys", "-t", pane_id, prompt])
    time.sleep(submit_delay)
    subprocess.run(["tmux", "send-keys", "-t", pane_id, "", "Enter"])


def write_context(task: AgentTask, content: str) -> None:
    assert task.state.worktree_path is not None, "worktree_path must be set before writing context"
    (task.state.worktree_path / "context.md").write_text(content)


def close_agent_pane(task: AgentTask) -> None:
    if task.state.pane_id:
        subprocess.run(["tmux", "kill-window", "-t", task.state.pane_id])


def remove_worktree(task: AgentTask) -> None:
    assert task.state.worktree_path is not None, "worktree_path must be set before removing"
    assert task.state.branch_name is not None, "branch_name must be set before removing"
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(task.state.worktree_path)],
        check=True,
    )
    subprocess.run(
        ["git", "branch", "-D", task.state.branch_name],
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


def read_done_note(task: AgentTask, graph_name: str, repo_root: Path) -> str:
    """Return the note (second line) from the .done signal file, or empty string."""
    signal_dir = repo_root / ".workflow" / graph_name / "signals" / task.id
    content = (signal_dir / ".done").read_text()
    lines = content.splitlines()
    return lines[1] if len(lines) > 1 else ""


def merge_pr(pr_url: str) -> None:
    """Merge a PR using gh CLI."""
    subprocess.run(
        ["gh", "pr", "merge", pr_url, "--merge"],
        check=True,
    )


def pull_main(repo_root: Path) -> bool:
    """Fast-forward local main to match origin/main after a PR merge.

    Returns True if the pull succeeded, False if it failed (e.g. because
    local main has diverged).  The caller should treat False as a signal
    that subsequent tasks must not start until the situation is resolved.
    """
    result = subprocess.run(
        ["git", "-C", str(repo_root), "pull", "--ff-only"],
        capture_output=True,
    )
    return result.returncode == 0


def write_merged_signal(task: AgentTask, graph_name: str, repo_root: Path) -> None:
    """Write the .merged sentinel after a successful PR merge."""
    signal_dir = repo_root / ".workflow" / graph_name / "signals" / task.id
    signal_dir.mkdir(parents=True, exist_ok=True)
    (signal_dir / ".merged").write_text(datetime.now(timezone.utc).isoformat())
