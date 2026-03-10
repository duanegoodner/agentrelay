"""Tests for integration contract dataclasses and protocol shapes."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from agentrelay.agent import Agent, AgentAddress
from agentrelay.integration_contracts import (
    AgentLauncher,
    CompletionSignal,
    IntegrationAdapters,
    LocalWorkspaceRef,
    PullRequestAdapter,
    RemoteWorkspaceRef,
    SignalAdapter,
    WorkspaceAdapter,
)
from agentrelay.task import AgentRole, Task
from agentrelay.task_runtime import TaskRuntime
from agentrelay.workstream import WorkstreamRuntime, WorkstreamSpec


class _DummyAddress(AgentAddress):
    def label(self) -> str:
        return "dummy-address"


class _DummyAgent(Agent):
    @property
    def address(self) -> AgentAddress:
        return _DummyAddress()

    def send_kickoff(self, instructions_path: str) -> None:
        _ = instructions_path


class _DummyWorkspaceAdapter:
    def ensure_workspace(
        self,
        runtime: TaskRuntime,
        workstream: WorkstreamRuntime,
    ) -> LocalWorkspaceRef:
        _ = (runtime, workstream)
        return LocalWorkspaceRef(
            worktree_path=Path("/tmp/worktree"), branch_name="feat"
        )

    def cleanup_workspace(
        self,
        runtime: TaskRuntime,
        workstream: WorkstreamRuntime,
    ) -> None:
        _ = (runtime, workstream)


class _DummySignalAdapter:
    def write_instructions(self, runtime: TaskRuntime, instructions_text: str) -> Path:
        _ = (runtime, instructions_text)
        return Path("/tmp/instructions.md")

    async def wait_for_completion(
        self,
        runtime: TaskRuntime,
        timeout_seconds: float | None = None,
    ) -> CompletionSignal:
        _ = (runtime, timeout_seconds)
        return CompletionSignal(outcome="done", pr_url="https://example/pr/1")


class _DummyPullRequestAdapter:
    def merge_task_pr(self, runtime: TaskRuntime, pr_url: str) -> None:
        _ = (runtime, pr_url)


class _DummyAgentLauncher:
    def launch_task_agent(self, runtime: TaskRuntime) -> Agent:
        _ = runtime
        return _DummyAgent()

    def send_kickoff(self, agent: Agent, instructions_path: Path) -> None:
        _ = (agent, instructions_path)


def _runtime() -> TaskRuntime:
    return TaskRuntime(task=Task(id="t1", role=AgentRole.GENERIC))


def _workstream_runtime() -> WorkstreamRuntime:
    return WorkstreamRuntime(spec=WorkstreamSpec(id="default"))


def test_local_workspace_ref_is_frozen_and_tagged() -> None:
    ref = LocalWorkspaceRef(worktree_path=Path("/tmp/w"), branch_name="feat")

    assert ref.kind == "local"
    assert ref.worktree_path == Path("/tmp/w")
    assert ref.branch_name == "feat"
    with pytest.raises(FrozenInstanceError):
        ref.branch_name = "other"  # type: ignore[misc]


def test_remote_workspace_ref_fields_and_kind() -> None:
    ref = RemoteWorkspaceRef(
        workspace_id="ws-123",
        branch_name="feature/cloud",
        workspace_uri="https://api.example/workspaces/ws-123",
        repo_ref="org/repo@abc123",
        execution_target="job-17",
        artifacts_uri="s3://bucket/path/",
    )

    assert ref.kind == "remote"
    assert ref.workspace_id == "ws-123"
    assert ref.workspace_uri is not None
    assert ref.repo_ref == "org/repo@abc123"
    assert ref.execution_target == "job-17"
    assert ref.artifacts_uri == "s3://bucket/path/"


def test_completion_signal_defaults() -> None:
    signal = CompletionSignal(outcome="failed")
    assert signal.pr_url is None
    assert signal.error is None
    assert signal.concerns == ()


def test_protocol_runtime_checkable_instances() -> None:
    workspace = _DummyWorkspaceAdapter()
    signals = _DummySignalAdapter()
    prs = _DummyPullRequestAdapter()
    launcher = _DummyAgentLauncher()

    assert isinstance(workspace, WorkspaceAdapter)
    assert isinstance(signals, SignalAdapter)
    assert isinstance(prs, PullRequestAdapter)
    assert isinstance(launcher, AgentLauncher)


def test_integration_adapters_dataclass_shape() -> None:
    adapters = IntegrationAdapters(
        workspace=_DummyWorkspaceAdapter(),
        signals=_DummySignalAdapter(),
        pull_requests=_DummyPullRequestAdapter(),
        agent_launcher=_DummyAgentLauncher(),
    )

    workspace_ref = adapters.workspace.ensure_workspace(
        _runtime(), _workstream_runtime()
    )
    assert workspace_ref.kind == "local"
    assert (
        adapters.signals.write_instructions(_runtime(), "hi").name == "instructions.md"
    )
