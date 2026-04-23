"""Top-level CLI for agentrelay.

Usage::

    agentrelay run graphs/demo.yaml
    agentrelay run graphs/demo.yaml --target-repo /path/to/repo
    agentrelay reset graphs/demo.yaml --yes
    agentrelay reset-task graphs/demo.yaml --task my_task
    agentrelay teardown-workstream graphs/demo.yaml --workstream ws-1
    agentrelay reset-workstream graphs/demo.yaml --workstream ws-1 --yes
    agentrelay reset-to graphs/demo.yaml --after my_task --yes
    agentrelay check --target-repo /path/to/repo
    agentrelay dry-run graphs/demo.yaml

This module provides the ``agentrelay`` console script registered in
``pyproject.toml``.  Each subcommand delegates to the existing library
functions in :mod:`run_graph`, :mod:`reset_graph`, :mod:`reset_task`,
:mod:`reset_to`, and :mod:`reset_workstream`.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Optional

import yaml

from agentrelay.graph_index import DuplicateGraphNameError, GraphIndex
from agentrelay.orchestrator import OrchestratorOutcome
from agentrelay.reset_graph import (
    _find_latest_run_dir,
    _resolve_graph_name,
    reset_graph,
)
from agentrelay.reset_ops import ResetOps
from agentrelay.reset_pr import GhIntegrationPrOps
from agentrelay.reset_task import reset_task
from agentrelay.reset_to import build_plan as build_reset_to_plan
from agentrelay.reset_to import execute_plan as execute_reset_to_plan
from agentrelay.reset_to import format_plan as format_reset_to_plan
from agentrelay.reset_workstream import (
    reset_workstream,
    teardown_workstream,
)
from agentrelay.run_graph import (
    RunOptions,
    _dry_run_conflict_check,
    _extract_operational_config,
    _print_result,
    dry_run,
    run_graph,
)
from agentrelay.sandbox import FileCredentialProvider
from agentrelay.session import SessionError
from agentrelay.task_graph import TaskGraph, TaskGraphBuilder
from agentrelay.tools import ToolValidationError


def _add_target_repo_arg(parser: argparse.ArgumentParser) -> None:
    """Add ``--target-repo`` argument to a subparser."""
    parser.add_argument(
        "-t",
        "--target-repo",
        default=None,
        help="Path to the target repository (default: current directory)",
    )


def _add_graph_dir_arg(parser: argparse.ArgumentParser) -> None:
    """Add ``--graph-dir`` / ``-g`` argument to a subparser."""
    parser.add_argument(
        "--graph-dir",
        "-g",
        default=None,
        help="Directory to scan for graph YAML files (enables name-based selection)",
    )


def _resolve_repo_path(args: argparse.Namespace) -> Path:
    """Return resolved repo path from ``--target-repo`` or cwd."""
    if args.target_repo is not None:
        return Path(args.target_repo).resolve()
    return Path.cwd()


def _resolve_graph_path(raw: str) -> Path:
    """Resolve a graph YAML path, exiting on error.

    Args:
        raw: Raw path string from the CLI.

    Returns:
        Resolved absolute path.
    """
    graph_path = Path(raw).resolve()
    if not graph_path.is_file():
        print(f"Error: graph file not found: {graph_path}", file=sys.stderr)
        sys.exit(1)
    return graph_path


def _resolve_graph_with_index(args: argparse.Namespace) -> Path:
    """Resolve graph reference using index (if ``-g`` given) or path.

    When ``--graph-dir`` is provided, builds a :class:`GraphIndex` and
    resolves the graph argument through it.  When absent, falls back to
    direct path resolution with a note about name uniqueness.

    Args:
        args: Parsed CLI arguments with ``graph`` and ``graph_dir``.

    Returns:
        Resolved absolute path to the graph YAML file.
    """
    if args.graph_dir is not None:
        graph_dir = Path(args.graph_dir).resolve()
        try:
            index = GraphIndex(graph_dir)
        except (FileNotFoundError, DuplicateGraphNameError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        try:
            return index.resolve(args.graph)
        except (KeyError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

    # No -g: backward-compatible path mode with note.
    print(
        "Note: running without --graph-dir; name uniqueness not validated.",
        file=sys.stderr,
    )
    return _resolve_graph_path(args.graph)


def _do_dry_run(graph_path: Path, repo_path: Path) -> None:
    """Run dry-run logic: validate graph and check for conflicts."""
    dry_run(graph_path)
    raw = yaml.safe_load(graph_path.read_text())
    graph_name = raw.get("name")
    if graph_name:
        _dry_run_conflict_check(repo_path, graph_name)


def _handle_run(args: argparse.Namespace) -> None:
    """Handler for ``agentrelay run``."""
    graph_path = _resolve_graph_with_index(args)
    repo_path = _resolve_repo_path(args)

    if args.dry_run:
        _do_dry_run(graph_path, repo_path)
        return

    credential_provider: Optional[FileCredentialProvider] = None
    if args.credentials is not None:
        creds_path = Path(args.credentials).resolve()
        if not creds_path.is_file():
            print(f"Error: credentials file not found: {creds_path}", file=sys.stderr)
            sys.exit(1)
        credential_provider = FileCredentialProvider(creds_path)

    options = RunOptions(
        tmux_session=args.tmux_session,
        keep_panes=args.keep_panes,
        model_override=args.model,
        max_concurrency=args.max_concurrency,
        max_task_attempts=args.max_task_attempts,
        teardown_mode=args.teardown_mode,
        fail_fast_on_workstream_error=args.fail_fast_workstream,
        fail_fast_on_internal_error=args.fail_fast_internal,
        credential_provider=credential_provider,
        anthropic_credential_name=args.anthropic_credential,
        sandbox_override=args.sandbox,
        verbose=args.verbose,
    )

    try:
        result = asyncio.run(
            run_graph(
                graph_path=graph_path,
                repo_path=repo_path,
                options=options,
            )
        )
    except (
        SessionError,
        ToolValidationError,
        ValueError,
        RuntimeError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    _print_result(result)

    if result.outcome != OrchestratorOutcome.SUCCEEDED:
        sys.exit(1)


def _handle_reset(args: argparse.Namespace) -> None:
    """Handler for ``agentrelay reset``."""
    graph_path = _resolve_graph_with_index(args)
    repo_path = _resolve_repo_path(args)
    graph_name = _resolve_graph_name(graph_path)

    try:
        reset_graph(graph_name, repo_path, yes=args.yes)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _handle_check(args: argparse.Namespace) -> None:
    """Handler for ``agentrelay check``."""
    repo_path = _resolve_repo_path(args)

    script = Path(__file__).resolve().parent.parent.parent / "tools" / "e2e_check.sh"
    if not script.is_file():
        print(
            "Error: e2e_check.sh not found. The 'check' subcommand is only "
            "available when running from the agentrelay source tree.",
            file=sys.stderr,
        )
        sys.exit(1)

    result = subprocess.run(
        ["bash", str(script), str(repo_path), "--env", args.env],
    )
    sys.exit(result.returncode)


def _handle_dry_run(args: argparse.Namespace) -> None:
    """Handler for ``agentrelay dry-run``."""
    graph_path = _resolve_graph_with_index(args)
    repo_path = _resolve_repo_path(args)
    _do_dry_run(graph_path, repo_path)


def _handle_list(args: argparse.Namespace) -> None:
    """Handler for ``agentrelay list``."""
    graph_dir = Path(args.graph_dir).resolve()
    try:
        index = GraphIndex(graph_dir)
    except (FileNotFoundError, DuplicateGraphNameError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    entries = index.entries
    if not entries:
        print("No graphs found.", file=sys.stderr)
        return

    name_w = max(len(e.name) for e in entries)
    cat_w = max(len(e.category) for e in entries)
    print(f"{'NAME':<{name_w}}  {'CATEGORY':<{cat_w}}  PATH")
    for e in entries:
        print(f"{e.name:<{name_w}}  {e.category:<{cat_w}}  {e.path}")


def _resolve_reset_context(
    args: argparse.Namespace,
) -> tuple[str, TaskGraph, Path, Path]:
    """Resolve graph, repo path, and run dir for reset subcommands.

    Loads the graph YAML, strips operational config keys, builds a
    :class:`TaskGraph`, and locates the latest run directory.

    Args:
        args: Parsed CLI arguments with ``graph``, ``graph_dir``, and
            ``target_repo``.

    Returns:
        Tuple of ``(graph_name, graph, repo_path, run_dir)``.
    """
    graph_path = _resolve_graph_with_index(args)
    repo_path = _resolve_repo_path(args)

    raw = yaml.safe_load(graph_path.read_text())
    graph_name = raw.get("name")
    if not graph_name:
        print("Error: Graph YAML has no 'name' field", file=sys.stderr)
        sys.exit(1)

    _extract_operational_config(raw)  # Pops operational keys.
    graph = TaskGraphBuilder.from_dict(raw)

    workflow_dir = repo_path / ".workflow" / graph_name
    run_dir = _find_latest_run_dir(workflow_dir)
    if run_dir is None:
        print(
            f"Error: No run directory found for graph '{graph_name}'. "
            "Has this graph been run?",
            file=sys.stderr,
        )
        sys.exit(1)

    return graph_name, graph, repo_path, run_dir


def _handle_reset_task(args: argparse.Namespace) -> None:
    """Handler for ``agentrelay reset-task``."""
    graph_name, graph, repo_path, run_dir = _resolve_reset_context(args)
    reset_ops = ResetOps.for_repo(repo_path)

    try:
        log = reset_task(
            graph_name,
            graph,
            run_dir,
            reset_ops,
            task_id=args.task,
            ws_id=args.workstream,
            integration_pr_ops=GhIntegrationPrOps(),
        )
    except (ValueError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    for msg in log:
        print(f"[reset-task] {msg}")
    print("[reset-task] Done.")


def _handle_teardown_workstream(args: argparse.Namespace) -> None:
    """Handler for ``agentrelay teardown-workstream``."""
    graph_name, graph, repo_path, run_dir = _resolve_reset_context(args)
    reset_ops = ResetOps.for_repo(repo_path)

    try:
        log = teardown_workstream(
            graph_name,
            graph,
            run_dir,
            reset_ops,
            ws_id=args.workstream,
        )
    except (ValueError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    for msg in log:
        print(f"[teardown-workstream] {msg}")
    print("[teardown-workstream] Done.")


def _handle_reset_workstream(args: argparse.Namespace) -> None:
    """Handler for ``agentrelay reset-workstream``."""
    graph_name, graph, repo_path, run_dir = _resolve_reset_context(args)
    reset_ops = ResetOps.for_repo(repo_path)

    if not args.yes:
        try:
            ws_spec = graph.workstream(args.workstream)
        except KeyError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        print(
            f"[reset-workstream] This will force-push to "
            f"'{ws_spec.merge_target_branch}'."
        )
        response = input("[reset-workstream] Continue? [y/N] ")
        if response.strip().lower() != "y":
            print("[reset-workstream] Aborted.")
            return

    try:
        log = reset_workstream(
            graph_name,
            graph,
            run_dir,
            reset_ops,
            ws_id=args.workstream,
            integration_pr_ops=GhIntegrationPrOps(),
        )
    except (ValueError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    for msg in log:
        print(f"[reset-workstream] {msg}")
    print("[reset-workstream] Done.")


def _handle_reset_to(args: argparse.Namespace) -> None:
    """Handler for ``agentrelay reset-to``."""
    graph_name, graph, repo_path, run_dir = _resolve_reset_context(args)
    reset_ops = ResetOps.for_repo(repo_path)

    try:
        plan = build_reset_to_plan(
            graph_name, graph, run_dir, reset_ops, after=args.after
        )
    except (ValueError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # Display plan.
    for line in format_reset_to_plan(plan).splitlines():
        print(f"[reset-to] {line}")

    if not args.yes:
        response = input("[reset-to] Proceed? [y/N] ")
        if response.strip().lower() != "y":
            print("[reset-to] Aborted.")
            return

    try:
        log = execute_reset_to_plan(
            graph_name,
            graph,
            run_dir,
            reset_ops,
            plan,
            integration_pr_ops=GhIntegrationPrOps(),
        )
    except (ValueError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    for msg in log:
        print(f"[reset-to] {msg}")
    print("[reset-to] Done.")


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="agentrelay",
        description="agentrelay task graph orchestrator.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- run ---
    run_parser = subparsers.add_parser(
        "run",
        help="Run a task graph",
        description="Run an agentrelay task graph.",
    )
    run_parser.add_argument("graph", help="Graph name or path to YAML file")
    _add_graph_dir_arg(run_parser)
    _add_target_repo_arg(run_parser)
    run_parser.add_argument(
        "-c",
        "--max-concurrency",
        type=int,
        default=None,
        help="Maximum concurrent tasks (default: 1)",
    )
    run_parser.add_argument(
        "-a",
        "--max-task-attempts",
        type=int,
        default=None,
        help="Maximum attempts per task (default: 1)",
    )
    run_parser.add_argument(
        "-T",
        "--teardown-mode",
        choices=["always", "never", "on_success"],
        default=None,
        help="When to tear down task resources (default: always)",
    )
    run_parser.add_argument(
        "-s",
        "--tmux-session",
        default=None,
        help="Override tmux session name (auto-detected from current tmux session)",
    )
    run_parser.add_argument(
        "-m",
        "--model",
        default=None,
        help="Override model for all agents",
    )
    run_parser.add_argument(
        "-C",
        "--credentials",
        default=None,
        help="Path to credentials YAML file for sandboxed agents",
    )
    run_parser.add_argument(
        "-A",
        "--anthropic-credential",
        default=None,
        help="Name of Anthropic credential from credentials YAML file",
    )
    run_parser.add_argument(
        "-S",
        "--sandbox",
        choices=["oci", "none"],
        default=None,
        help="Override sandbox type for all tasks (oci or none)",
    )
    run_parser.add_argument(
        "-W",
        "--fail-fast-workstream",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Stop preparing new workstreams after a workstream failure (default: false)",
    )
    run_parser.add_argument(
        "-I",
        "--fail-fast-internal",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Stop scheduling immediately on internal orchestrator errors (default: true)",
    )
    run_parser.add_argument(
        "-k",
        "--keep-panes",
        action="store_true",
        help="Keep tmux panes open after task completion",
    )
    run_parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Validate graph and print execution plan without running",
    )
    run_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed step-level output during execution",
    )
    run_parser.set_defaults(func=_handle_run)

    # --- reset ---
    reset_parser = subparsers.add_parser(
        "reset",
        help="Reset a graph run",
        description="Reset a repository to its pre-graph-run state.",
    )
    reset_parser.add_argument("graph", help="Graph name or path to YAML file")
    _add_graph_dir_arg(reset_parser)
    _add_target_repo_arg(reset_parser)
    reset_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt",
    )
    reset_parser.set_defaults(func=_handle_reset)

    # --- check ---
    check_parser = subparsers.add_parser(
        "check",
        help="Preflight checks on a target repo",
        description="Run preflight checks on a target repository.",
    )
    _add_target_repo_arg(check_parser)
    check_parser.add_argument(
        "-e",
        "--env",
        default="tmux",
        help="Agent environment to check for (default: tmux)",
    )
    check_parser.set_defaults(func=_handle_check)

    # --- dry-run ---
    dry_run_parser = subparsers.add_parser(
        "dry-run",
        help="Validate graph and print execution plan",
        description="Validate a graph YAML and print the execution plan.",
    )
    dry_run_parser.add_argument("graph", help="Graph name or path to YAML file")
    _add_graph_dir_arg(dry_run_parser)
    _add_target_repo_arg(dry_run_parser)
    dry_run_parser.set_defaults(func=_handle_dry_run)

    # --- list ---
    list_parser = subparsers.add_parser(
        "list",
        help="List available graphs",
        description="List available graphs from a graph directory.",
    )
    list_parser.add_argument(
        "--graph-dir",
        "-g",
        required=True,
        help="Directory to scan for graph YAML files",
    )
    list_parser.set_defaults(func=_handle_list)

    # --- reset-task ---
    reset_task_parser = subparsers.add_parser(
        "reset-task",
        help="Reset the tip task of a workstream",
        description="Reset a task to allow re-execution. Must be the workstream tip.",
    )
    reset_task_parser.add_argument("graph", help="Graph name or path to YAML file")
    _add_graph_dir_arg(reset_task_parser)
    _add_target_repo_arg(reset_task_parser)
    reset_task_group = reset_task_parser.add_mutually_exclusive_group(required=True)
    reset_task_group.add_argument(
        "--task",
        default=None,
        help="Task ID to reset (must be the workstream tip)",
    )
    reset_task_group.add_argument(
        "--workstream",
        default=None,
        help="Workstream ID (auto-detect tip task)",
    )
    reset_task_parser.set_defaults(func=_handle_reset_task)

    # --- teardown-workstream ---
    teardown_ws_parser = subparsers.add_parser(
        "teardown-workstream",
        help="Remove workstream worktree and integration branch",
        description=(
            "Remove worktree and integration infrastructure for a workstream. "
            "All tasks must be reset first."
        ),
    )
    teardown_ws_parser.add_argument("graph", help="Graph name or path to YAML file")
    _add_graph_dir_arg(teardown_ws_parser)
    _add_target_repo_arg(teardown_ws_parser)
    teardown_ws_parser.add_argument(
        "--workstream",
        required=True,
        help="Workstream ID to tear down",
    )
    teardown_ws_parser.set_defaults(func=_handle_teardown_workstream)

    # --- reset-workstream ---
    reset_ws_parser = subparsers.add_parser(
        "reset-workstream",
        help="Reset a merged workstream and its target branch",
        description=(
            "Fully reset a merged workstream, including target branch rollback. "
            "Force-pushes to the target branch (usually main)."
        ),
    )
    reset_ws_parser.add_argument("graph", help="Graph name or path to YAML file")
    _add_graph_dir_arg(reset_ws_parser)
    _add_target_repo_arg(reset_ws_parser)
    reset_ws_parser.add_argument(
        "--workstream",
        required=True,
        help="Workstream ID to reset",
    )
    reset_ws_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt (required: force-pushes to target branch)",
    )
    reset_ws_parser.set_defaults(func=_handle_reset_workstream)

    # --- reset-to ---
    reset_to_parser = subparsers.add_parser(
        "reset-to",
        help="Roll back a graph to a specific task or workstream",
        description=(
            "Roll back a graph to a specific state in a single command. "
            "--after accepts a task ID (keep that task and everything before it) "
            "or a workstream ID (keep that workstream and everything merged "
            "before it). Force-pushes to affected branches."
        ),
    )
    reset_to_parser.add_argument("graph", help="Graph name or path to YAML file")
    _add_graph_dir_arg(reset_to_parser)
    _add_target_repo_arg(reset_to_parser)
    reset_to_parser.add_argument(
        "--after",
        required=True,
        help="Task ID or workstream ID to keep (everything after is removed)",
    )
    reset_to_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt (force-pushes to affected branches)",
    )
    reset_to_parser.set_defaults(func=_handle_reset_to)

    return parser


def main() -> None:
    """CLI entry point registered as the ``agentrelay`` console script."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)
