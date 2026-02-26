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
    target_repo_root: Path,
    base_branch: str = "main",
) -> Path:
    worktree_path = worktrees_root / graph_name / task.id
    branch_name = f"task/{graph_name}/{task.id}"
    subprocess.run(
        [
            "git",
            "-C",
            str(target_repo_root),
            "worktree",
            "add",
            "-b",
            branch_name,
            str(worktree_path),
            base_branch,
        ],
        check=True,
    )
    task.state.worktree_path = worktree_path
    task.state.branch_name = branch_name
    return worktree_path


def write_task_context(
    task: AgentTask, graph_name: str, target_repo_root: Path
) -> None:
    signal_dir = target_repo_root / ".workflow" / graph_name / "signals" / task.id
    context = {
        "task_id": task.id,
        "graph_name": graph_name,
        "signal_dir": str(signal_dir),
    }
    assert (
        task.state.worktree_path is not None
    ), "worktree_path must be set before writing context"
    (task.state.worktree_path / "task_context.json").write_text(
        json.dumps(context, indent=2)
    )


def launch_agent(task: AgentTask, tmux_session: str) -> str:
    assert (
        task.state.worktree_path is not None
    ), "worktree_path must be set before launching agent"
    pane_id = (
        subprocess.check_output(
            [
                "tmux",
                "new-window",
                "-t",
                tmux_session,
                "-n",
                task.id,
                "-P",
                "-F",
                "#{pane_id}",
                "-c",
                str(task.state.worktree_path),
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
    subprocess.run(
        [
            "tmux",
            "send-keys",
            "-t",
            pane_id,
            f'export PATH="{env_path}" && claude --dangerously-skip-permissions',
            "Enter",
        ]
    )
    return pane_id


def send_prompt(
    pane_id: str,
    prompt: str,
    bypass_delay: float = 4.0,
    startup_delay: float = 6.0,
    submit_delay: float = 0.5,
) -> None:
    # Navigate the --dangerously-skip-permissions confirmation dialog:
    # cursor starts on "No, exit"; Down moves to "Yes, I accept", Enter confirms
    time.sleep(bypass_delay)
    subprocess.run(["tmux", "send-keys", "-t", pane_id, "Down"])
    time.sleep(0.2)
    subprocess.run(["tmux", "send-keys", "-t", pane_id, "Enter"])
    # Wait for Claude to finish initialising past the confirmation
    time.sleep(startup_delay)
    # Send prompt text first, then wait before submitting — ensures Claude
    # has registered the full text in its input buffer before Enter is sent
    subprocess.run(["tmux", "send-keys", "-t", pane_id, prompt])
    time.sleep(submit_delay)
    subprocess.run(["tmux", "send-keys", "-t", pane_id, "Enter"])


def write_context(task: AgentTask, content: str) -> None:
    assert (
        task.state.worktree_path is not None
    ), "worktree_path must be set before writing context"
    (task.state.worktree_path / "context.md").write_text(content)


def save_agent_log(task: AgentTask, signal_dir: Path) -> None:
    """Capture the tmux pane scrollback and write to signal_dir/agent.log."""
    if not task.state.pane_id:
        return
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", task.state.pane_id, "-p", "-S", "-"],
        capture_output=True,
        text=True,
    )
    signal_dir.mkdir(parents=True, exist_ok=True)
    (signal_dir / "agent.log").write_text(result.stdout)


def close_agent_pane(task: AgentTask) -> None:
    if task.state.pane_id:
        subprocess.run(["tmux", "kill-window", "-t", task.state.pane_id])


def remove_worktree(task: AgentTask, target_repo_root: Path) -> None:
    assert (
        task.state.worktree_path is not None
    ), "worktree_path must be set before removing"
    assert task.state.branch_name is not None, "branch_name must be set before removing"
    subprocess.run(
        [
            "git",
            "-C",
            str(target_repo_root),
            "worktree",
            "remove",
            "--force",
            str(task.state.worktree_path),
        ],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(target_repo_root), "branch", "-D", task.state.branch_name],
        check=True,
    )


async def poll_for_completion(
    task: AgentTask,
    graph_name: str,
    target_repo_root: Path,
    poll_interval: float = 2.0,
) -> str:
    signal_dir = target_repo_root / ".workflow" / graph_name / "signals" / task.id
    while True:
        if (signal_dir / ".done").exists():
            return "done"
        if (signal_dir / ".failed").exists():
            return "failed"
        await asyncio.sleep(poll_interval)


def read_done_note(task: AgentTask, graph_name: str, target_repo_root: Path) -> str:
    """Return the note (second line) from the .done signal file, or empty string."""
    signal_dir = target_repo_root / ".workflow" / graph_name / "signals" / task.id
    content = (signal_dir / ".done").read_text()
    lines = content.splitlines()
    return lines[1] if len(lines) > 1 else ""


def merge_pr(pr_url: str) -> None:
    """Merge a PR using gh CLI."""
    subprocess.run(
        ["gh", "pr", "merge", pr_url, "--merge"],
        check=True,
    )


def pull_main(target_repo_root: Path) -> bool:
    """Fast-forward local main to match origin/main after a PR merge.

    Returns True if the pull succeeded, False if it failed (e.g. because
    local main has diverged).  The caller should treat False as a signal
    that subsequent tasks must not start until the situation is resolved.
    """
    result = subprocess.run(
        ["git", "-C", str(target_repo_root), "pull", "--ff-only"],
        capture_output=True,
    )
    return result.returncode == 0


def write_merged_signal(
    task: AgentTask, graph_name: str, target_repo_root: Path
) -> None:
    """Write the .merged sentinel after a successful PR merge."""
    signal_dir = target_repo_root / ".workflow" / graph_name / "signals" / task.id
    signal_dir.mkdir(parents=True, exist_ok=True)
    (signal_dir / ".merged").write_text(datetime.now(timezone.utc).isoformat())


def pixi_toml_changed_in_pr(pr_url: str) -> bool:
    """Return True if pixi.toml was among the files changed in the given PR."""
    result = subprocess.run(
        ["gh", "pr", "view", pr_url, "--json", "files", "--jq", "[.files[].path]"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    return "pixi.toml" in json.loads(result.stdout)


def run_pixi_install(target_repo_root: Path) -> bool:
    """Run `pixi install` for target_repo_root. Returns True on success."""
    result = subprocess.run(
        ["pixi", "install", "--manifest-path", str(target_repo_root / "pixi.toml")],
        capture_output=True,
    )
    return result.returncode == 0


def neutralize_pixi_lock_in_pr(task: AgentTask) -> None:
    """Restore main's current pixi.lock into the agent branch and push.

    Ensures the PR never carries an agent-generated pixi.lock into main,
    preventing merge conflicts when parallel agents have both modified pixi.toml.
    The orchestrator regenerates pixi.lock in main after merging.
    Only commits and pushes if the agent's pixi.lock actually differs from main's.
    """
    worktree = task.state.worktree_path
    branch = task.state.branch_name
    subprocess.run(["git", "-C", str(worktree), "fetch", "origin", "main"], check=True)
    subprocess.run(
        ["git", "-C", str(worktree), "checkout", "origin/main", "--", "pixi.lock"],
        check=True,
    )
    staged = subprocess.run(
        ["git", "-C", str(worktree), "diff", "--staged", "--name-only"],
        capture_output=True,
        text=True,
    )
    if "pixi.lock" in staged.stdout:
        subprocess.run(
            [
                "git",
                "-C",
                str(worktree),
                "commit",
                "-m",
                "chore: restore main pixi.lock (orchestrator regenerates after merge)",
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(worktree), "push", "origin", f"HEAD:{branch}"],
            check=True,
        )


def record_run_start(graph_name: str, target_repo_root: Path) -> None:
    """Write run_info.json with the starting HEAD sha and timestamp.

    Called before any tasks are dispatched so that reset_graph can return
    the target repo to exactly this state.
    """
    result = subprocess.run(
        ["git", "-C", str(target_repo_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    start_head = result.stdout.strip()
    run_info_dir = target_repo_root / ".workflow" / graph_name
    run_info_dir.mkdir(parents=True, exist_ok=True)
    (run_info_dir / "run_info.json").write_text(
        json.dumps(
            {
                "start_head": start_head,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        )
    )


def read_run_info(graph_name: str, target_repo_root: Path) -> dict:
    """Return the dict stored in run_info.json for the given graph run."""
    p = target_repo_root / ".workflow" / graph_name / "run_info.json"
    return json.loads(p.read_text())


def reset_target_repo_to_head(start_head: str, target_repo_root: Path) -> None:
    """Hard-reset target repo's main to start_head and force-push to origin.

    Uses --force-with-lease so the push is rejected if unrelated commits
    have appeared on origin/main since start_head was recorded.
    """
    subprocess.run(
        ["git", "-C", str(target_repo_root), "reset", "--hard", start_head],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(target_repo_root),
            "push",
            "--force-with-lease",
            "origin",
            "main",
        ],
        check=True,
    )


def list_remote_task_branches(graph_name: str, target_repo_root: Path) -> list[str]:
    """Return short branch names on origin matching task/<graph-name>/*."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(target_repo_root),
            "ls-remote",
            "--heads",
            "origin",
            f"refs/heads/task/{graph_name}/*",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    branches = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        ref = line.split("\t")[1]  # refs/heads/task/<graph>/<id>
        branches.append(ref.removeprefix("refs/heads/"))
    return branches


def delete_remote_branches(branches: list[str], target_repo_root: Path) -> None:
    """Delete a list of remote branches from origin. No-op if list is empty."""
    if not branches:
        return
    subprocess.run(
        ["git", "-C", str(target_repo_root), "push", "origin", "--delete"] + branches,
        check=True,
    )


def save_pr_summary(pr_url: str, signal_dir: Path) -> None:
    """Fetch the PR body and write it to signal_dir/summary.md.

    Called after merge_pr() so the agent's self-description of what it did is
    preserved in the signal directory alongside the other per-task artefacts.
    Silently skips if gh returns an error or the body is empty.
    """
    result = subprocess.run(
        ["gh", "pr", "view", pr_url, "--json", "body", "--jq", ".body"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return
    body = result.stdout.strip()
    if body:
        signal_dir.mkdir(parents=True, exist_ok=True)
        (signal_dir / "summary.md").write_text(body)


def commit_pixi_lock_to_main(target_repo_root: Path) -> None:
    """Commit a freshly regenerated pixi.lock to main and push.

    Called after run_pixi_install() re-solves pixi.lock from the newly merged
    pixi.toml. Only commits and pushes if pixi.lock actually changed.
    """
    subprocess.run(["git", "-C", str(target_repo_root), "add", "pixi.lock"], check=True)
    staged = subprocess.run(
        ["git", "-C", str(target_repo_root), "diff", "--staged", "--name-only"],
        capture_output=True,
        text=True,
    )
    if "pixi.lock" in staged.stdout:
        subprocess.run(
            [
                "git",
                "-C",
                str(target_repo_root),
                "commit",
                "-m",
                "chore: regenerate pixi.lock after dependency update",
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(target_repo_root), "push", "origin", "main"],
            check=True,
        )
