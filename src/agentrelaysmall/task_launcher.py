import asyncio
import json
import os
import subprocess
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path

from agentrelaysmall.agent_task import AgentTask


def create_graph_branch(
    graph_name: str,
    target_repo_root: Path,
    base_branch: str = "main",
) -> None:
    """Create graph/<graph-name> off base_branch and push it to origin.

    Idempotent: uses ls-remote as the authoritative check so stale local
    tracking refs (left over after a reset) cannot cause a false skip.
    If the remote branch already exists, skips creation.
    If the remote branch does not exist, sets the local branch to base_branch
    (creating or force-moving it as needed) and pushes to origin.
    """
    branch = f"graph/{graph_name}"
    # ls-remote is authoritative: stale refs/remotes/origin/<branch> tracking
    # refs can make rev-parse --verify return 0 even after a reset deletes the
    # remote branch, so we always check the remote directly.
    remote_check = subprocess.run(
        [
            "git",
            "-C",
            str(target_repo_root),
            "ls-remote",
            "--heads",
            "origin",
            f"refs/heads/{branch}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    if remote_check.stdout.strip():
        print(f"[graph] integration branch {branch} already exists — skipping creation")
        return
    # Remote branch does not exist.  Set the local branch to base_branch
    # (branch -f creates or moves it).  If the branch is currently checked out
    # in the main worktree, branch -f is rejected; fall back to reset --hard.
    set_local = subprocess.run(
        ["git", "-C", str(target_repo_root), "branch", "-f", branch, base_branch],
        capture_output=True,
    )
    if set_local.returncode != 0:
        # Branch is currently checked out — hard-reset HEAD to base_branch
        subprocess.run(
            ["git", "-C", str(target_repo_root), "reset", "--hard", base_branch],
            check=True,
        )
    subprocess.run(
        ["git", "-C", str(target_repo_root), "push", "-u", "origin", branch],
        check=True,
    )
    # Ensure the main worktree is back on base_branch
    subprocess.run(
        ["git", "-C", str(target_repo_root), "checkout", base_branch],
        capture_output=True,
    )


def create_worktree(
    task: AgentTask,
    graph_name: str,
    worktrees_root: Path,
    target_repo_root: Path,
    base_branch: str | None = None,
) -> Path:
    graph_branch = f"graph/{graph_name}"
    effective_base = base_branch if base_branch is not None else graph_branch
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
            effective_base,
        ],
        check=True,
    )
    task.state.worktree_path = worktree_path
    task.state.branch_name = branch_name
    return worktree_path


def write_task_context(
    task: AgentTask,
    graph_name: str,
    target_repo_root: Path,
    graph_branch: str,
    agent_index: int,
) -> None:
    signal_dir = target_repo_root / ".workflow" / graph_name / "signals" / task.id
    context = {
        "task_id": task.id,
        "graph_name": graph_name,
        "signal_dir": str(signal_dir),
        "role": task.role.value,
        "description": textwrap.fill(task.description, width=72),
        "graph_branch": graph_branch,
        "model": task.model,
        "completion_gate": task.completion_gate,
        "agent_index": agent_index,
    }
    signal_dir.mkdir(parents=True, exist_ok=True)
    (signal_dir / "task_context.json").write_text(json.dumps(context, indent=2))


def launch_agent(
    task: AgentTask,
    tmux_session: str,
    model: str | None = None,
    signal_dir: Path | None = None,
) -> str:
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
    # tools (gh, pixi, etc.) that live outside the default non-interactive PATH.
    # Export AGENTRELAY_SIGNAL_DIR so WorktreeTaskRunner.from_config() can locate
    # task_context.json under .workflow/ without reading from the worktree root.
    env_path = os.environ.get("PATH", "")
    signal_dir_export = f' AGENTRELAY_SIGNAL_DIR="{signal_dir}"' if signal_dir else ""
    model_flag = f"--model {model} " if model else ""
    subprocess.run(
        [
            "tmux",
            "send-keys",
            "-t",
            pane_id,
            f'export PATH="{env_path}"{signal_dir_export} && claude {model_flag}--dangerously-skip-permissions --add-dir {str(task.state.worktree_path)}',
            "Enter",
        ]
    )
    return pane_id


def _wait_for_claude_tui(pane_id: str, timeout: float = 30.0) -> bool:
    """Poll the tmux pane until Claude's TUI input area is visible.

    'bypass permissions' appears in the Claude status bar when launched with
    --dangerously-skip-permissions and the TUI is fully loaded.  Polling
    instead of a fixed sleep handles variable startup times (trust dialog
    acceptance, workspace initialisation, slow machines).

    Returns True when ready, False if timeout expires.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        capture = subprocess.run(
            ["tmux", "capture-pane", "-t", pane_id, "-p"],
            capture_output=True,
            text=True,
        )
        if capture.returncode == 0 and "bypass permissions" in capture.stdout:
            return True
        time.sleep(0.5)
    return False


def send_prompt(
    pane_id: str,
    prompt: str,
    bypass_delay: float = 4.0,
    startup_timeout: float = 30.0,
    submit_delay: float = 0.5,
) -> None:
    # Accept the workspace-trust dialog if it appears:
    # default option is "Yes, trust folder", so Enter confirms it.
    # The --dangerously-skip-permissions dialog is auto-accepted by
    # skipDangerousModePermissionPrompt=true in ~/.claude/settings.json,
    # so we no longer need the Down keystroke that used to navigate it.
    time.sleep(bypass_delay)
    subprocess.run(["tmux", "send-keys", "-t", pane_id, "Enter"])
    # Poll until Claude's TUI shows "bypass permissions" (fully loaded).
    # This is more robust than a fixed sleep for fresh (untrusted) workspaces
    # where the trust dialog acceptance adds variable startup time.
    if not _wait_for_claude_tui(pane_id, timeout=startup_timeout):
        print(
            f"[warn] Claude TUI not detected in pane {pane_id} after "
            f"{startup_timeout}s; sending prompt anyway"
        )
    # Send prompt text first, then wait before submitting — ensures Claude
    # has registered the full text in its input buffer before Enter is sent
    subprocess.run(["tmux", "send-keys", "-t", pane_id, prompt])
    time.sleep(submit_delay)
    subprocess.run(["tmux", "send-keys", "-t", pane_id, "Enter"])


def write_context(signal_dir: Path, content: str) -> None:
    signal_dir.mkdir(parents=True, exist_ok=True)
    (signal_dir / "context.md").write_text(content)


def write_instructions(signal_dir: Path, content: str) -> None:
    signal_dir.mkdir(parents=True, exist_ok=True)
    (signal_dir / "instructions.md").write_text(content)


def run_completion_gate(command: str, worktree_path: Path) -> bool:
    """Run the completion gate command in the worktree. Returns True if exit code is 0."""
    result = subprocess.run(command, shell=True, cwd=str(worktree_path))
    return result.returncode == 0


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


def pull_graph_branch(graph_name: str, target_repo_root: Path) -> bool:
    """Update the local graph/<graph-name> branch after a task PR merges.

    Two-step: fetch updates origin/<branch> tracking ref, then update-ref
    forces the local branch ref to match.  update-ref works even when the
    branch is currently checked out, unlike the fetch <src>:<dst> refspec
    form which is rejected in that situation.

    Returns True on success, False otherwise.
    """
    branch = f"graph/{graph_name}"
    fetch = subprocess.run(
        ["git", "-C", str(target_repo_root), "fetch", "origin", branch],
        capture_output=True,
    )
    if fetch.returncode != 0:
        return False
    update = subprocess.run(
        [
            "git",
            "-C",
            str(target_repo_root),
            "update-ref",
            f"refs/heads/{branch}",
            f"origin/{branch}",
        ],
        capture_output=True,
    )
    return update.returncode == 0


def create_final_pr(graph_name: str, target_repo_root: Path) -> str | None:
    """Create a PR from graph/<graph-name> → main and return its URL.

    Returns None if the graph branch has no commits ahead of main (e.g. a
    run resumed from stale signals with no new task work done).
    Idempotent: if an open PR from this head already exists (e.g. because the
    graph was re-run after a partial reset), returns the existing PR URL.
    """
    graph_branch = f"graph/{graph_name}"
    ahead = subprocess.run(
        [
            "git",
            "-C",
            str(target_repo_root),
            "log",
            "--oneline",
            f"main..{graph_branch}",
        ],
        capture_output=True,
        text=True,
    )
    if not ahead.stdout.strip():
        print(
            f"[graph] {graph_branch} has no commits ahead of main — "
            "skipping final PR (did tasks actually run?)"
        )
        return None
    result = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--title",
            f"graph/{graph_name}: merge all tasks into main",
            "--body",
            f"## Summary\n\nMerges the `{graph_branch}` integration branch into `main`.\n"
            f"This PR includes the combined output of all tasks in the `{graph_name}` graph.\n",
            "--base",
            "main",
            "--head",
            graph_branch,
        ],
        capture_output=True,
        text=True,
        cwd=str(target_repo_root),
    )
    if result.returncode == 0:
        return result.stdout.strip()
    # Creation failed — check for an existing open PR with the same head
    print(f"[graph] gh pr create stderr: {result.stderr.strip()}")
    existing = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "--head",
            graph_branch,
            "--base",
            "main",
            "--state",
            "open",
            "--json",
            "url",
            "--jq",
            ".[0].url",
        ],
        capture_output=True,
        text=True,
        cwd=str(target_repo_root),
    )
    if existing.returncode == 0 and existing.stdout.strip():
        url = existing.stdout.strip()
        print(f"[graph] using existing open PR: {url}")
        return url
    raise subprocess.CalledProcessError(
        result.returncode, result.args, result.stdout, result.stderr
    )


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

    Fetches origin/main first so the local tracking ref is current; this
    prevents --force-with-lease from being rejected with "stale info" when
    the final graph PR was merged on GitHub after the run completed but
    before reset was invoked.
    """
    subprocess.run(
        ["git", "-C", str(target_repo_root), "fetch", "origin", "main"],
        check=True,
    )
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


def delete_local_graph_branch(graph_name: str, target_repo_root: Path) -> None:
    """Delete the local graph/<graph-name> branch if it exists. Silent no-op otherwise."""
    branch = f"graph/{graph_name}"
    subprocess.run(
        ["git", "-C", str(target_repo_root), "branch", "-D", branch],
        capture_output=True,
    )


def graph_branch_exists_on_remote(graph_name: str, target_repo_root: Path) -> bool:
    """Return True if graph/<graph-name> exists on origin."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(target_repo_root),
            "ls-remote",
            "--heads",
            "origin",
            f"refs/heads/graph/{graph_name}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(result.stdout.strip())


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
