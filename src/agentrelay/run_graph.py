"""Composition and CLI entry point for running an agentrelay task graph.

Usage::

    python -m agentrelay.run_graph graphs/demo.yaml
    python -m agentrelay.run_graph graphs/demo.yaml --dry-run
    python -m agentrelay.run_graph graphs/demo.yaml --max-concurrency 4 --model claude-opus-4-6

This module provides:

- :func:`run_graph`: async composition function that wires all components and
  runs the orchestrator.
- :func:`dry_run`: validates a graph YAML and prints the execution plan.
- :func:`main`: CLI entry point with argparse.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from agentrelay.ops import git, signals
from agentrelay.orchestrator import (
    Orchestrator,
    OrchestratorConfig,
    OrchestratorOutcome,
    OrchestratorResult,
    build_standard_runner,
    build_standard_workstream_runner,
)
from agentrelay.task_graph import TaskGraph, TaskGraphBuilder
from agentrelay.task_runner.core.runner import TearDownMode
from agentrelay.task_runtime import TaskStatus


def _extract_operational_config(
    raw: dict[str, Any],
) -> tuple[str, bool, Optional[str]]:
    """Pop operational keys from a raw YAML dict before graph parsing.

    The graph YAML may include operational keys (``tmux_session``,
    ``keep_panes``, ``model``) that are not part of the structural graph
    schema.  These must be removed before passing to
    :meth:`TaskGraphBuilder.from_dict` (which rejects unknown keys).

    Args:
        raw: Mutable raw YAML dict.  Modified in place.

    Returns:
        Tuple of ``(tmux_session, keep_panes, model_default)``.
    """
    tmux_session: str = raw.pop("tmux_session", "agentrelay")
    keep_panes: bool = raw.pop("keep_panes", False)
    model: Optional[str] = raw.pop("model", None)
    return tmux_session, keep_panes, model


def _apply_overrides(
    raw: dict[str, Any],
    *,
    tmux_session: Optional[str] = None,
    model: Optional[str] = None,
) -> None:
    """Apply CLI overrides to task dicts in a raw YAML dict.

    Mutates ``raw["tasks"]`` in place.  Creates nested dicts as needed so
    that per-task ``primary_agent`` configurations reflect the overrides.

    Args:
        raw: Mutable raw YAML dict containing a ``"tasks"`` list.
        tmux_session: If set, override every task's tmux session name.
        model: If set, override every task's agent model.
    """
    if tmux_session is None and model is None:
        return
    for task in raw.get("tasks", []):
        if tmux_session is not None:
            agent = task.setdefault("primary_agent", {})
            env = agent.setdefault("environment", {})
            env["session"] = tmux_session
        if model is not None:
            agent = task.setdefault("primary_agent", {})
            agent["model"] = model


def _load_and_prepare_graph(
    graph_path: Path,
    *,
    tmux_session: Optional[str] = None,
    model_override: Optional[str] = None,
) -> tuple[TaskGraph, str, bool]:
    """Load YAML, extract operational config, apply overrides, build graph.

    Args:
        graph_path: Path to the graph YAML file.
        tmux_session: CLI override for tmux session name.
        model_override: CLI override for agent model.

    Returns:
        Tuple of ``(graph, effective_tmux_session, effective_keep_panes)``.
    """
    raw = yaml.safe_load(graph_path.read_text())
    yaml_session, yaml_keep_panes, yaml_model = _extract_operational_config(raw)

    effective_session = tmux_session if tmux_session is not None else yaml_session
    effective_model = model_override if model_override is not None else yaml_model

    _apply_overrides(raw, tmux_session=effective_session, model=effective_model)

    graph = TaskGraphBuilder.from_dict(raw)
    return graph, effective_session, yaml_keep_panes


def _record_run_start(repo_path: Path, graph_name: str) -> None:
    """Write run_info.json with start HEAD and timestamp.

    This file is read by ``reset_graph`` to know what SHA to reset to.

    Args:
        repo_path: Path to the repository root.
        graph_name: Name of the task graph being executed.
    """
    workflow_dir = repo_path / ".workflow" / graph_name
    start_head = git.rev_parse_head(repo_path)
    signals.write_json(
        workflow_dir,
        "run_info.json",
        {
            "start_head": start_head,
            "started_at": datetime.now(timezone.utc).isoformat(),
        },
    )


async def run_graph(
    graph_path: Path,
    repo_path: Path,
    *,
    tmux_session: Optional[str] = None,
    keep_panes: bool = False,
    model_override: Optional[str] = None,
    config: Optional[OrchestratorConfig] = None,
) -> OrchestratorResult:
    """Build all components from a graph YAML and run the orchestrator.

    This is the top-level composition function that wires
    :func:`build_standard_runner`, :func:`build_standard_workstream_runner`,
    and :class:`Orchestrator` together.

    Args:
        graph_path: Path to the graph YAML file.
        repo_path: Path to the repository root.
        tmux_session: Override tmux session name (overrides YAML value).
        keep_panes: Keep tmux panes open after task completion.
        model_override: Override model for all agents (overrides YAML value).
        config: Orchestrator configuration.  Defaults to
            :class:`OrchestratorConfig` defaults.

    Returns:
        OrchestratorResult: Terminal orchestration result.
    """
    if config is None:
        config = OrchestratorConfig()

    graph, _, yaml_keep_panes = _load_and_prepare_graph(
        graph_path, tmux_session=tmux_session, model_override=model_override
    )
    effective_keep_panes = keep_panes or yaml_keep_panes

    assert graph.name is not None, "Graph must have a name"

    _record_run_start(repo_path, graph.name)

    task_runner = build_standard_runner(
        repo_path=repo_path,
        graph_name=graph.name,
        graph=graph,
        keep_panes=effective_keep_panes,
    )
    workstream_runner = build_standard_workstream_runner(
        repo_path=repo_path,
        graph_name=graph.name,
    )
    orchestrator = Orchestrator(
        graph=graph,
        task_runner=task_runner,
        workstream_runner=workstream_runner,
        config=config,
    )
    return await orchestrator.run()


def dry_run(graph_path: Path) -> None:
    """Validate a graph YAML and print the execution plan.

    Args:
        graph_path: Path to the graph YAML file.
    """
    graph, _, _ = _load_and_prepare_graph(graph_path)

    print(f"Graph: {graph.name}")
    print(f"Tasks: {len(graph.task_ids())}")
    print(f"Workstreams: {len(graph.workstream_ids())}")

    print("\nWorkstreams:")
    for ws_id in graph.workstream_ids():
        ws = graph.workstream(ws_id)
        parent = ws.parent_workstream_id or "(root)"
        print(
            f"  {ws_id}  parent={parent}  base={ws.base_branch}  target={ws.merge_target_branch}"
        )

    print("\nExecution order:")
    for task_id in graph.task_ids():
        task = graph.task(task_id)
        deps = graph.dependency_ids(task_id)
        dep_str = ", ".join(deps) if deps else "(none)"
        desc = task.description or ""
        if len(desc) > 60:
            desc = desc[:57] + "..."
        print(f"  {task_id}")
        print(f"    role={task.role.value}  workstream={task.workstream_id}")
        print(f"    deps: {dep_str}")
        if desc:
            print(f"    desc: {desc}")

    roots = graph.roots()
    leaves = graph.leaves()
    print(f"\nRoots (no deps): {', '.join(roots)}")
    print(f"Leaves (no dependents): {', '.join(leaves)}")


def _build_config_from_args(args: argparse.Namespace) -> OrchestratorConfig:
    """Build an OrchestratorConfig from parsed CLI arguments.

    Only overrides fields that were explicitly provided on the command line.

    Args:
        args: Parsed CLI arguments.

    Returns:
        OrchestratorConfig with CLI overrides applied.
    """
    kwargs: dict[str, Any] = {}
    if args.max_concurrency is not None:
        kwargs["max_concurrency"] = args.max_concurrency
    if args.max_task_attempts is not None:
        kwargs["max_task_attempts"] = args.max_task_attempts
    if args.teardown_mode is not None:
        kwargs["task_teardown_mode"] = TearDownMode(args.teardown_mode)
    return OrchestratorConfig(**kwargs)


def _print_result(result: OrchestratorResult) -> None:
    """Print a human-readable summary of the orchestration result.

    Args:
        result: Terminal orchestration result.
    """
    print(f"\nOutcome: {result.outcome.value}")
    if result.fatal_error:
        print(f"Fatal error:\n{result.fatal_error}")

    succeeded = []
    failed = []
    for task_id, runtime in result.task_runtimes.items():
        if runtime.state.status is TaskStatus.PR_MERGED:
            succeeded.append(task_id)
        elif runtime.state.status is TaskStatus.FAILED:
            failed.append(task_id)

    if succeeded:
        print(f"Succeeded: {', '.join(succeeded)}")
    if failed:
        print(f"Failed: {', '.join(failed)}")
        for task_id in failed:
            error = result.task_runtimes[task_id].state.error
            if error:
                print(f"  {task_id}: {error}")


def main() -> None:
    """CLI entry point for running an agentrelay task graph."""
    parser = argparse.ArgumentParser(
        description="Run an agentrelay task graph.",
    )
    parser.add_argument(
        "graph",
        help="Path to graph YAML file",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=None,
        help="Maximum concurrent task attempts (default: 1)",
    )
    parser.add_argument(
        "--max-task-attempts",
        type=int,
        default=None,
        help="Maximum attempts per task (default: 1)",
    )
    parser.add_argument(
        "--teardown-mode",
        choices=["always", "never", "on_success"],
        default=None,
        help="When to tear down task resources (default: on_success)",
    )
    parser.add_argument(
        "--tmux-session",
        default=None,
        help="Override tmux session name for all agents",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override model for all agents",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate graph and print execution plan without running",
    )
    args = parser.parse_args()

    graph_path = Path(args.graph).resolve()
    if not graph_path.is_file():
        print(f"Error: graph file not found: {graph_path}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        dry_run(graph_path)
        return

    config = _build_config_from_args(args)
    repo_path = Path.cwd()

    result = asyncio.run(
        run_graph(
            graph_path=graph_path,
            repo_path=repo_path,
            tmux_session=args.tmux_session,
            model_override=args.model,
            config=config,
        )
    )
    _print_result(result)

    if result.outcome != OrchestratorOutcome.SUCCEEDED:
        sys.exit(1)


if __name__ == "__main__":
    main()
