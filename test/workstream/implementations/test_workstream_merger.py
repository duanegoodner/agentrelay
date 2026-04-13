"""Tests for GhWorkstreamIntegrator."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from agentrelay.workstream.core.io import IntegrationResult, WorkstreamIntegrator
from agentrelay.workstream.core.runtime import (
    TaskSummary,
    WorkstreamRuntime,
    WorkstreamStatus,
)
from agentrelay.workstream.core.workstream import WorkstreamSpec
from agentrelay.workstream.implementations.workstream_integrator import (
    GhWorkstreamIntegrator,
    _truncate,
)

_GIT = "agentrelay.workstream.implementations.workstream_integrator.git"
_GH = "agentrelay.workstream.implementations.workstream_integrator.gh"


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

    @patch(_GIT)
    @patch(_GH)
    def test_creates_pr_with_correct_base_and_head(
        self,
        mock_gh: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """Creates a PR from integration branch into merge_target_branch."""
        mock_git.rev_list_count.return_value = 1
        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        integrator = GhWorkstreamIntegrator(repo_path=Path("/repo"))
        runtime = _make_runtime()

        integrator.create_integration_pr(runtime)

        mock_gh.pr_create.assert_called_once()
        call_kwargs = mock_gh.pr_create.call_args
        assert call_kwargs[1]["base"] == "main"
        assert call_kwargs[1]["head"] == "agentrelay/demo/ws-1/integration"

    @patch(_GIT)
    @patch(_GH)
    def test_does_not_merge_pr(
        self,
        mock_gh: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """Does not call gh.pr_merge — PR is left open for review."""
        mock_git.rev_list_count.return_value = 1
        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        integrator = GhWorkstreamIntegrator(repo_path=Path("/repo"))
        runtime = _make_runtime()

        integrator.create_integration_pr(runtime)

        assert not hasattr(mock_gh, "pr_merge") or not mock_gh.pr_merge.called

    @patch(_GIT)
    @patch(_GH)
    def test_marks_pr_created_on_runtime(
        self,
        mock_gh: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """Sets merge_pr_url on workstream artifacts via mark_pr_created."""
        mock_git.rev_list_count.return_value = 1
        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        integrator = GhWorkstreamIntegrator(repo_path=Path("/repo"))
        runtime = _make_runtime()

        integrator.create_integration_pr(runtime)

        assert runtime.artifacts.merge_pr_url == "https://github.com/org/repo/pull/99"
        assert runtime.status == WorkstreamStatus.PR_CREATED

    @patch(_GIT)
    @patch(_GH)
    def test_pr_body_contains_task_summaries(
        self,
        mock_gh: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """PR body includes task summaries when present."""
        mock_git.rev_list_count.return_value = 1
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

    @patch(_GIT)
    @patch(_GH)
    def test_pr_body_contains_ops_concerns(
        self,
        mock_gh: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """PR body includes ops concerns when present."""
        mock_git.rev_list_count.return_value = 1
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

    @patch(_GIT)
    @patch(_GH)
    def test_pr_body_separates_design_and_ops_concerns(
        self,
        mock_gh: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """PR body keeps design and ops concerns in separate sections."""
        mock_git.rev_list_count.return_value = 1
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

    @patch(_GIT)
    @patch(_GH)
    def test_skips_pr_when_no_commits_ahead(
        self,
        mock_gh: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """Marks merged and skips gh.pr_create when branch has 0 commits ahead."""
        mock_git.rev_list_count.return_value = 0
        mock_git.rev_parse.return_value = "target_sha_abc"
        integrator = GhWorkstreamIntegrator(repo_path=Path("/repo"))
        runtime = _make_runtime()

        result = integrator.create_integration_pr(runtime)

        mock_git.rev_list_count.assert_called_once_with(
            Path("/repo"), "main", "agentrelay/demo/ws-1/integration"
        )
        mock_gh.pr_create.assert_not_called()
        assert runtime.status == WorkstreamStatus.MERGED
        assert runtime.artifacts.merge_pr_url is None
        assert result == IntegrationResult(
            skipped=True, target_branch_authoritative_sha="target_sha_abc"
        )

    @patch(_GIT)
    @patch(_GH)
    def test_creates_pr_when_commits_ahead(
        self,
        mock_gh: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """Creates PR normally when branch has commits ahead."""
        mock_git.rev_list_count.return_value = 3
        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        integrator = GhWorkstreamIntegrator(repo_path=Path("/repo"))
        runtime = _make_runtime()

        result = integrator.create_integration_pr(runtime)

        mock_gh.pr_create.assert_called_once()
        assert runtime.status == WorkstreamStatus.PR_CREATED
        assert runtime.artifacts.merge_pr_url == "https://github.com/org/repo/pull/99"
        assert result == IntegrationResult(skipped=False)

    @patch(_GIT)
    @patch(_GH)
    def test_pr_body_shows_role_when_description_missing(
        self,
        mock_gh: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """Falls back to task_id (role) when description is None."""
        mock_git.rev_list_count.return_value = 1
        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        integrator = GhWorkstreamIntegrator(repo_path=Path("/repo"))
        runtime = _make_runtime()
        runtime.artifacts.task_summaries = [
            TaskSummary(task_id="impl_queue", role="spec_writer"),
        ]

        integrator.create_integration_pr(runtime)

        body = mock_gh.pr_create.call_args[1]["body"]
        assert "impl_queue (spec writer)" in body

    @patch(_GIT)
    @patch(_GH)
    def test_pr_body_shows_task_id_when_description_and_role_missing(
        self,
        mock_gh: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """Falls back to bare task_id when both description and role are None."""
        mock_git.rev_list_count.return_value = 1
        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        integrator = GhWorkstreamIntegrator(repo_path=Path("/repo"))
        runtime = _make_runtime()
        runtime.artifacts.task_summaries = [
            TaskSummary(task_id="my_task"),
        ]

        integrator.create_integration_pr(runtime)

        body = mock_gh.pr_create.call_args[1]["body"]
        assert "**my_task** — my_task" in body
        assert "(None)" not in body

    @patch(_GIT)
    @patch(_GH)
    def test_pr_body_truncates_long_description(
        self,
        mock_gh: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """Truncates descriptions longer than 200 characters."""
        mock_git.rev_list_count.return_value = 1
        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        integrator = GhWorkstreamIntegrator(repo_path=Path("/repo"))
        runtime = _make_runtime()
        long_desc = "A" * 300
        runtime.artifacts.task_summaries = [
            TaskSummary(task_id="task_a", description=long_desc),
        ]

        integrator.create_integration_pr(runtime)

        body = mock_gh.pr_create.call_args[1]["body"]
        assert "A" * 200 + " …" in body
        assert "A" * 201 not in body

    @patch(_GIT)
    @patch(_GH)
    def test_pr_body_does_not_truncate_short_description(
        self,
        mock_gh: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """Short descriptions appear in full without ellipsis."""
        mock_git.rev_list_count.return_value = 1
        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        integrator = GhWorkstreamIntegrator(repo_path=Path("/repo"))
        runtime = _make_runtime()
        runtime.artifacts.task_summaries = [
            TaskSummary(task_id="task_a", description="Short description"),
        ]

        integrator.create_integration_pr(runtime)

        body = mock_gh.pr_create.call_args[1]["body"]
        assert "Short description" in body
        assert "…" not in body

    @patch(_GIT)
    @patch(_GH)
    def test_pr_body_includes_summary_in_details_block(
        self,
        mock_gh: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """Summary text renders inside a collapsible <details> block."""
        mock_git.rev_list_count.return_value = 1
        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        integrator = GhWorkstreamIntegrator(repo_path=Path("/repo"))
        runtime = _make_runtime()
        runtime.artifacts.task_summaries = [
            TaskSummary(
                task_id="task_a",
                description="Do stuff",
                summary_text="Detailed agent summary here.",
            ),
        ]

        integrator.create_integration_pr(runtime)

        body = mock_gh.pr_create.call_args[1]["body"]
        assert "<details>" in body
        assert "<summary>Agent summary</summary>" in body
        assert "Detailed agent summary here." in body
        assert "</details>" in body

    @patch(_GIT)
    @patch(_GH)
    def test_pr_body_omits_details_when_no_summary(
        self,
        mock_gh: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """No <details> block when summary_text is None."""
        mock_git.rev_list_count.return_value = 1
        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        integrator = GhWorkstreamIntegrator(repo_path=Path("/repo"))
        runtime = _make_runtime()
        runtime.artifacts.task_summaries = [
            TaskSummary(task_id="task_a", description="Do stuff"),
        ]

        integrator.create_integration_pr(runtime)

        body = mock_gh.pr_create.call_args[1]["body"]
        assert "<details>" not in body

    @patch(_GIT)
    @patch(_GH)
    def test_pr_body_omits_details_when_summary_empty(
        self,
        mock_gh: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """No <details> block when summary_text is empty string."""
        mock_git.rev_list_count.return_value = 1
        mock_gh.pr_create.return_value = "https://github.com/org/repo/pull/99"
        integrator = GhWorkstreamIntegrator(repo_path=Path("/repo"))
        runtime = _make_runtime()
        runtime.artifacts.task_summaries = [
            TaskSummary(task_id="task_a", description="Do stuff", summary_text=""),
        ]

        integrator.create_integration_pr(runtime)

        body = mock_gh.pr_create.call_args[1]["body"]
        assert "<details>" not in body


class TestTruncate:
    """Tests for the _truncate helper."""

    def test_short_text_unchanged(self) -> None:
        assert _truncate("hello") == "hello"

    def test_at_limit_unchanged(self) -> None:
        text = "A" * 200
        assert _truncate(text) == text

    def test_over_limit_truncated(self) -> None:
        text = "A" * 201
        result = _truncate(text)
        assert result == "A" * 200 + " …"
        assert len(result) == 202  # 200 + " …" (2 chars)
