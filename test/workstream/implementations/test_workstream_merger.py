"""Tests for GhWorkstreamIntegrator."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from agentrelay.workstream.core.io import WorkstreamIntegrator
from agentrelay.workstream.core.runtime import WorkstreamRuntime, WorkstreamStatus
from agentrelay.workstream.core.workstream import WorkstreamSpec
from agentrelay.workstream.implementations.workstream_integrator import (
    GhWorkstreamIntegrator,
)


def _make_runtime(
    workstream_id: str = "ws-1",
    merge_target_branch: str = "main",
    branch_name: str = "agentrelay/demo/ws-1/integration",
) -> WorkstreamRuntime:
    runtime = WorkstreamRuntime(
        spec=WorkstreamSpec(
            id=workstream_id,
            merge_target_branch=merge_target_branch,
        ),
    )
    runtime.state.branch_name = branch_name
    runtime.state.signal_dir = Path(tempfile.mkdtemp())
    return runtime


class TestGhWorkstreamIntegrator:
    """Tests for GhWorkstreamIntegrator.create_integration_pr."""

    @patch("agentrelay.workstream.implementations.workstream_integrator.gh")
    def test_creates_pr_with_correct_base_and_head(
        self,
        mock_gh: MagicMock,
    ) -> None:
        """Creates a PR from integration branch into merge_target_branch."""
        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        integrator = GhWorkstreamIntegrator(repo_path=Path("/repo"))
        runtime = _make_runtime()

        integrator.create_integration_pr(runtime)

        mock_gh.pr_create.assert_called_once()
        call_kwargs = mock_gh.pr_create.call_args
        assert call_kwargs[1]["base"] == "main"
        assert call_kwargs[1]["head"] == "agentrelay/demo/ws-1/integration"

    @patch("agentrelay.workstream.implementations.workstream_integrator.gh")
    def test_does_not_merge_pr(
        self,
        mock_gh: MagicMock,
    ) -> None:
        """Does not call gh.pr_merge — PR is left open for review."""
        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        integrator = GhWorkstreamIntegrator(repo_path=Path("/repo"))
        runtime = _make_runtime()

        integrator.create_integration_pr(runtime)

        assert not hasattr(mock_gh, "pr_merge") or not mock_gh.pr_merge.called

    @patch("agentrelay.workstream.implementations.workstream_integrator.gh")
    def test_marks_pr_created_on_runtime(
        self,
        mock_gh: MagicMock,
    ) -> None:
        """Sets merge_pr_url on workstream artifacts via mark_pr_created."""
        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        integrator = GhWorkstreamIntegrator(repo_path=Path("/repo"))
        runtime = _make_runtime()

        integrator.create_integration_pr(runtime)

        assert runtime.artifacts.merge_pr_url == "https://github.com/org/repo/pull/99"
        assert runtime.status == WorkstreamStatus.PR_CREATED

    @patch("agentrelay.workstream.implementations.workstream_integrator.gh")
    def test_pr_body_contains_task_summaries(
        self,
        mock_gh: MagicMock,
    ) -> None:
        """PR body includes task summaries when present."""
        from agentrelay.workstream.core.runtime import TaskSummary

        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        integrator = GhWorkstreamIntegrator(repo_path=Path("/repo"))
        runtime = _make_runtime()
        runtime.artifacts.task_summaries = [
            TaskSummary(
                task_id="task_a",
                description="Add feature",
                pr_url="https://example.com/task_a",
            ),
        ]

        integrator.create_integration_pr(runtime)

        call_kwargs = mock_gh.pr_create.call_args
        body = call_kwargs[1]["body"]
        assert "task_a" in body
        assert "Add feature" in body

    @patch("agentrelay.workstream.implementations.workstream_integrator.gh")
    def test_pr_body_contains_ops_concerns(
        self,
        mock_gh: MagicMock,
    ) -> None:
        """PR body includes ops concerns when present."""
        from agentrelay.workstream.core.runtime import TaskSummary

        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        integrator = GhWorkstreamIntegrator(repo_path=Path("/repo"))
        runtime = _make_runtime()
        runtime.artifacts.task_summaries = [
            TaskSummary(
                task_id="task_a",
                description="Add feature",
                ops_concerns=("slow build", "missing dep"),
            ),
        ]

        integrator.create_integration_pr(runtime)

        call_kwargs = mock_gh.pr_create.call_args
        body = call_kwargs[1]["body"]
        assert "## Ops Concerns" in body
        assert "slow build" in body
        assert "missing dep" in body

    @patch("agentrelay.workstream.implementations.workstream_integrator.gh")
    def test_pr_body_separates_design_and_ops_concerns(
        self,
        mock_gh: MagicMock,
    ) -> None:
        """PR body keeps design and ops concerns in separate sections."""
        from agentrelay.workstream.core.runtime import TaskSummary

        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        integrator = GhWorkstreamIntegrator(repo_path=Path("/repo"))
        runtime = _make_runtime()
        runtime.artifacts.task_summaries = [
            TaskSummary(
                task_id="task_a",
                description="Add feature",
                concerns=("spec ambiguity",),
                ops_concerns=("build flaky",),
            ),
        ]

        integrator.create_integration_pr(runtime)

        call_kwargs = mock_gh.pr_create.call_args
        body = call_kwargs[1]["body"]
        assert "## Concerns" in body
        assert "spec ambiguity" in body
        assert "## Ops Concerns" in body
        assert "build flaky" in body

    def test_satisfies_workstream_integrator_protocol(self) -> None:
        """GhWorkstreamIntegrator satisfies the WorkstreamIntegrator protocol."""
        integrator = GhWorkstreamIntegrator(repo_path=Path("/repo"))
        assert isinstance(integrator, WorkstreamIntegrator)
