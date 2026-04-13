"""Runtime and runner builders for graph execution.

This module consolidates all builder logic that converts a
:class:`~agentrelay.task_graph.TaskGraph` into runtime and runner objects.
Builders live here (rather than in the packages they construct) because they
depend on :class:`TaskGraph` — placing them in lower-level packages would
create reverse dependency cycles.

Classes:
    TaskRuntimeBuilder: TaskGraph -> per-task TaskRuntime map.
    WorkstreamRuntimeBuilder: TaskGraph -> per-workstream WorkstreamRuntime map.

Functions:
    build_standard_runner: Build a StandardTaskRunner wired for worktree + tmux
        + Claude Code.
    build_standard_workstream_runner: Build a StandardWorkstreamRunner wired for
        git worktree + GitHub CLI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from agentrelay.sandbox import (
    AnthropicCredential,
    ClaudeCodeAdapter,
    CredentialProvider,
    NullCredentialProvider,
    NullSandbox,
    OciSandbox,
    SandboxType,
)
from agentrelay.task_graph import TaskGraph
from agentrelay.task_runner.core.dispatch import StepDispatch
from agentrelay.task_runner.core.io import (
    TaskCompletionChecker,
    TaskLogCapture,
    TaskMerger,
    TaskPreparer,
    TaskTeardown,
)
from agentrelay.task_runner.core.runner import StandardTaskRunner
from agentrelay.task_runner.implementations.task_completion_checker import (
    SignalCompletionChecker,
)
from agentrelay.task_runner.implementations.task_gate_checker import (
    ShellGateChecker,
)
from agentrelay.task_runner.implementations.task_kickoff import TmuxTaskKickoff
from agentrelay.task_runner.implementations.task_launcher import TmuxTaskLauncher
from agentrelay.task_runner.implementations.task_log_capture import (
    WorktreeTaskLogCapture,
)
from agentrelay.task_runner.implementations.task_merger import GhTaskMerger
from agentrelay.task_runner.implementations.task_preparer import WorktreeTaskPreparer
from agentrelay.task_runner.implementations.task_teardown import WorktreeTaskTeardown
from agentrelay.task_runtime.runtime import TaskRuntime
from agentrelay.workstream.core.runner import StandardWorkstreamRunner
from agentrelay.workstream.core.runtime import WorkstreamRuntime
from agentrelay.workstream.implementations.integration_auto_merger import (
    GhIntegrationAutoMerger,
)
from agentrelay.workstream.implementations.integration_merge_checker import (
    GhIntegrationMergeChecker,
)
from agentrelay.workstream.implementations.workstream_integrator import (
    GhWorkstreamIntegrator,
)
from agentrelay.workstream.implementations.workstream_preparer import (
    GitWorkstreamPreparer,
)
from agentrelay.workstream.implementations.workstream_teardown import (
    GitWorkstreamTeardown,
)


class TaskRuntimeBuilder:
    """Builder for initializing per-task runtime envelopes from a task graph."""

    @classmethod
    def from_graph(cls, graph: TaskGraph) -> dict[str, TaskRuntime]:
        """Build initial runtimes for all tasks in a graph.

        Runtimes are returned in the graph's stable topological task order.
        Each runtime starts with default mutable state/artifacts and no agent.

        Args:
            graph: Validated immutable task graph.

        Returns:
            dict[str, TaskRuntime]: Task runtimes keyed by task ID.
        """
        runtimes: dict[str, TaskRuntime] = {}
        for task_id in graph.task_ids():
            runtimes[task_id] = TaskRuntime(task=graph.task(task_id))
        return runtimes


class WorkstreamRuntimeBuilder:
    """Builder for initializing per-workstream runtime envelopes from a graph."""

    @classmethod
    def from_graph(cls, graph: TaskGraph) -> dict[str, WorkstreamRuntime]:
        """Build initial runtimes for all workstreams in a graph.

        Runtimes are returned in the graph's stable sorted workstream order.
        Each runtime starts with default mutable state/artifacts.

        Args:
            graph: Validated immutable task graph.

        Returns:
            dict[str, WorkstreamRuntime]: Workstream runtimes keyed by ID.
        """
        runtimes: dict[str, WorkstreamRuntime] = {}
        for workstream_id in graph.workstream_ids():
            runtimes[workstream_id] = WorkstreamRuntime(
                spec=graph.workstream(workstream_id)
            )
        return runtimes


def build_standard_runner(
    repo_path: Path,
    graph_name: str,
    run_dir: Path,
    graph: TaskGraph,
    keep_panes: bool = False,
    poll_interval: float = 2.0,
    context_content: Optional[str] = None,
    tools: tuple[str, ...] = (),
    credential_provider: Optional[CredentialProvider] = None,
    anthropic_credential: Optional[AnthropicCredential] = None,
) -> StandardTaskRunner:
    """Build the standard runner for worktree + tmux + Claude Code.

    All steps use ``StepDispatch`` ``default`` since only one
    framework/environment combo currently exists.

    When adding a new ``AgentFramework`` or ``AgentEnvironment``, add keyed
    entries to the ``StepDispatch`` tables for steps that have distinct
    implementations. Refer to the sensitivity table in
    :class:`StandardTaskRunner`'s docstring.

    Dispatch table (current):

    +-----------------------+----------------------------+-----------------------+
    | Step                  | Implementation             | Notes                 |
    +=======================+============================+=======================+
    | preparer              | WorktreeTaskPreparer       | env/fw agnostic       |
    +-----------------------+----------------------------+-----------------------+
    | launcher              | TmuxTaskLauncher           | will need entries     |
    +-----------------------+----------------------------+-----------------------+
    | kickoff               | TmuxTaskKickoff            | will need entries     |
    +-----------------------+----------------------------+-----------------------+
    | completion_checker    | SignalCompletionChecker     | may need entries      |
    +-----------------------+----------------------------+-----------------------+
    | gate_checker          | ShellGateChecker           | env/fw agnostic       |
    +-----------------------+----------------------------+-----------------------+
    | merger                | GhTaskMerger               | env/fw agnostic       |
    +-----------------------+----------------------------+-----------------------+
    | log_capture           | WorktreeTaskLogCapture      | will need entries     |
    +-----------------------+----------------------------+-----------------------+
    | teardown              | WorktreeTaskTeardown       | will need entries     |
    +-----------------------+----------------------------+-----------------------+

    Args:
        repo_path: Path to the bare/main repository.
        graph_name: Name of the task graph being executed.
        graph: The task graph (used to compute dependency descriptions).
        keep_panes: Whether to keep tmux panes after teardown.
        poll_interval: Seconds between completion signal polls.
        context_content: Optional context content to write to the signal dir.
        tools: Declared tool names from the graph YAML.

    Returns:
        A fully wired :class:`StandardTaskRunner`.
    """

    def _make_launcher(runtime: TaskRuntime) -> TmuxTaskLauncher:
        isolation = runtime.task.primary_agent.isolation
        if isolation is not None and isolation.sandbox_type == SandboxType.OCI:
            sandbox = OciSandbox(
                image=isolation.image,
                runtime=isolation.runtime,
                anthropic_credential=anthropic_credential,
            )
        else:
            sandbox = NullSandbox()
        return TmuxTaskLauncher(
            adapter=ClaudeCodeAdapter(),
            sandbox=sandbox,
            credential_provider=credential_provider or NullCredentialProvider(),
            repo_path=repo_path,
            graph_name=graph_name,
        )

    tmux_kickoff = TmuxTaskKickoff()

    def _make_preparer(runtime: TaskRuntime) -> TaskPreparer:
        dep_ids = graph.dependency_ids(runtime.task.id)
        dep_descs = {did: graph.task(did).description for did in dep_ids}
        return WorktreeTaskPreparer(
            run_dir=run_dir,
            graph_name=graph_name,
            dependency_descriptions=dep_descs,
            context_content=context_content,
            tools=tools,
        )

    def _make_merger(runtime: TaskRuntime) -> TaskMerger:
        return GhTaskMerger(repo_path=repo_path)

    def _make_completion_checker(runtime: TaskRuntime) -> TaskCompletionChecker:
        return SignalCompletionChecker(poll_interval=poll_interval)

    def _make_log_capture(runtime: TaskRuntime) -> TaskLogCapture:
        return WorktreeTaskLogCapture()

    def _make_teardown(runtime: TaskRuntime) -> TaskTeardown:
        return WorktreeTaskTeardown(repo_path=repo_path, keep_panes=keep_panes)

    return StandardTaskRunner(
        _preparer=StepDispatch(default=_make_preparer),
        _launcher=StepDispatch(default=_make_launcher),
        _kickoff=StepDispatch(default=lambda rt: tmux_kickoff),
        _completion_checker=StepDispatch(default=_make_completion_checker),
        _gate_checker=ShellGateChecker(),
        _merger=StepDispatch(default=_make_merger),
        _log_capture=StepDispatch(default=_make_log_capture),
        _teardown=StepDispatch(default=_make_teardown),
    )


def build_standard_workstream_runner(
    repo_path: Path,
    graph_name: str,
    run_dir: Path,
) -> StandardWorkstreamRunner:
    """Build the standard workstream runner for git worktree + GitHub CLI.

    Wires the three workstream lifecycle steps with concrete implementations:

    +----------+-------------------------+
    | Step     | Implementation          |
    +==========+=========================+
    | preparer | GitWorkstreamPreparer   |
    +----------+-------------------------+
    | integrator | GhWorkstreamIntegrator |
    +----------+-------------------------+
    | teardown | GitWorkstreamTeardown   |
    +----------+-------------------------+

    Args:
        repo_path: Path to the bare/main repository.
        graph_name: Name of the task graph being executed.

    Returns:
        A fully wired :class:`StandardWorkstreamRunner`.
    """
    return StandardWorkstreamRunner(
        _preparer=GitWorkstreamPreparer(
            repo_path=repo_path, graph_name=graph_name, run_dir=run_dir
        ),
        _integrator=GhWorkstreamIntegrator(repo_path=repo_path),
        _teardown=GitWorkstreamTeardown(repo_path=repo_path),
    )


def build_integration_merge_checker() -> GhIntegrationMergeChecker:
    """Build the standard integration merge checker for GitHub CLI.

    Returns:
        A :class:`GhIntegrationMergeChecker` instance.
    """
    return GhIntegrationMergeChecker()


def build_integration_auto_merger() -> GhIntegrationAutoMerger:
    """Build the standard integration auto-merger for GitHub CLI.

    Returns:
        A :class:`GhIntegrationAutoMerger` instance.
    """
    return GhIntegrationAutoMerger()
