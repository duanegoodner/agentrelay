"""Reset a target repo to its pre-graph-run state.

Usage (from the target repo dir, with pixi env active):
    python -m agentrelaysmall.reset_graph graphs/agentrelaydemos.yaml
    python -m agentrelaysmall.reset_graph graphs/agentrelaydemos.yaml --yes

What this does (in order):
    1. Reads .workflow/<graph>/run_info.json to find the starting HEAD sha.
    2. Closes any open GitHub PRs on task/<graph>/* branches.
    3. Hard-resets target repo's main to the starting HEAD and force-pushes.
    4. Deletes remote task/<graph>/* branches.
    5. Removes leftover worktrees from worktrees_root/<graph>/.
    6. Deletes .workflow/<graph>/ from the target repo.

Requires:
    - run_info.json written by run_graph at graph start (present if graph was run)
    - gh CLI available and authenticated
    - git remote named 'origin' in the target repo
"""

import argparse
import shutil
import subprocess
from pathlib import Path

from agentrelaysmall.agent_task_graph import AgentTaskGraphBuilder
from agentrelaysmall.task_launcher import (
    delete_remote_branches,
    list_remote_task_branches,
    read_run_info,
    reset_target_repo_to_head,
)

REPO_ROOT = (
    Path(__file__).resolve().parents[2]
)  # src/agentrelaysmall/reset_graph.py → repo root
WORKTREES_ROOT = REPO_ROOT.parent / "worktrees"


def _get_remote_repo(target_repo_root: Path) -> str:
    """Return the GitHub owner/repo string inferred from origin remote URL."""
    result = subprocess.run(
        ["git", "-C", str(target_repo_root), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=True,
    )
    url = result.stdout.strip()
    # Handle both SSH (git@github.com:owner/repo.git) and HTTPS forms
    if url.startswith("git@"):
        # git@github.com:owner/repo.git
        path_part = url.split(":", 1)[1]
    else:
        # https://github.com/owner/repo.git
        path_part = url.split("github.com/", 1)[1]
    return path_part.removesuffix(".git")


def _close_open_prs(graph_name: str, target_repo_root: Path) -> None:
    """Close any open PRs whose head branch matches task/<graph-name>/*."""
    remote_repo = _get_remote_repo(target_repo_root)
    result = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            remote_repo,
            "--state",
            "open",
            "--json",
            "number,headRefName",
            "--jq",
            f'[.[] | select(.headRefName | startswith("task/{graph_name}/"))]',
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return
    import json

    prs = json.loads(result.stdout)
    for pr in prs:
        number = pr["number"]
        print(f"  [reset] closing PR #{number} ({pr['headRefName']})")
        subprocess.run(
            ["gh", "pr", "close", str(number), "--repo", remote_repo],
            check=True,
        )


def _remove_leftover_worktrees(graph_name: str, worktrees_root: Path) -> None:
    """Remove the worktrees/<graph-name>/ directory if it exists."""
    graph_wt_dir = worktrees_root / graph_name
    if graph_wt_dir.exists():
        print(f"  [reset] removing leftover worktrees at {graph_wt_dir}")
        shutil.rmtree(graph_wt_dir)


def _remove_workflow_dir(graph_name: str, target_repo_root: Path) -> None:
    """Remove .workflow/<graph-name>/ from the target repo."""
    workflow_dir = target_repo_root / ".workflow" / graph_name
    if workflow_dir.exists():
        print(f"  [reset] removing {workflow_dir}")
        shutil.rmtree(workflow_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset a target repo to its pre-graph-run state."
    )
    parser.add_argument("graph", help="Path to graph YAML file")
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt",
    )
    args = parser.parse_args()

    graph_path = Path(args.graph)
    if not graph_path.is_absolute():
        graph_path = Path.cwd() / graph_path

    graph = AgentTaskGraphBuilder.from_yaml(graph_path, REPO_ROOT, WORKTREES_ROOT)

    try:
        run_info = read_run_info(graph.name, graph.target_repo_root)
    except FileNotFoundError:
        print(
            f"[reset] ERROR: no run_info.json found for graph '{graph.name}' "
            f"in {graph.target_repo_root / '.workflow' / graph.name}\n"
            "Has this graph been run at least once?"
        )
        raise SystemExit(1)

    start_head = run_info["start_head"]
    started_at = run_info.get("started_at", "unknown")

    print(f"[reset] graph:       {graph.name}")
    print(f"[reset] target repo: {graph.target_repo_root}")
    print(f"[reset] run started: {started_at}")
    print(f"[reset] start HEAD:  {start_head[:12]}")
    print()
    print("[reset] This will:")
    print("  1. Close open PRs on task branches")
    print(
        f"  2. git reset --hard {start_head[:12]} && push --force-with-lease origin main"
    )
    print("  3. Delete remote task branches")
    print("  4. Remove leftover worktrees")
    print(f"  5. Delete .workflow/{graph.name}/")

    if not args.yes:
        answer = input("\nContinue? [y/N] ")
        if answer.strip().lower() != "y":
            print("[reset] Aborted.")
            raise SystemExit(0)

    print()
    print("[reset] step 1: closing open PRs")
    _close_open_prs(graph.name, graph.target_repo_root)

    print("[reset] step 2: resetting main and force-pushing")
    reset_target_repo_to_head(start_head, graph.target_repo_root)
    print(f"  [reset] main is now at {start_head[:12]}")

    print("[reset] step 3: deleting remote task branches")
    branches = list_remote_task_branches(graph.name, graph.target_repo_root)
    if branches:
        print(f"  [reset] deleting: {branches}")
        delete_remote_branches(branches, graph.target_repo_root)
    else:
        print("  [reset] none found")

    print("[reset] step 4: removing leftover worktrees")
    _remove_leftover_worktrees(graph.name, WORKTREES_ROOT)

    print("[reset] step 5: removing signal files")
    _remove_workflow_dir(graph.name, graph.target_repo_root)

    print("\n[reset] done — target repo is back to its pre-run state.")


if __name__ == "__main__":
    main()
