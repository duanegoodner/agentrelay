"""Implementations of :class:`~agentrelay.workstream.core.io.WorkstreamIntegrator`.

Classes:
    GhWorkstreamIntegrator: Creates a workstream integration PR via GitHub CLI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentrelay.ops import gh, git
from agentrelay.workstream.core.runtime import WorkstreamRuntime


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
            desc = s.description or "(no description)"
            line = f"- **{s.task_id}** — {desc}"
            if s.pr_url:
                line += f"\n  PR: {s.pr_url}"
            parts.append(line + "\n")

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

    def create_integration_pr(self, workstream_runtime: WorkstreamRuntime) -> None:
        """Create a PR from the integration branch to the merge target.

        Args:
            workstream_runtime: Workstream runtime whose integration branch
                should be submitted as a PR.
        """
        spec = workstream_runtime.spec
        branch_name = workstream_runtime.state.branch_name
        assert branch_name is not None, "branch_name must be set before integration"

        ahead = git.rev_list_count(
            self.repo_path, spec.merge_target_branch, branch_name
        )
        if ahead == 0:
            workstream_runtime.mark_merged()
            return

        body = _build_pr_body(workstream_runtime)

        pr_url = gh.pr_create(
            self.repo_path,
            title=f"Integrate workstream {spec.id}",
            body=body,
            base=spec.merge_target_branch,
            head=branch_name,
        )

        workstream_runtime.mark_pr_created(pr_url)
