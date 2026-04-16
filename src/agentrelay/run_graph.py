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
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from agentrelay.ops import docker as docker_ops
from agentrelay.ops import git, signals, tmux
from agentrelay.orchestrator import (
    GraphProbe,
    Orchestrator,
    OrchestratorConfig,
    OrchestratorOutcome,
    OrchestratorResult,
    TaskRuntimeBuilder,
    WorkstreamRuntimeBuilder,
    build_integration_auto_merger,
    build_integration_merge_checker,
    build_standard_runner,
    build_standard_workstream_runner,
    build_task_pr_prober,
    probe_graph_state,
)
from agentrelay.output import (
    ConsoleListener,
    ResumeTaskInfo,
    print_config_warnings,
    print_override_report,
    print_resume_summary,
    print_summary,
)
from agentrelay.reset_graph import _find_latest_run_dir
from agentrelay.resolved_validation import validate_frozen_tasks
from agentrelay.sandbox import (
    AnthropicCredential,
    CredentialProvider,
    FileCredentialProvider,
    SandboxType,
)
from agentrelay.task_graph import TaskGraph, TaskGraphBuilder
from agentrelay.task_runner.core.runner import TearDownMode
from agentrelay.task_runtime import TaskRuntime
from agentrelay.tools import ToolValidationError, validate_tools
from agentrelay.workstream import WorkstreamRuntime, WorkstreamStatus


@dataclasses.dataclass(frozen=True)
class OperationalConfig:
    """Graph-level operational settings extracted from YAML.

    These keys are popped from the raw YAML dict before graph parsing
    (which rejects unknown keys).  ``None`` means "not specified in YAML;
    fall back to CLI or default."
    """

    keep_panes: bool = False
    model: Optional[str] = None
    tools: tuple[str, ...] = ()
    anthropic_credential: Optional[str] = None
    fail_fast_on_workstream_error: Optional[bool] = None
    fail_fast_on_internal_error: Optional[bool] = None
    max_concurrency: Optional[int] = None
    max_task_attempts: Optional[int] = None
    teardown_mode: Optional[str] = None


_VALID_TEARDOWN_MODES = {"always", "never", "on_success"}


def _extract_operational_config(raw: dict[str, Any]) -> OperationalConfig:
    """Pop operational keys from a raw YAML dict before graph parsing.

    Args:
        raw: Mutable raw YAML dict.  Modified in place.

    Returns:
        OperationalConfig with values from the YAML (or defaults).
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

    raw_concurrency: Optional[int] = raw.pop("max_concurrency", None)
    if raw_concurrency is not None:
        if not isinstance(raw_concurrency, int) or raw_concurrency < 1:
            raise ValueError(
                "Invalid graph schema at 'max_concurrency': must be an integer >= 1"
            )

    raw_attempts: Optional[int] = raw.pop("max_task_attempts", None)
    if raw_attempts is not None:
        if not isinstance(raw_attempts, int) or raw_attempts < 1:
            raise ValueError(
                "Invalid graph schema at 'max_task_attempts': must be an integer >= 1"
            )

    raw_teardown: Optional[str] = raw.pop("teardown_mode", None)
    if raw_teardown is not None:
        if raw_teardown not in _VALID_TEARDOWN_MODES:
            raise ValueError(
                f"Invalid graph schema at 'teardown_mode': must be one of "
                f"{sorted(_VALID_TEARDOWN_MODES)}, got {raw_teardown!r}"
            )

    return OperationalConfig(
        keep_panes=keep_panes,
        model=model,
        tools=tools,
        anthropic_credential=anthropic_credential,
        fail_fast_on_workstream_error=raw_fail_fast,
        fail_fast_on_internal_error=raw_fail_fast_internal,
        max_concurrency=raw_concurrency,
        max_task_attempts=raw_attempts,
        teardown_mode=raw_teardown,
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
) -> tuple[TaskGraph, OperationalConfig]:
    """Load YAML, extract operational config, apply overrides, build graph.

    Args:
        graph_path: Path to the graph YAML file.
        tmux_session: Resolved tmux session name to apply to all tasks.
        model_override: CLI override for agent model.
        sandbox_override: CLI override for sandbox type (``"oci"`` or
            ``"none"``).  Applied to every task when set.

    Returns:
        Tuple of ``(graph, ops_config)``.
    """
    raw = yaml.safe_load(graph_path.read_text())
    ops = _extract_operational_config(raw)

    effective_model = model_override if model_override is not None else ops.model

    _apply_overrides(
        raw,
        tmux_session=tmux_session,
        model=effective_model,
        sandbox=sandbox_override,
    )

    graph = TaskGraphBuilder.from_dict(raw)
    return (graph, ops)


@dataclasses.dataclass(frozen=True)
class _RunContext:
    """Result of resolving whether this is a fresh or resume run.

    Attributes:
        run_dir: Path to the run directory for this session.
        prior_run_dir: Path to the prior run directory, or ``None`` for
            fresh runs.
        is_resume: ``True`` if resuming from a prior run.
        run_number: Integer run number for this session.
        prior_run_number: Integer run number of the prior run, or ``None``.
    """

    run_dir: Path
    prior_run_dir: Optional[Path]
    is_resume: bool
    run_number: int
    prior_run_number: Optional[int]


def _resolve_run_context(repo_path: Path, graph_name: str) -> _RunContext:
    """Detect whether this is a fresh or resume run and create the run dir.

    If ``.workflow/<graph>/`` does not exist, creates ``runs/0/`` (fresh).
    If it exists, finds the latest run directory and creates
    ``runs/<N+1>/`` (resume).

    Args:
        repo_path: Path to the repository root.
        graph_name: Name of the task graph being executed.

    Returns:
        _RunContext describing the run directory and resume state.

    Raises:
        RuntimeError: If the workflow directory exists but contains no
            valid run directories.
    """
    workflow_dir = repo_path / ".workflow" / graph_name
    if not workflow_dir.is_dir():
        run_dir = workflow_dir / "runs" / "0"
        run_dir.mkdir(parents=True, exist_ok=True)
        return _RunContext(
            run_dir=run_dir,
            prior_run_dir=None,
            is_resume=False,
            run_number=0,
            prior_run_number=None,
        )

    prior_run_dir = _find_latest_run_dir(workflow_dir)
    if prior_run_dir is None:
        raise RuntimeError(
            f"Workflow directory exists but has no run directories: {workflow_dir}\n"
            "Run `agentrelay reset` to clean up, or remove the directory manually."
        )
    prior_run_number = int(prior_run_dir.name)
    new_run_number = prior_run_number + 1
    run_dir = workflow_dir / "runs" / str(new_run_number)
    run_dir.mkdir(parents=True, exist_ok=True)
    return _RunContext(
        run_dir=run_dir,
        prior_run_dir=prior_run_dir,
        is_resume=True,
        run_number=new_run_number,
        prior_run_number=prior_run_number,
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


def _record_run_start(
    run_dir: Path,
    repo_path: Path,
    *,
    start_head: Optional[str] = None,
) -> None:
    """Write run_info.json with start HEAD and timestamp.

    This file is read by ``reset_graph`` to know what SHA to reset to.

    Args:
        run_dir: Path to the per-run directory.
        repo_path: Path to the repository root (for ``git rev-parse``).
        start_head: Override for the start HEAD SHA.  When resuming,
            pass the prior run's ``start_head`` so that
            ``agentrelay reset`` always finds the original pre-graph
            HEAD regardless of how many resume cycles have occurred.
            When ``None``, reads from ``git rev-parse HEAD``.
    """
    if start_head is None:
        start_head = git.rev_parse_head(repo_path)
    signals.write_json(
        run_dir,
        "run_info.json",
        {
            "start_head": start_head,
            "started_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def _read_prior_start_head(prior_run_dir: Path) -> str:
    """Read ``start_head`` from a prior run's ``run_info.json``.

    Args:
        prior_run_dir: Path to the prior run directory.

    Returns:
        The ``start_head`` SHA string.

    Raises:
        FileNotFoundError: If ``run_info.json`` does not exist.
        KeyError: If ``start_head`` is missing from the JSON.
    """
    path = prior_run_dir / "run_info.json"
    data = json.loads(path.read_text())
    return str(data["start_head"])


def _record_run_config(
    run_dir: Path,
    config: OrchestratorConfig,
    *,
    keep_panes: bool,
    model: Optional[str],
    sandbox: Optional[str],
    anthropic_credential: Optional[str],
    verbose: bool,
) -> None:
    """Write run_config.json with the effective resolved configuration.

    Records the fully resolved configuration after CLI > YAML > default
    precedence has been applied.  This is the authoritative record of
    what settings were actually used for a run.

    Args:
        run_dir: Path to the per-run directory.
        config: Fully resolved orchestrator configuration.
        keep_panes: Effective keep_panes setting.
        model: Model override (from CLI or graph YAML), or None for default.
        sandbox: Sandbox override (from CLI), or None for default.
        anthropic_credential: Resolved Anthropic credential name, or None.
        verbose: Whether verbose output is enabled.
    """
    signals.write_json(
        run_dir,
        "run_config.json",
        {
            "max_concurrency": config.max_concurrency,
            "max_task_attempts": config.max_task_attempts,
            "task_teardown_mode": config.task_teardown_mode.value,
            "fail_fast_on_internal_error": config.fail_fast_on_internal_error,
            "fail_fast_on_workstream_error": config.fail_fast_on_workstream_error,
            "keep_panes": keep_panes,
            "model": model,
            "sandbox": sandbox,
            "anthropic_credential": anthropic_credential,
            "verbose": verbose,
        },
    )


def _copy_graph_yaml(run_dir: Path, graph_path: Path) -> None:
    """Copy the source graph YAML into the run directory.

    Writes a byte-for-byte copy so that comments and formatting are
    preserved.  The copy is immutable during the run and serves as a
    record of "what the graph was at orchestrator launch."  Agents read
    this file to understand the full task DAG.

    Args:
        run_dir: Path to the per-run directory.
        graph_path: Resolved path to the source graph YAML file.
    """
    dest = run_dir / "graph.yaml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(graph_path.read_bytes())


# ---------------------------------------------------------------------------
# Resume helpers
# ---------------------------------------------------------------------------


def _copy_frozen_artifacts(
    prior_run_dir: Path,
    new_run_dir: Path,
    probe: GraphProbe,
) -> None:
    """Copy frozen task and workstream artifacts from a prior run to a new run.

    For each frozen task (has a ``resolved.json``), copies:
    - ``resolved.json``
    - ``outputs.json`` (if present — needed for downstream ``inputs_from``)
    - ``status/`` signal files (so ``_read_task_status_from_signals`` returns
      the correct terminal status)

    For each non-PENDING workstream, copies all signal files (and
    ``resolved.json`` if present).  Without these files the orchestrator
    cannot read the correct workstream status — for example, a
    ``PR_CREATED`` workstream would appear PENDING, and
    ``_refresh_workstream_terminal_states`` would try to write
    ``merge_ready`` to a missing ``signal_dir``.

    Args:
        prior_run_dir: Path to the prior run directory.
        new_run_dir: Path to the new run directory.
        probe: Probe result from the prior run.
    """
    for task_id, task_probe in probe.task_probes.items():
        if task_probe.resolved is None:
            continue
        src_dir = prior_run_dir / "signals" / task_id
        dst_dir = new_run_dir / "signals" / task_id
        dst_dir.mkdir(parents=True, exist_ok=True)

        # Copy resolved.json.
        src_resolved = src_dir / "resolved.json"
        if src_resolved.is_file():
            shutil.copy2(src_resolved, dst_dir / "resolved.json")

        # Copy outputs.json (needed for downstream inputs_from resolution).
        src_outputs = src_dir / "outputs.json"
        if src_outputs.is_file():
            shutil.copy2(src_outputs, dst_dir / "outputs.json")

        # Copy status signal files.
        src_status = src_dir / "status"
        if src_status.is_dir():
            dst_status = dst_dir / "status"
            dst_status.mkdir(parents=True, exist_ok=True)
            for signal_file in src_status.iterdir():
                if signal_file.is_file():
                    shutil.copy2(signal_file, dst_status / signal_file.name)

    for ws_id, ws_probe in probe.workstream_probes.items():
        if ws_probe.status == WorkstreamStatus.PENDING:
            continue
        src_dir = prior_run_dir / "workstreams" / ws_id
        if not src_dir.is_dir():
            continue
        dst_dir = new_run_dir / "workstreams" / ws_id
        dst_dir.mkdir(parents=True, exist_ok=True)

        for item in src_dir.iterdir():
            if item.is_file():
                shutil.copy2(item, dst_dir / item.name)


def _build_resume_runtimes(
    graph: TaskGraph,
    probe: GraphProbe,
    new_run_dir: Path,
) -> tuple[dict[str, TaskRuntime], dict[str, WorkstreamRuntime]]:
    """Build runtimes for a resume run from a prior-run probe.

    Frozen tasks (those with ``resolved.json`` in the probe) get their
    ``signal_dir`` pointed at the new run directory (where status files
    were copied by :func:`_copy_frozen_artifacts`).  Non-frozen tasks
    start as PENDING with default state.

    Non-PENDING workstreams get their state populated from the probe
    (signal_dir, worktree_path, branch_name, merge_pr_url).  This
    ensures the orchestrator can read the correct status and write
    status transitions.  PENDING workstreams start with default state —
    the orchestrator will call ``prepare()`` which is idempotent (PR D
    reuses existing worktrees).

    Args:
        graph: Current graph definition.
        probe: Probe result from the prior run.
        new_run_dir: Path to the new run directory.

    Returns:
        Tuple of ``(task_runtimes, workstream_runtimes)``.
    """
    task_runtimes = TaskRuntimeBuilder.from_graph(graph)
    for task_id, task_probe in probe.task_probes.items():
        if task_probe.resolved is None:
            continue
        runtime = task_runtimes[task_id]
        runtime.state.signal_dir = new_run_dir / "signals" / task_id
        runtime.state.branch_name = task_probe.branch_name
        runtime.state.attempt_num = task_probe.attempt_num
        runtime.artifacts.pr_url = task_probe.pr_url

    workstream_runtimes = WorkstreamRuntimeBuilder.from_graph(graph)
    for ws_id, ws_probe in probe.workstream_probes.items():
        if ws_probe.status == WorkstreamStatus.PENDING:
            continue
        ws_runtime = workstream_runtimes[ws_id]
        ws_runtime.state.signal_dir = new_run_dir / "workstreams" / ws_id
        ws_runtime.state.worktree_path = ws_probe.worktree_path
        ws_runtime.state.branch_name = ws_probe.branch_name
        ws_runtime.artifacts.merge_pr_url = ws_probe.merge_pr_url
        if ws_probe.resolved is not None:
            ws_runtime.artifacts.target_branch_before_any_merge = (
                ws_probe.resolved.target_branch_before_any_merge
            )

    return task_runtimes, workstream_runtimes


def _reset_stale_worktree_branches(
    repo_path: Path,
    graph_name: str,
    graph: TaskGraph,
    frozen_task_ids: set[str],
) -> None:
    """Switch worktrees off stale task branches before dispatch.

    When a worktree is checked out on a non-frozen task's branch, the
    task preparer would treat it as a retry (preserving old WIP commits).
    Switching to the integration branch forces the preparer to
    force-create a clean task branch.

    Args:
        repo_path: Path to the repository root.
        graph_name: Name of the graph.
        graph: Current graph definition.
        frozen_task_ids: Set of task IDs that are frozen (should not be
            touched).
    """
    task_branch_prefix = f"agentrelay/{graph_name}/"
    for ws_id in graph.workstream_ids():
        worktree_path = repo_path / ".worktrees" / graph_name / ws_id
        if not worktree_path.is_dir():
            continue

        try:
            current = git.current_branch(worktree_path)
        except Exception:
            continue

        if current is None:
            continue

        # Check if the current branch is a task branch for a non-frozen task.
        if not current.startswith(task_branch_prefix):
            continue
        suffix = current[len(task_branch_prefix) :]
        # Task branches are agentrelay/<graph>/<task_id> (no further slashes).
        # Integration branches have an extra /integration suffix.
        if "/" in suffix:
            continue
        task_id = suffix
        if task_id in frozen_task_ids:
            continue

        # Switch to the integration branch and remove untracked files.
        # Untracked files from the interrupted agent survive branch
        # switches.  Without cleanup, the new agent would see a partial,
        # potentially incoherent view of the interrupted work (uncommitted
        # files but not committed ones, since force-create overwrites the
        # branch).  A clean worktree ensures a coherent fresh start.
        integration_branch = f"agentrelay/{graph_name}/{ws_id}/integration"
        git.checkout(worktree_path, integration_branch)
        git.clean(worktree_path)


def _compare_run_configs(
    prior_run_dir: Path,
    current_config: OrchestratorConfig,
    *,
    model: Optional[str],
    sandbox: Optional[str],
) -> list[str]:
    """Compare prior run config with current settings.

    Returns a list of warning strings for fields that differ.  Returns
    an empty list if the file is missing or configs match.

    Args:
        prior_run_dir: Path to the prior run directory.
        current_config: Current orchestrator configuration.
        model: Current model override (from CLI or YAML), or None.
        sandbox: Current sandbox override (from CLI), or None.

    Returns:
        List of human-readable warning strings.
    """
    path = prior_run_dir / "run_config.json"
    if not path.is_file():
        return []
    try:
        prior = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    warnings: list[str] = []
    checks: list[tuple[str, Any, Any]] = [
        (
            "max_concurrency",
            prior.get("max_concurrency"),
            current_config.max_concurrency,
        ),
        (
            "max_task_attempts",
            prior.get("max_task_attempts"),
            current_config.max_task_attempts,
        ),
        (
            "task_teardown_mode",
            prior.get("task_teardown_mode"),
            current_config.task_teardown_mode.value,
        ),
        ("model", prior.get("model"), model),
        ("sandbox", prior.get("sandbox"), sandbox),
    ]
    for field_name, prior_val, current_val in checks:
        if prior_val != current_val:
            warnings.append(
                f"{field_name}: {prior_val} -> {current_val} (using current)"
            )
    return warnings


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


def _resolve_override(
    cli_value: Optional[Any],
    yaml_value: Optional[Any],
) -> Optional[Any]:
    """Resolve a config value: CLI > YAML > ``None``.

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
    max_concurrency: Optional[int] = None,
    max_task_attempts: Optional[int] = None,
    teardown_mode: Optional[str] = None,
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

    All ``Optional`` config parameters follow CLI > YAML > default
    precedence.  ``None`` means "not specified by CLI; fall back to
    graph YAML, then :class:`OrchestratorConfig` default."

    Args:
        graph_path: Path to the graph YAML file.
        repo_path: Path to the repository root.
        tmux_session: Override tmux session name (overrides YAML value).
        keep_panes: Keep tmux panes open after task completion.
        model_override: Override model for all agents (overrides YAML value).
        max_concurrency: CLI override for max concurrent tasks.
        max_task_attempts: CLI override for max attempts per task.
        teardown_mode: CLI override for teardown mode
            (``"always"``, ``"never"``, or ``"on_success"``).
        fail_fast_on_workstream_error: CLI override for workstream
            fail-fast behavior.
        fail_fast_on_internal_error: CLI override for internal error
            fail-fast behavior.
        credential_provider: Credential provider for sandboxed agents.
            When ``None``, :class:`NullCredentialProvider` is used.
        anthropic_credential_name: Name of the Anthropic credential to
            use from the credentials YAML ``anthropic`` section.
        sandbox_override: CLI override for sandbox type (``"oci"`` or
            ``"none"``).  When set, overrides sandbox config for all tasks.
        verbose: Show detailed step-level output during execution.

    Returns:
        OrchestratorResult: Terminal orchestration result.
    """
    config = OrchestratorConfig()

    # Resolve tmux session: CLI flag > auto-detect > error.
    if tmux_session is None:
        tmux_session = tmux.current_session()
    if tmux_session is None:
        raise _SessionError(
            "No tmux session specified and not running inside tmux.\n"
            "Either run from inside a tmux session or use --tmux-session."
        )

    graph, ops = _load_and_prepare_graph(
        graph_path,
        tmux_session=tmux_session,
        model_override=model_override,
        sandbox_override=sandbox_override,
    )
    effective_keep_panes = keep_panes or ops.keep_panes

    # Resolve config fields: CLI > YAML > OrchestratorConfig default.
    eff_concurrency = _resolve_override(max_concurrency, ops.max_concurrency)
    if eff_concurrency is not None:
        config = dataclasses.replace(config, max_concurrency=eff_concurrency)

    eff_attempts = _resolve_override(max_task_attempts, ops.max_task_attempts)
    if eff_attempts is not None:
        config = dataclasses.replace(config, max_task_attempts=eff_attempts)

    eff_teardown = _resolve_override(teardown_mode, ops.teardown_mode)
    if eff_teardown is not None:
        config = dataclasses.replace(
            config, task_teardown_mode=TearDownMode(eff_teardown)
        )

    eff_fail_fast = _resolve_override(
        fail_fast_on_workstream_error, ops.fail_fast_on_workstream_error
    )
    if eff_fail_fast is not None:
        config = dataclasses.replace(
            config, fail_fast_on_workstream_error=eff_fail_fast
        )

    eff_fail_fast_internal = _resolve_override(
        fail_fast_on_internal_error, ops.fail_fast_on_internal_error
    )
    if eff_fail_fast_internal is not None:
        config = dataclasses.replace(
            config, fail_fast_on_internal_error=eff_fail_fast_internal
        )

    assert graph.name is not None, "Graph must have a name"

    ctx = _resolve_run_context(repo_path, graph.name)
    _validate_tmux_sessions(graph)
    validate_tools(ops.tools)

    # -- Resume path: probe prior run and prepare new run dir --
    task_runtimes: Optional[dict[str, TaskRuntime]] = None
    workstream_runtimes: Optional[dict[str, WorkstreamRuntime]] = None

    if ctx.is_resume:
        assert ctx.prior_run_dir is not None
        assert ctx.prior_run_number is not None

        pr_prober = build_task_pr_prober()
        probe = probe_graph_state(
            repo_path, graph.name, graph, ctx.prior_run_dir, pr_prober
        )

        # Collect frozen tasks (those with resolved.json).
        frozen = {
            tid: tp.resolved
            for tid, tp in probe.task_probes.items()
            if tp.resolved is not None
        }
        current_tasks = {tid: graph.task(tid) for tid in graph.task_ids()}
        validation = validate_frozen_tasks(frozen, current_tasks)
        if validation.has_errors:
            missing = ", ".join(validation.missing_task_ids)
            raise RuntimeError(
                f"Cannot resume: frozen task(s) missing from current graph: {missing}\n"
                "These tasks completed in a prior run but no longer exist in the "
                "graph YAML. Add them back or use `agentrelay reset` to start fresh."
            )

        _copy_frozen_artifacts(ctx.prior_run_dir, ctx.run_dir, probe)

        frozen_ids = set(frozen.keys())
        _reset_stale_worktree_branches(repo_path, graph.name, graph, frozen_ids)

        config_warnings = _compare_run_configs(
            ctx.prior_run_dir, config, model=model_override, sandbox=sandbox_override
        )

        task_runtimes, workstream_runtimes = _build_resume_runtimes(
            graph, probe, ctx.run_dir
        )

        # Print resume summary.
        task_infos = [
            ResumeTaskInfo(
                task_id=tid,
                status=probe.task_probes[tid].status,
                frozen=tid in frozen_ids,
            )
            for tid in graph.task_ids()
        ]
        print_resume_summary(
            graph.name, ctx.run_number, ctx.prior_run_number, task_infos
        )
        if validation.has_overrides:
            print_override_report(validation)
        if config_warnings:
            print_config_warnings(config_warnings)

    # -- Record run metadata --
    prior_start_head = (
        _read_prior_start_head(ctx.prior_run_dir)
        if ctx.is_resume and ctx.prior_run_dir is not None
        else None
    )
    _record_run_start(ctx.run_dir, repo_path, start_head=prior_start_head)
    _copy_graph_yaml(ctx.run_dir, graph_path)

    # Resolve Anthropic credential: CLI flag > graph YAML default > auto-select.
    effective_anthropic_name = anthropic_credential_name or ops.anthropic_credential
    anthropic_credential: Optional[AnthropicCredential] = None
    if isinstance(credential_provider, FileCredentialProvider):
        anthropic_credential = credential_provider.resolve_anthropic(
            effective_anthropic_name
        )

    _record_run_config(
        ctx.run_dir,
        config,
        keep_panes=effective_keep_panes,
        model=model_override,
        sandbox=sandbox_override,
        anthropic_credential=effective_anthropic_name,
        verbose=verbose,
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
            run_dir=ctx.run_dir,
            graph=graph,
            keep_panes=effective_keep_panes,
            tools=ops.tools,
            credential_provider=credential_provider,
            anthropic_credential=anthropic_credential,
        )
        workstream_runner = build_standard_workstream_runner(
            repo_path=repo_path,
            graph_name=graph.name,
            run_dir=ctx.run_dir,
        )
        orchestrator = Orchestrator(
            graph=graph,
            task_runner=task_runner,
            workstream_runner=workstream_runner,
            config=config,
            listener=ConsoleListener(verbose=verbose),
            integration_merge_checker=build_integration_merge_checker(repo_path),
            integration_auto_merger=build_integration_auto_merger(repo_path),
        )
        return await orchestrator.run(
            task_runtimes=task_runtimes,
            workstream_runtimes=workstream_runtimes,
        )
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
    graph, ops = _load_and_prepare_graph(graph_path)

    print(f"Graph: {graph.name}")
    print(f"Tasks: {len(graph.task_ids())}")
    print(f"Workstreams: {len(graph.workstream_ids())}")
    if ops.tools:
        print(f"Tools: {', '.join(ops.tools)}")

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
    """Print resume notice during dry-run (non-fatal)."""
    workflow_dir = repo_path / ".workflow" / graph_name
    if workflow_dir.is_dir():
        latest = _find_latest_run_dir(workflow_dir)
        if latest is not None:
            run_num = int(latest.name)
            print(
                f"\nNote: prior run exists (run {run_num}). "
                f"Running this graph will resume as run {run_num + 1}."
            )
            print("  Use `agentrelay reset` first for a completely fresh start.")


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
        help="When to tear down task resources (default: always)",
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
        "-k",
        "--keep-panes",
        action="store_true",
        help="Keep tmux panes open after task completion",
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

    try:
        result = asyncio.run(
            run_graph(
                graph_path=graph_path,
                repo_path=repo_path,
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
        )
    except (
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
