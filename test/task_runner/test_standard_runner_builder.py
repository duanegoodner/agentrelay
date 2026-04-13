"""Tests for build_standard_runner builder function."""

from pathlib import Path
from unittest.mock import MagicMock

from agentrelay.orchestrator.builders import build_standard_runner
from agentrelay.sandbox import (
    CredentialProvider,
    IsolationConfig,
    NullCredentialProvider,
    OciSandbox,
    SandboxType,
    TokenTier,
)
from agentrelay.task import AgentConfig, AgentRole, Task
from agentrelay.task_graph import TaskGraph
from agentrelay.task_runner import StandardTaskRunner
from agentrelay.task_runner.implementations import (
    GhTaskMerger,
    ShellGateChecker,
    SignalCompletionChecker,
    TmuxTaskKickoff,
    TmuxTaskLauncher,
    WorktreeTaskPreparer,
    WorktreeTaskTeardown,
)
from agentrelay.task_runtime import TaskRuntime


def _graph_with_deps() -> TaskGraph:
    task_a = Task(id="a", role=AgentRole.GENERIC, description="task A")
    task_b = Task(
        id="b",
        role=AgentRole.GENERIC,
        description="task B",
        dependencies=("a",),
    )
    return TaskGraph.from_tasks((task_a, task_b))


def test_build_returns_standard_task_runner() -> None:
    graph = _graph_with_deps()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        run_dir=Path("/repo/.workflow/test_graph/runs/0"),
        graph=graph,
    )
    assert isinstance(runner, StandardTaskRunner)


def test_preparer_dispatch_returns_worktree_task_preparer() -> None:
    graph = _graph_with_deps()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        run_dir=Path("/repo/.workflow/test_graph/runs/0"),
        graph=graph,
    )
    runtime = TaskRuntime(task=graph.task("b"))
    preparer = runner._preparer(runtime)
    assert isinstance(preparer, WorktreeTaskPreparer)


def test_preparer_computes_dependency_descriptions() -> None:
    graph = _graph_with_deps()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        run_dir=Path("/repo/.workflow/test_graph/runs/0"),
        graph=graph,
    )
    runtime = TaskRuntime(task=graph.task("b"))
    preparer = runner._preparer(runtime)
    assert isinstance(preparer, WorktreeTaskPreparer)
    assert preparer.dependency_descriptions == {"a": "task A"}
    assert preparer.run_dir == Path("/repo/.workflow/test_graph/runs/0")


def test_launcher_dispatch_returns_tmux_launcher() -> None:
    graph = _graph_with_deps()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        run_dir=Path("/repo/.workflow/test_graph/runs/0"),
        graph=graph,
    )
    runtime = TaskRuntime(task=graph.task("a"))
    assert isinstance(runner._launcher(runtime), TmuxTaskLauncher)


def test_kickoff_dispatch_returns_tmux_kickoff() -> None:
    graph = _graph_with_deps()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        run_dir=Path("/repo/.workflow/test_graph/runs/0"),
        graph=graph,
    )
    runtime = TaskRuntime(task=graph.task("a"))
    assert isinstance(runner._kickoff(runtime), TmuxTaskKickoff)


def test_completion_checker_dispatch_returns_signal_checker() -> None:
    graph = _graph_with_deps()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        run_dir=Path("/repo/.workflow/test_graph/runs/0"),
        graph=graph,
        poll_interval=5.0,
    )
    runtime = TaskRuntime(task=graph.task("a"))
    checker = runner._completion_checker(runtime)
    assert isinstance(checker, SignalCompletionChecker)
    assert checker.poll_interval == 5.0


def test_merger_dispatch_returns_gh_merger() -> None:
    graph = _graph_with_deps()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        run_dir=Path("/repo/.workflow/test_graph/runs/0"),
        graph=graph,
    )
    runtime = TaskRuntime(task=graph.task("a"))
    merger = runner._merger(runtime)
    assert isinstance(merger, GhTaskMerger)
    assert merger.repo_path == Path("/repo")


def test_gate_checker_is_shell_gate_checker() -> None:
    graph = _graph_with_deps()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        run_dir=Path("/repo/.workflow/test_graph/runs/0"),
        graph=graph,
    )
    assert isinstance(runner._gate_checker, ShellGateChecker)


def test_teardown_dispatch_returns_worktree_teardown() -> None:
    graph = _graph_with_deps()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        run_dir=Path("/repo/.workflow/test_graph/runs/0"),
        graph=graph,
        keep_panes=True,
    )
    runtime = TaskRuntime(task=graph.task("a"))
    teardown = runner._teardown(runtime)
    assert isinstance(teardown, WorktreeTaskTeardown)
    assert teardown.keep_panes is True


def test_launcher_has_null_credential_provider() -> None:
    """Default launcher uses NullCredentialProvider."""
    graph = _graph_with_deps()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        run_dir=Path("/repo/.workflow/test_graph/runs/0"),
        graph=graph,
    )
    runtime = TaskRuntime(task=graph.task("a"))
    launcher = runner._launcher(runtime)
    assert isinstance(launcher, TmuxTaskLauncher)
    assert isinstance(launcher.credential_provider, NullCredentialProvider)


def test_launcher_uses_custom_credential_provider() -> None:
    """Custom credential_provider is passed through to launcher."""
    mock_cp = MagicMock(spec=CredentialProvider)
    graph = _graph_with_deps()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        run_dir=Path("/repo/.workflow/test_graph/runs/0"),
        graph=graph,
        credential_provider=mock_cp,
    )
    runtime = TaskRuntime(task=graph.task("a"))
    launcher = runner._launcher(runtime)
    assert isinstance(launcher, TmuxTaskLauncher)
    assert launcher.credential_provider is mock_cp


def _graph_with_oci() -> TaskGraph:
    task_a = Task(
        id="a",
        role=AgentRole.GENERIC,
        description="OCI task",
        primary_agent=AgentConfig(
            isolation=IsolationConfig(
                sandbox_type=SandboxType.OCI,
                token_tier=TokenTier.STANDARD,
            ),
        ),
    )
    return TaskGraph.from_tasks((task_a,))


def test_oci_launcher_has_no_anthropic_credential_by_default() -> None:
    """OCI sandbox has no anthropic_credential when not provided."""
    graph = _graph_with_oci()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        run_dir=Path("/repo/.workflow/test_graph/runs/0"),
        graph=graph,
    )
    runtime = TaskRuntime(task=graph.task("a"))
    launcher = runner._launcher(runtime)
    assert isinstance(launcher, TmuxTaskLauncher)
    assert isinstance(launcher.sandbox, OciSandbox)
    assert launcher.sandbox._anthropic_credential is None


def test_oci_launcher_passes_anthropic_credential_to_sandbox() -> None:
    """anthropic_credential is forwarded to OciSandbox."""
    from agentrelay.sandbox import AnthropicCredential, CredentialType

    cred = AnthropicCredential(
        name="test",
        credential_type=CredentialType.API_KEY,
        api_key="sk-test",
    )
    graph = _graph_with_oci()
    runner = build_standard_runner(
        repo_path=Path("/repo"),
        graph_name="test_graph",
        run_dir=Path("/repo/.workflow/test_graph/runs/0"),
        graph=graph,
        anthropic_credential=cred,
    )
    runtime = TaskRuntime(task=graph.task("a"))
    launcher = runner._launcher(runtime)
    assert isinstance(launcher, TmuxTaskLauncher)
    assert isinstance(launcher.sandbox, OciSandbox)
    assert launcher.sandbox._anthropic_credential is cred
