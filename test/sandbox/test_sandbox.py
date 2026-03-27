"""Tests for AgentSandbox protocol and NullSandbox implementation."""

from pathlib import Path

from agentrelay.sandbox import (
    AgentSandbox,
    NullSandbox,
    SandboxContext,
)


def _make_context() -> SandboxContext:
    return SandboxContext(
        worktree_path=Path("/tmp/wt"),
        signal_dir=Path("/tmp/signals"),
        repo_path=Path("/repo"),
        task_id="task_a",
        graph_name="test-graph",
    )


class TestAgentSandboxProtocol:
    """Tests for the AgentSandbox protocol."""

    def test_is_runtime_checkable(self) -> None:
        assert isinstance(NullSandbox(), AgentSandbox)


class TestNullSandbox:
    """Tests for NullSandbox implementation."""

    def test_satisfies_protocol(self) -> None:
        sandbox = NullSandbox()
        assert isinstance(sandbox, AgentSandbox)

    def test_wrap_command_returns_unchanged(self) -> None:
        sandbox = NullSandbox()
        ctx = _make_context()
        cmd = "claude --model opus --print 'do stuff'"
        assert sandbox.wrap_command(cmd, ctx) == cmd

    def test_setup_is_noop(self) -> None:
        sandbox = NullSandbox()
        ctx = _make_context()
        sandbox.setup(ctx)  # should not raise

    def test_teardown_is_noop(self) -> None:
        sandbox = NullSandbox()
        ctx = _make_context()
        sandbox.teardown(ctx)  # should not raise
