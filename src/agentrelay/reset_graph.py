"""Reset a repository to its pre-graph-run state.

Usage::

    python -m agentrelay.reset_graph graphs/demo.yaml
    python -m agentrelay.reset_graph graphs/demo.yaml --yes

Reads ``.workflow/<graph>/run_info.json`` (written by :mod:`run_graph`) to
determine the starting HEAD, then:

1. Closes open PRs on graph branches.
2. Resets main to the starting HEAD and force-pushes (if safe).
3. Deletes remote and local branches created by the graph run.
4. Removes worktree directories.
5. Removes the ``.workflow/<graph>/`` directory.

Idempotent: re-running after a successful reset is safe.  Out-of-order
resets (resetting an older graph while a newer one's commits remain) are
detected and the main-branch reset is skipped to avoid history corruption.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentrelay.ops import gh, git

_BRANCH_PREFIX = "agentrelay"


@dataclass
class ResetPlan:
    """Describes the operations a reset will perform.

    Attributes:
        graph_name: Name of the graph being reset.
        repo_path: Path to the repository root.
        start_head: SHA to reset main to.
        started_at: ISO timestamp of the original run.
        branch_prefix: Remote branch prefix to match.
        worktree_dir: Directory containing workstream worktrees.
        workflow_dir: Signal/run-info directory.
        can_reset_main: Whether the main-branch reset is safe.
        open_prs: Open PRs that will be closed.
        remote_branches: Remote branches that will be deleted.
        log: Messages emitted during planning.
    """

    graph_name: str
    repo_path: Path
    start_head: str
    started_at: str
    branch_prefix: str
    worktree_dir: Path
    workflow_dir: Path
    can_reset_main: bool
    open_prs: list[dict[str, Any]] = field(default_factory=list)
    remote_branches: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)


def _load_run_info(workflow_dir: Path) -> dict[str, str]:
    """Read and return run_info.json from the workflow directory.

    Raises:
        FileNotFoundError: If run_info.json does not exist.
    """
    path = workflow_dir / "run_info.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"No run_info.json at {path}. Was the graph run with run_graph?"
        )
    return json.loads(path.read_text())


def plan_reset(
    graph_name: str,
    repo_path: Path,
) -> ResetPlan:
    """Build a reset plan by inspecting repository and GitHub state.

    Does not modify anything — only reads.

    Args:
        graph_name: Name of the graph to reset.
        repo_path: Path to the repository root.

    Returns:
        ResetPlan describing what the reset will do.
    """
    workflow_dir = repo_path / ".workflow" / graph_name
    worktree_dir = repo_path / ".worktrees" / graph_name
    branch_prefix = f"{_BRANCH_PREFIX}/{graph_name}/"

    run_info = _load_run_info(workflow_dir)
    start_head = run_info["start_head"]
    started_at = run_info.get("started_at", "unknown")

    plan = ResetPlan(
        graph_name=graph_name,
        repo_path=repo_path,
        start_head=start_head,
        started_at=started_at,
        branch_prefix=branch_prefix,
        worktree_dir=worktree_dir,
        workflow_dir=workflow_dir,
        can_reset_main=True,
    )

    # Check ancestry for out-of-order reset detection.
    if not git.merge_base_is_ancestor(repo_path, start_head, "HEAD"):
        plan.can_reset_main = False
        plan.log.append(
            f"WARNING: start_head {start_head[:12]} is not an ancestor of HEAD. "
            "This likely means graphs were run in a different order. "
            "Main-branch reset will be skipped. Reset graphs in reverse "
            "run order (most-recently-run first)."
        )

    # Discover open PRs on graph branches.
    try:
        plan.open_prs = gh.pr_list(repo_path, head_prefix=branch_prefix)
    except subprocess.CalledProcessError:
        plan.log.append(
            "Could not list PRs (gh CLI error). PR closing will be skipped."
        )

    # Discover remote branches.
    plan.remote_branches = git.ls_remote_branches(
        repo_path, f"refs/heads/{branch_prefix}*"
    )

    return plan


def execute_reset(plan: ResetPlan) -> list[str]:
    """Execute a reset plan, returning a log of actions taken.

    Args:
        plan: A reset plan from :func:`plan_reset`.

    Returns:
        List of human-readable log messages.
    """
    log: list[str] = list(plan.log)
    repo = plan.repo_path

    # Step 1: Close open PRs.
    for pr in plan.open_prs:
        pr_num = int(pr["number"])
        branch = pr["headRefName"]
        try:
            gh.pr_close(repo, pr_num)
            log.append(f"Closed PR #{pr_num} ({branch})")
        except subprocess.CalledProcessError:
            log.append(f"Failed to close PR #{pr_num} ({branch}), skipping")

    # Step 2: Reset main and force-push.
    if plan.can_reset_main:
        git.fetch_branch(repo, "main")
        git.reset_hard(repo, plan.start_head)
        git.push_force_with_lease(repo, "main")
        log.append(f"Reset main to {plan.start_head[:12]} and force-pushed")
    else:
        log.append("Skipped main-branch reset (out-of-order)")

    # Step 3: Delete remote branches.
    for branch in plan.remote_branches:
        try:
            git.push_delete_branch(repo, branch)
            log.append(f"Deleted remote branch {branch}")
        except subprocess.CalledProcessError:
            log.append(f"Failed to delete remote branch {branch}, skipping")

    # Step 3b: Delete local branches (best-effort).
    for branch in plan.remote_branches:
        try:
            git.branch_delete(repo, branch)
        except subprocess.CalledProcessError:
            pass  # Local branch may not exist

    # Step 4: Remove worktree directory.
    if plan.worktree_dir.is_dir():
        shutil.rmtree(plan.worktree_dir)
        log.append(f"Removed worktree directory {plan.worktree_dir}")

    # Step 5: Remove workflow directory.
    if plan.workflow_dir.is_dir():
        shutil.rmtree(plan.workflow_dir)
        log.append(f"Removed workflow directory {plan.workflow_dir}")

    return log


def print_plan(plan: ResetPlan) -> None:
    """Print a human-readable summary of a reset plan.

    Args:
        plan: A reset plan from :func:`plan_reset`.
    """
    print(f"[reset] Graph: {plan.graph_name}")
    print(f"[reset] Start HEAD: {plan.start_head[:12]}")
    print(f"[reset] Run started at: {plan.started_at}")
    print(f"[reset] Open PRs to close: {len(plan.open_prs)}")
    print(f"[reset] Remote branches to delete: {len(plan.remote_branches)}")
    print(
        f"[reset] Reset main: {'yes' if plan.can_reset_main else 'SKIPPED (out-of-order)'}"
    )
    if plan.worktree_dir.is_dir():
        print(f"[reset] Worktree dir to remove: {plan.worktree_dir}")
    if plan.workflow_dir.is_dir():
        print(f"[reset] Workflow dir to remove: {plan.workflow_dir}")
    for msg in plan.log:
        print(f"[reset] {msg}")


def reset_graph(
    graph_name: str,
    repo_path: Path,
    *,
    yes: bool = False,
) -> list[str]:
    """Plan and execute a graph reset.

    Args:
        graph_name: Name of the graph to reset.
        repo_path: Path to the repository root.
        yes: Skip interactive confirmation.

    Returns:
        List of log messages describing actions taken.
    """
    plan = plan_reset(graph_name, repo_path)
    print_plan(plan)

    if not yes:
        response = input("\n[reset] Continue? [y/N] ")
        if response.strip().lower() != "y":
            print("[reset] Aborted.")
            return []

    log = execute_reset(plan)
    for msg in log:
        print(f"[reset] {msg}")
    print("[reset] Done.")
    return log


def _resolve_graph_name(graph_path: Path) -> str:
    """Extract graph name from a YAML file.

    Args:
        graph_path: Path to the graph YAML file.

    Returns:
        The graph name string.
    """
    import yaml

    raw = yaml.safe_load(graph_path.read_text())
    name = raw.get("name")
    if not name:
        raise ValueError(f"Graph YAML at {graph_path} has no 'name' field")
    return str(name)


def main() -> None:
    """CLI entry point for resetting a graph run."""
    parser = argparse.ArgumentParser(
        description="Reset a repository to its pre-graph-run state.",
    )
    parser.add_argument(
        "graph",
        help="Path to graph YAML file",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt",
    )
    args = parser.parse_args()

    graph_path = Path(args.graph).resolve()
    if not graph_path.is_file():
        print(f"Error: graph file not found: {graph_path}", file=sys.stderr)
        sys.exit(1)

    graph_name = _resolve_graph_name(graph_path)
    repo_path = Path.cwd()

    try:
        reset_graph(graph_name, repo_path, yes=args.yes)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
