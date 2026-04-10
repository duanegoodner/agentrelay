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
import dataclasses
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from agentrelay.ops import docker as docker_ops
from agentrelay.ops import git, signals, tmux
from agentrelay.orchestrator import (
    Orchestrator,
    OrchestratorConfig,
    OrchestratorOutcome,
    OrchestratorResult,
    build_integration_auto_merger,
    build_integration_merge_checker,
    build_standard_runner,
    build_standard_workstream_runner,
)
from agentrelay.output import ConsoleListener, print_summary
from agentrelay.sandbox import (
    AnthropicCredential,
    CredentialProvider,
    FileCredentialProvider,
    SandboxType,
)
from agentrelay.task_graph import TaskGraph, TaskGraphBuilder
from agentrelay.task_runner.core.runner import TearDownMode
from agentrelay.tools import ToolValidationError, validate_tools


def _extract_operational_config(
    raw: dict[str, Any],
) -> tuple[
    bool,
    Optional[str],
    tuple[str, ...],
    Optional[str],
    Optional[bool],
    Optional[bool],
]:
    """Pop operational keys from a raw YAML dict before graph parsing.

    The graph YAML may include operational keys (``keep_panes``, ``model``,
    ``tools``, ``anthropic_credential``, ``fail_fast_on_workstream_error``,
    ``fail_fast_on_internal_error``) that are not part of the structural
    graph schema.  These must be removed before passing to
    :meth:`TaskGraphBuilder.from_dict` (which rejects unknown keys).

    Args:
        raw: Mutable raw YAML dict.  Modified in place.

    Returns:
        Tuple of ``(keep_panes, model_default, tools,
        anthropic_credential, fail_fast_on_workstream_error,
        fail_fast_on_internal_error)``.
        ``tools`` defaults to an empty tuple.
        ``anthropic_credential`` is ``None`` if not specified.
        ``fail_fast_on_workstream_error`` is ``None`` if not specified.
        ``fail_fast_on_internal_error`` is ``None`` if not specified.
    """
    keep_panes: bool = raw.pop("keep_panes", False)
    model: Optional[str] = raw.pop("model", None)
    raw_tools = raw.pop("tools", None)
    tools: tuple[str, ...] = tuple(raw_tools) if raw_tools else ()
    anthropic_credential: Optional[str] = raw.pop("anthropic_credential", None)
    raw_fail_fast: Optional[bool] = raw.pop("fail_fast_on_workstream_error", None)
    if raw_fail_fast is not None and not isinstance(raw_fail_fast, bool):
        raise ValueError(
            "Invalid graph schema at 'fail_fast_on_workstream_error': must be a boolean"
        )
    raw_fail_fast_internal: Optional[bool] = raw.pop(
        "fail_fast_on_internal_error", None
    )
    if raw_fail_fast_internal is not None and not isinstance(
        raw_fail_fast_internal, bool
    ):
        raise ValueError(
            "Invalid graph schema at 'fail_fast_on_internal_error': must be a boolean"
        )
    return (
        keep_panes,
        model,
        tools,
        anthropic_credential,
        raw_fail_fast,
        raw_fail_fast_internal,
    )


def _apply_overrides(
    raw: dict[str, Any],
    *,
    tmux_session: Optional[str] = None,
    model: Optional[str] = None,
    sandbox: Optional[str] = None,
) -> None:
    """Apply CLI overrides to task dicts in a raw YAML dict.

    Mutates ``raw["tasks"]`` in place.  Creates nested dicts as needed so
    that per-task ``primary_agent`` configurations reflect the overrides.

    Args:
        raw: Mutable raw YAML dict containing a ``"tasks"`` list.
        tmux_session: If set, override every task's tmux session name.
        model: If set, override every task's agent model.
        sandbox: If set, override sandbox type (``"oci"`` or ``"none"``)
            for all tasks.  Applied at task level and agent level so that
            agent-level YAML cannot override the CLI flag.
    """
    if tmux_session is None and model is None and sandbox is None:
        return
    for task in raw.get("tasks", []):
        if tmux_session is not None:
            agent = task.setdefault("primary_agent", {})
            env = agent.setdefault("environment", {})
            env["session"] = tmux_session
        if model is not None:
            agent = task.setdefault("primary_agent", {})
            agent["model"] = model
        if sandbox is not None:
            # Task level — overrides graph and workstream inheritance.
            iso = task.setdefault("isolation", {})
            iso["sandbox"] = sandbox
            # Primary agent level — overrides any agent-level YAML.
            if "primary_agent" in task:
                agent_iso = task["primary_agent"].setdefault("isolation", {})
                agent_iso["sandbox"] = sandbox
            # Review agent level — YAML structure is review.agent.isolation.
            if "review" in task and isinstance(task["review"], dict):
                review_agent = task["review"].setdefault("agent", {})
                review_iso = review_agent.setdefault("isolation", {})
                review_iso["sandbox"] = sandbox


def _load_and_prepare_graph(
    graph_path: Path,
    *,
    tmux_session: Optional[str] = None,
    model_override: Optional[str] = None,
    sandbox_override: Optional[str] = None,
) -> tuple[
    TaskGraph,
    bool,
    tuple[str, ...],
    Optional[str],
    Optional[bool],
    Optional[bool],
]:
    """Load YAML, extract operational config, apply overrides, build graph.

    Args:
        graph_path: Path to the graph YAML file.
        tmux_session: Resolved tmux session name to apply to all tasks.
        model_override: CLI override for agent model.
        sandbox_override: CLI override for sandbox type (``"oci"`` or
            ``"none"``).  Applied to every task when set.

    Returns:
        Tuple of ``(graph, keep_panes, tools, anthropic_credential_name,
        fail_fast_on_workstream_error, fail_fast_on_internal_error)``.
    """
    raw = yaml.safe_load(graph_path.read_text())
    (
        yaml_keep_panes,
        yaml_model,
        tools,
        yaml_anthropic,
        yaml_fail_fast,
        yaml_fail_fast_internal,
    ) = _extract_operational_config(raw)

    effective_model = model_override if model_override is not None else yaml_model

    _apply_overrides(
        raw,
        tmux_session=tmux_session,
        model=effective_model,
        sandbox=sandbox_override,
    )

    graph = TaskGraphBuilder.from_dict(raw)
    return (
        graph,
        yaml_keep_panes,
        tools,
        yaml_anthropic,
        yaml_fail_fast,
        yaml_fail_fast_internal,
    )


class _ConflictError(RuntimeError):
    """Raised when leftover state from a previous run would conflict."""


def _check_for_conflicts(repo_path: Path, graph_name: str) -> None:
    """Check for leftover state that would conflict with a new run.

    Raises:
        _ConflictError: If ``.workflow/<graph>`` or ``.worktrees/<graph>``
            already exists.
    """
    workflow_dir = repo_path / ".workflow" / graph_name
    worktree_dir = repo_path / ".worktrees" / graph_name
    conflicts = []
    if workflow_dir.is_dir():
        conflicts.append(str(workflow_dir))
    if worktree_dir.is_dir():
        conflicts.append(str(worktree_dir))
    if conflicts:
        dirs = ", ".join(conflicts)
        raise _ConflictError(
            f"Leftover state from a previous run of graph '{graph_name}': {dirs}\n"
            f"Run `agentrelay reset <graph.yaml>` to clean up first."
        )


class _SessionError(RuntimeError):
    """Raised when the tmux session is not specified or doesn't exist."""


def _validate_tmux_sessions(graph: TaskGraph) -> None:
    """Validate that all tasks have a tmux session and it exists.

    Raises:
        _SessionError: If any task has an empty session or the session
            doesn't exist.
    """
    sessions_seen: set[str] = set()
    for task_id in graph.task_ids():
        task = graph.task(task_id)
        session = task.primary_agent.environment.session
        if not session:
            raise _SessionError(
                f"Task '{task_id}' has no tmux session specified.\n"
                "Use --tmux-session on the CLI or run from inside a tmux session."
            )
        sessions_seen.add(session)

    for session in sorted(sessions_seen):
        if not tmux.has_session(session):
            raise _SessionError(
                f"Tmux session '{session}' does not exist.\n"
                f"Create it first: tmux new-session -d -s {session}"
            )


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


def _copy_graph_yaml(repo_path: Path, graph_name: str, graph_path: Path) -> None:
    """Copy the source graph YAML into the workflow directory.

    Writes a byte-for-byte copy so that comments and formatting are
    preserved.  The copy is immutable during the run and serves as a
    record of "what the graph was at orchestrator launch."  Agents read
    this file to understand the full task DAG.

    Args:
        repo_path: Path to the repository root.
        graph_name: Name of the task graph being executed.
        graph_path: Resolved path to the source graph YAML file.
    """
    dest = repo_path / ".workflow" / graph_name / "graph.yaml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(graph_path.read_bytes())


def _any_task_uses_oci(graph: TaskGraph) -> bool:
    """Check whether any task in the graph uses OCI sandbox isolation.

    Args:
        graph: Validated immutable task graph.

    Returns:
        ``True`` if at least one task has ``SandboxType.OCI``.
    """
    for task_id in graph.task_ids():
        isolation = graph.task(task_id).primary_agent.isolation
        if isolation is not None and isolation.sandbox_type == SandboxType.OCI:
            return True
    return False


def _resolve_fail_fast(
    cli_value: Optional[bool],
    yaml_value: Optional[bool],
) -> Optional[bool]:
    """Resolve ``fail_fast_on_workstream_error``: CLI > YAML > ``None``.

    Returns ``None`` when neither CLI nor YAML specifies a value,
    leaving the :class:`OrchestratorConfig` default in effect.
    """
    if cli_value is not None:
        return cli_value
    return yaml_value


async def run_graph(
    graph_path: Path,
    repo_path: Path,
    *,
    tmux_session: Optional[str] = None,
    keep_panes: bool = False,
    model_override: Optional[str] = None,
    config: Optional[OrchestratorConfig] = None,
    fail_fast_on_workstream_error: Optional[bool] = None,
    fail_fast_on_internal_error: Optional[bool] = None,
    credential_provider: Optional[CredentialProvider] = None,
    anthropic_credential_name: Optional[str] = None,
    sandbox_override: Optional[str] = None,
    verbose: bool = False,
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
        fail_fast_on_workstream_error: CLI override for
            ``OrchestratorConfig.fail_fast_on_workstream_error``.
            When ``None``, falls back to graph YAML, then config default.
        fail_fast_on_internal_error: CLI override for
            ``OrchestratorConfig.fail_fast_on_internal_error``.
            When ``None``, falls back to graph YAML, then config default.
        credential_provider: Credential provider for sandboxed agents.
            When ``None``, :class:`NullCredentialProvider` is used.
        anthropic_credential_name: Name of the Anthropic credential to
            use from the credentials YAML ``anthropic`` section.  CLI
            override; falls back to graph YAML ``anthropic_credential``.
        sandbox_override: CLI override for sandbox type (``"oci"`` or
            ``"none"``).  When set, overrides sandbox config for all tasks.
        verbose: Show detailed step-level output during execution.

    Returns:
        OrchestratorResult: Terminal orchestration result.
    """
    if config is None:
        config = OrchestratorConfig()

    # Resolve tmux session: CLI flag > auto-detect > error.
    if tmux_session is None:
        tmux_session = tmux.current_session()
    if tmux_session is None:
        raise _SessionError(
            "No tmux session specified and not running inside tmux.\n"
            "Either run from inside a tmux session or use --tmux-session."
        )

    (
        graph,
        yaml_keep_panes,
        tools,
        yaml_anthropic_name,
        yaml_fail_fast,
        yaml_fail_fast_internal,
    ) = _load_and_prepare_graph(
        graph_path,
        tmux_session=tmux_session,
        model_override=model_override,
        sandbox_override=sandbox_override,
    )
    effective_keep_panes = keep_panes or yaml_keep_panes

    # Resolve fail_fast_on_workstream_error: CLI > YAML > config default.
    effective_fail_fast = _resolve_fail_fast(
        fail_fast_on_workstream_error, yaml_fail_fast
    )
    if effective_fail_fast is not None:
        config = dataclasses.replace(
            config, fail_fast_on_workstream_error=effective_fail_fast
        )

    # Resolve fail_fast_on_internal_error: CLI > YAML > config default.
    effective_fail_fast_internal = _resolve_fail_fast(
        fail_fast_on_internal_error, yaml_fail_fast_internal
    )
    if effective_fail_fast_internal is not None:
        config = dataclasses.replace(
            config, fail_fast_on_internal_error=effective_fail_fast_internal
        )

    assert graph.name is not None, "Graph must have a name"

    _check_for_conflicts(repo_path, graph.name)
    _validate_tmux_sessions(graph)
    validate_tools(tools)
    _record_run_start(repo_path, graph.name)
    _copy_graph_yaml(repo_path, graph.name, graph_path)

    # Resolve Anthropic credential: CLI flag > graph YAML default > auto-select.
    effective_anthropic_name = anthropic_credential_name or yaml_anthropic_name
    anthropic_credential: Optional[AnthropicCredential] = None
    if isinstance(credential_provider, FileCredentialProvider):
        anthropic_credential = credential_provider.resolve_anthropic(
            effective_anthropic_name
        )

    # Create Docker network if any task uses OCI sandbox.
    uses_oci = _any_task_uses_oci(graph)
    network_name = f"agentrelay-{graph.name}" if uses_oci else None

    if network_name is not None:
        if not docker_ops.is_available():
            raise RuntimeError(
                "Docker is required for OCI sandbox but is not available"
            )
        docker_ops.network_create(network_name)

    try:
        task_runner = build_standard_runner(
            repo_path=repo_path,
            graph_name=graph.name,
            graph=graph,
            keep_panes=effective_keep_panes,
            tools=tools,
            credential_provider=credential_provider,
            anthropic_credential=anthropic_credential,
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
            listener=ConsoleListener(verbose=verbose),
            integration_merge_checker=build_integration_merge_checker(),
            integration_auto_merger=build_integration_auto_merger(),
        )
        return await orchestrator.run()
    finally:
        if network_name is not None:
            try:
                docker_ops.network_remove(network_name)
            except Exception:
                pass  # Best-effort cleanup


def dry_run(graph_path: Path) -> None:
    """Validate a graph YAML and print the execution plan.

    Args:
        graph_path: Path to the graph YAML file.
    """
    graph, _, tools, _, _, _ = _load_and_prepare_graph(graph_path)

    print(f"Graph: {graph.name}")
    print(f"Tasks: {len(graph.task_ids())}")
    print(f"Workstreams: {len(graph.workstream_ids())}")
    if tools:
        print(f"Tools: {', '.join(tools)}")

    print("\nWorkstreams:")
    for ws_id in graph.workstream_ids():
        ws = graph.workstream(ws_id)
        parent = ws.parent_workstream_id or "(root)"
        auto = "  auto_merge" if ws.auto_merge else ""
        print(
            f"  {ws_id}  parent={parent}  base={ws.base_branch}  target={ws.merge_target_branch}{auto}"
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


def _dry_run_conflict_check(repo_path: Path, graph_name: str) -> None:
    """Print conflict warnings during dry-run (non-fatal)."""
    workflow_dir = repo_path / ".workflow" / graph_name
    worktree_dir = repo_path / ".worktrees" / graph_name
    if workflow_dir.is_dir() or worktree_dir.is_dir():
        print(f"\nWARNING: Leftover state from a previous run of '{graph_name}':")
        if workflow_dir.is_dir():
            print(f"  {workflow_dir}")
        if worktree_dir.is_dir():
            print(f"  {worktree_dir}")
        print("  Run reset_graph to clean up before a real run.")


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
    print_summary(result)


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for ``run_graph``.

    Extracted from :func:`main` to allow direct testing of argument
    parsing without invoking the full CLI entry point.
    """
    parser = argparse.ArgumentParser(
        description="Run an agentrelay task graph.",
    )
    parser.add_argument(
        "graph",
        help="Path to graph YAML file",
    )
    parser.add_argument(
        "-c",
        "--max-concurrency",
        type=int,
        default=None,
        help="Maximum concurrent tasks (default: 1)",
    )
    parser.add_argument(
        "-a",
        "--max-task-attempts",
        type=int,
        default=None,
        help="Maximum attempts per task (default: 1)",
    )
    parser.add_argument(
        "-T",
        "--teardown-mode",
        choices=["always", "never", "on_success"],
        default=None,
        help="When to tear down task resources (default: on_success)",
    )
    parser.add_argument(
        "-s",
        "--tmux-session",
        default=None,
        help="Override tmux session name (auto-detected from current tmux session)",
    )
    parser.add_argument(
        "-m",
        "--model",
        default=None,
        help="Override model for all agents",
    )
    parser.add_argument(
        "-C",
        "--credentials",
        default=None,
        help="Path to credentials YAML file for sandboxed agents",
    )
    parser.add_argument(
        "-A",
        "--anthropic-credential",
        default=None,
        help="Name of Anthropic credential from credentials YAML file",
    )
    parser.add_argument(
        "-S",
        "--sandbox",
        choices=["oci", "none"],
        default=None,
        help="Override sandbox type for all tasks (oci or none)",
    )
    parser.add_argument(
        "-W",
        "--fail-fast-workstream",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Stop preparing new workstreams after a workstream failure (default: false)",
    )
    parser.add_argument(
        "-I",
        "--fail-fast-internal",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Stop scheduling immediately on internal orchestrator errors (default: true)",
    )
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Validate graph and print execution plan without running",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed step-level output during execution",
    )
    return parser


def main() -> None:
    """CLI entry point for running an agentrelay task graph."""
    parser = _build_parser()
    args = parser.parse_args()

    graph_path = Path(args.graph).resolve()
    if not graph_path.is_file():
        print(f"Error: graph file not found: {graph_path}", file=sys.stderr)
        sys.exit(1)

    repo_path = Path.cwd()

    if args.dry_run:
        dry_run(graph_path)
        # Also check for conflicts in the current directory.
        raw = yaml.safe_load(graph_path.read_text())
        graph_name = raw.get("name")
        if graph_name:
            _dry_run_conflict_check(repo_path, graph_name)
        return

    credential_provider: Optional[CredentialProvider] = None
    if args.credentials is not None:
        creds_path = Path(args.credentials).resolve()
        if not creds_path.is_file():
            print(f"Error: credentials file not found: {creds_path}", file=sys.stderr)
            sys.exit(1)
        credential_provider = FileCredentialProvider(creds_path)

    config = _build_config_from_args(args)

    try:
        result = asyncio.run(
            run_graph(
                graph_path=graph_path,
                repo_path=repo_path,
                tmux_session=args.tmux_session,
                model_override=args.model,
                config=config,
                fail_fast_on_workstream_error=args.fail_fast_workstream,
                fail_fast_on_internal_error=args.fail_fast_internal,
                credential_provider=credential_provider,
                anthropic_credential_name=args.anthropic_credential,
                sandbox_override=args.sandbox,
                verbose=args.verbose,
            )
        )
    except (
        _ConflictError,
        _SessionError,
        ToolValidationError,
        ValueError,
        RuntimeError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    _print_result(result)

    if result.outcome != OrchestratorOutcome.SUCCEEDED:
        sys.exit(1)


if __name__ == "__main__":
    main()
