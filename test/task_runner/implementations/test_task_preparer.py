"""Tests for WorktreeTaskPreparer."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from agentrelay.errors import WorkspaceIntegrationError
from agentrelay.task import AgentRole, Task
from agentrelay.task_runner.core.io import TaskPreparer
from agentrelay.task_runner.implementations.task_preparer import (
    WorktreeTaskPreparer,
)
from agentrelay.task_runtime import TaskRuntime


def _make_runtime(
    task_id: str = "task_1", role: AgentRole = AgentRole.GENERIC
) -> TaskRuntime:
    runtime = TaskRuntime(task=Task(id=task_id, role=role, description="Do something"))
    runtime.state.integration_branch = "agentrelay/demo"
    runtime.state.workstream_worktree_path = Path("/worktrees/demo/ws-1")
    return runtime


def _make_preparer(repo_path: Path = Path("/repo")) -> WorktreeTaskPreparer:
    return WorktreeTaskPreparer(
        repo_path=repo_path,
        graph_name="demo",
        dependency_descriptions={"dep_1": "A dependency"},
    )


class TestWorktreeTaskPreparer:
    """Tests for WorktreeTaskPreparer.prepare."""

    @patch("agentrelay.task_runner.implementations.task_preparer.resolve_instructions")
    @patch("agentrelay.task_runner.implementations.task_preparer.policies_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_policies")
    @patch("agentrelay.task_runner.implementations.task_preparer.manifest_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_manifest")
    @patch("agentrelay.task_runner.implementations.task_preparer.signals")
    @patch("agentrelay.task_runner.implementations.task_preparer.git")
    def test_creates_branch_and_checks_out(
        self,
        mock_git: MagicMock,
        mock_signals: MagicMock,
        mock_build_manifest: MagicMock,
        _mock_manifest_to_dict: MagicMock,
        _mock_build_policies: MagicMock,
        _mock_policies_to_dict: MagicMock,
        _mock_resolve: MagicMock,
    ) -> None:
        """Calls git.branch_create and git.checkout in the workstream worktree."""
        preparer = _make_preparer(repo_path=Path("/repo"))
        runtime = _make_runtime()
        mock_build_manifest.return_value = MagicMock()

        preparer.prepare(runtime)

        mock_git.branch_create.assert_called_once_with(
            Path("/worktrees/demo/ws-1"),
            "agentrelay/demo/task_1",
            "agentrelay/demo",
        )
        mock_git.checkout.assert_called_once_with(
            Path("/worktrees/demo/ws-1"),
            "agentrelay/demo/task_1",
        )

    @patch("agentrelay.task_runner.implementations.task_preparer.resolve_instructions")
    @patch("agentrelay.task_runner.implementations.task_preparer.policies_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_policies")
    @patch("agentrelay.task_runner.implementations.task_preparer.manifest_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_manifest")
    @patch("agentrelay.task_runner.implementations.task_preparer.signals")
    @patch("agentrelay.task_runner.implementations.task_preparer.git")
    def test_writes_three_protocol_files(
        self,
        _mock_git: MagicMock,
        mock_signals: MagicMock,
        mock_build_manifest: MagicMock,
        mock_manifest_to_dict: MagicMock,
        mock_build_policies: MagicMock,
        mock_policies_to_dict: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Writes manifest.json, policies.json, and instructions.md."""
        mock_build_manifest.return_value = MagicMock()
        mock_manifest_to_dict.return_value = {"manifest": "data"}
        mock_build_policies.return_value = MagicMock()
        mock_policies_to_dict.return_value = {"policies": "data"}
        mock_resolve.return_value = "# Instructions"

        preparer = _make_preparer()
        runtime = _make_runtime()
        preparer.prepare(runtime)

        signal_dir = Path("/repo/.workflow/demo/signals/task_1")
        mock_signals.write_json.assert_any_call(
            signal_dir, "manifest.json", {"manifest": "data"}
        )
        mock_signals.write_json.assert_any_call(
            signal_dir, "policies.json", {"policies": "data"}
        )
        mock_signals.write_text.assert_any_call(
            signal_dir, "instructions.md", "# Instructions"
        )

    @patch("agentrelay.task_runner.implementations.task_preparer.resolve_instructions")
    @patch("agentrelay.task_runner.implementations.task_preparer.policies_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_policies")
    @patch("agentrelay.task_runner.implementations.task_preparer.manifest_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_manifest")
    @patch("agentrelay.task_runner.implementations.task_preparer.signals")
    @patch("agentrelay.task_runner.implementations.task_preparer.git")
    def test_sets_runtime_state(
        self,
        _mock_git: MagicMock,
        _mock_signals: MagicMock,
        mock_build_manifest: MagicMock,
        _mock_manifest_to_dict: MagicMock,
        _mock_build_policies: MagicMock,
        _mock_policies_to_dict: MagicMock,
        _mock_resolve: MagicMock,
    ) -> None:
        """Sets worktree_path, branch_name, and signal_dir on runtime."""
        mock_build_manifest.return_value = MagicMock()
        preparer = _make_preparer()
        runtime = _make_runtime()

        preparer.prepare(runtime)

        assert runtime.state.worktree_path == Path("/worktrees/demo/ws-1")
        assert runtime.state.branch_name == "agentrelay/demo/task_1"
        assert runtime.state.signal_dir == Path("/repo/.workflow/demo/signals/task_1")

    @patch("agentrelay.task_runner.implementations.task_preparer.resolve_instructions")
    @patch("agentrelay.task_runner.implementations.task_preparer.policies_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_policies")
    @patch("agentrelay.task_runner.implementations.task_preparer.manifest_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_manifest")
    @patch("agentrelay.task_runner.implementations.task_preparer.signals")
    @patch("agentrelay.task_runner.implementations.task_preparer.git")
    def test_writes_context_md_when_provided(
        self,
        _mock_git: MagicMock,
        mock_signals: MagicMock,
        mock_build_manifest: MagicMock,
        _mock_manifest_to_dict: MagicMock,
        _mock_build_policies: MagicMock,
        _mock_policies_to_dict: MagicMock,
        _mock_resolve: MagicMock,
    ) -> None:
        """Writes context.md when context_content is provided."""
        mock_build_manifest.return_value = MagicMock()
        preparer = _make_preparer()
        preparer.context_content = "# Context\nPrevious task output."

        runtime = _make_runtime()
        preparer.prepare(runtime)

        signal_dir = Path("/repo/.workflow/demo/signals/task_1")
        mock_signals.write_text.assert_any_call(
            signal_dir, "context.md", "# Context\nPrevious task output."
        )

    @patch("agentrelay.task_runner.implementations.task_preparer.resolve_instructions")
    @patch("agentrelay.task_runner.implementations.task_preparer.policies_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_policies")
    @patch("agentrelay.task_runner.implementations.task_preparer.manifest_to_dict")
    @patch("agentrelay.task_runner.implementations.task_preparer.build_manifest")
    @patch("agentrelay.task_runner.implementations.task_preparer.signals")
    @patch("agentrelay.task_runner.implementations.task_preparer.git")
    def test_omits_context_md_when_not_provided(
        self,
        _mock_git: MagicMock,
        mock_signals: MagicMock,
        mock_build_manifest: MagicMock,
        _mock_manifest_to_dict: MagicMock,
        _mock_build_policies: MagicMock,
        _mock_policies_to_dict: MagicMock,
        _mock_resolve: MagicMock,
    ) -> None:
        """Does not write context.md when context_content is None."""
        mock_build_manifest.return_value = MagicMock()
        preparer = _make_preparer()
        runtime = _make_runtime()

        preparer.prepare(runtime)

        context_calls = [
            c for c in mock_signals.write_text.call_args_list if c[0][1] == "context.md"
        ]
        assert context_calls == []

    @patch("agentrelay.task_runner.implementations.task_preparer.signals")
    @patch("agentrelay.task_runner.implementations.task_preparer.git")
    def test_wraps_git_error_in_workspace_integration_error(
        self,
        mock_git: MagicMock,
        _mock_signals: MagicMock,
    ) -> None:
        """Wraps CalledProcessError from git in WorkspaceIntegrationError."""
        mock_git.branch_create.side_effect = subprocess.CalledProcessError(
            1, "git branch"
        )
        preparer = _make_preparer()
        runtime = _make_runtime()

        with pytest.raises(WorkspaceIntegrationError, match="task_1"):
            preparer.prepare(runtime)

    def test_satisfies_task_preparer_protocol(self) -> None:
        """WorktreeTaskPreparer satisfies the TaskPreparer protocol."""
        preparer = _make_preparer()
        assert isinstance(preparer, TaskPreparer)
