"""Implementations of :class:`~agentrelay.workstream.core.io.WorkstreamIntegrator`.

Classes:
    GhWorkstreamIntegrator: Creates a workstream integration PR via GitHub CLI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentrelay.ops import gh, git
from agentrelay.workstream.core.io import IntegrationResult
from agentrelay.workstream.core.runtime import WorkstreamRuntime

_MAX_DESCRIPTION_LENGTH = 200


def _truncate(text: str, limit: int = _MAX_DESCRIPTION_LENGTH) -> str:
    """Truncate *text* to *limit* characters, appending an ellipsis if needed."""
    if len(text) <= limit:
        return text
    return text[:limit] + " …"


def _task_label(task_id: str, role: str | None) -> str:
    """Fallback label when a task has no description."""
    if role:
        return f"{task_id} ({role.replace('_', ' ')})"
    return task_id


def _build_pr_body(
    workstream_runtime: WorkstreamRuntime,
) -> str:
    """Build a rich markdown PR body from task summaries and concerns."""
    spec = workstream_runtime.spec
    branch_name = workstream_runtime.state.branch_name
    summaries = workstream_runtime.artifacts.task_summaries

    parts = [
        "## Summary\n",
        f"Merges workstream `{spec.id}` integration branch "
        f"`{branch_name}` into `{spec.merge_target_branch}`.\n",
    ]

    if summaries:
        parts.append("\n### Tasks\n")
        for s in summaries:
            desc = (
                _truncate(s.description)
                if s.description
                else _task_label(s.task_id, s.role)
            )
            line = f"- **{s.task_id}** — {desc}"
            if s.pr_url:
                line += f"\n  PR: {s.pr_url}"
            parts.append(line + "\n")

            if s.summary_text:
                parts.append(
                    "<details>\n"
                    "<summary>Agent summary</summary>\n"
                    "\n"
                    f"{s.summary_text}\n"
                    "\n"
                    "</details>\n"
                )

    # Aggregate concerns across all tasks.
    tasks_with_concerns = [s for s in summaries if s.concerns]
    if tasks_with_concerns:
        parts.append("\n## Concerns\n")
        for s in tasks_with_concerns:
            parts.append(f"\n### {s.task_id}\n")
            for concern in s.concerns:
                parts.append(f"- {concern}\n")

    # Aggregate ops concerns across all tasks.
    tasks_with_ops_concerns = [s for s in summaries if s.ops_concerns]
    if tasks_with_ops_concerns:
        parts.append("\n## Ops Concerns\n")
        for s in tasks_with_ops_concerns:
            parts.append(f"\n### {s.task_id}\n")
            for concern in s.ops_concerns:
                parts.append(f"- {concern}\n")

    return "\n".join(parts)


@dataclass
class GhWorkstreamIntegrator:
    """Create the workstream integration PR via GitHub CLI.

    Creates a pull request from the workstream's integration branch into
    its ``merge_target_branch``. Does NOT merge the PR — that is left
    for human review (or a future agent-merge step).
    """

    repo_path: Path

    def create_integration_pr(
        self, workstream_runtime: WorkstreamRuntime
    ) -> IntegrationResult:
        """Create a PR from the integration branch to the merge target.

        When the integration branch has no commits ahead of the target,
        the PR is skipped and the workstream transitions directly to
        ``MERGED``.  In this case, the integrator is the authoritative
        source for the target branch SHA (nothing changed).

        Args:
            workstream_runtime: Workstream runtime whose integration branch
                should be submitted as a PR.

        Returns:
            IntegrationResult: Whether the PR was skipped and the
            authoritative target branch SHA when skipped.
        """
        spec = workstream_runtime.spec
        branch_name = workstream_runtime.state.branch_name
        assert branch_name is not None, "branch_name must be set before integration"

        ahead = git.rev_list_count(
            self.repo_path, spec.merge_target_branch, branch_name
        )
        if ahead == 0:
            target_sha = git.rev_parse(self.repo_path, spec.merge_target_branch)
            workstream_runtime.mark_merged()
            return IntegrationResult(
                skipped=True, target_branch_authoritative_sha=target_sha
            )

        body = _build_pr_body(workstream_runtime)

        pr_url = gh.pr_create(
            self.repo_path,
            title=f"Integrate workstream {spec.id}",
            body=body,
            base=spec.merge_target_branch,
            head=branch_name,
        )

        workstream_runtime.mark_pr_created(pr_url)
        return IntegrationResult(skipped=False)
