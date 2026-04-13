"""Per-step protocols for workstream execution.

This module defines fine-grained protocol interfaces for each step of the
workstream lifecycle. :class:`~agentrelay.workstream.core.runner.WorkstreamRunner`
holds these protocol fields directly.

Protocols:
    WorkstreamPreparer: Provision worktree and integration branch.
    WorkstreamIntegrator: Create integration PR.
    WorkstreamTeardown: Clean up worktree and integration branch.
    IntegrationMergeChecker: Poll for human-initiated merge of integration PR.
    IntegrationAutoMerger: Merge an integration PR on the hosting platform.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from agentrelay.workstream.core.runtime import WorkstreamRuntime

# ── Result dataclasses ──


@dataclass(frozen=True)
class IntegrationResult:
    """Result from workstream integration PR creation.

    Attributes:
        skipped: True when the integration branch had no commits ahead
            of the target and the PR was skipped.
        target_branch_authoritative_sha: SHA of the target branch when
            ``skipped=True`` (the integrator is the authoritative source).
            ``None`` when ``skipped=False`` — the merger or checker that
            performs the actual merge is the authoritative source instead.
    """

    skipped: bool
    target_branch_authoritative_sha: Optional[str] = None


@dataclass(frozen=True)
class IntegrationMergeResult:
    """Result from auto-merging a workstream integration PR.

    Attributes:
        target_branch_before_merge: SHA of the target branch immediately
            before the integration PR was merged.
    """

    target_branch_before_merge: str


@dataclass(frozen=True)
class IntegrationMergeCheckResult:
    """Result from polling whether a workstream integration PR is merged.

    Attributes:
        merged: Whether the integration PR has been merged.
        target_branch_before_merge: SHA of the target branch before the
            merge commit.  Populated when ``merged=True``, derived from
            the merge commit's first parent.  ``None`` when ``merged=False``
            or when the merge commit SHA could not be determined.
    """

    merged: bool
    target_branch_before_merge: Optional[str] = None


# ── Per-step protocols ──


@runtime_checkable
class WorkstreamPreparer(Protocol):
    """Provision workspace infrastructure for a workstream lane."""

    def prepare_workstream(self, workstream_runtime: WorkstreamRuntime) -> None:
        """Provision worktree and integration branch for this workstream.

        Args:
            workstream_runtime: Workstream runtime to provision.
        """
        ...


@runtime_checkable
class WorkstreamIntegrator(Protocol):
    """Create integration PR for a workstream lane."""

    def create_integration_pr(
        self, workstream_runtime: WorkstreamRuntime
    ) -> IntegrationResult:
        """Create a PR from the integration branch to the merge target.

        Args:
            workstream_runtime: Workstream runtime whose integration branch
                should be submitted as a PR.

        Returns:
            IntegrationResult: Whether the PR was skipped (no commits ahead)
            and the authoritative target branch SHA when skipped.
        """
        ...


@runtime_checkable
class WorkstreamTeardown(Protocol):
    """Clean up workstream workspace infrastructure."""

    def teardown_workstream(self, workstream_runtime: WorkstreamRuntime) -> None:
        """Delete worktree and integration branch for this workstream.

        Args:
            workstream_runtime: Workstream runtime whose resources should be
                cleaned up.
        """
        ...


@runtime_checkable
class IntegrationMergeChecker(Protocol):
    """Check whether a workstream's integration PR has been merged."""

    def is_merged(
        self, workstream_runtime: WorkstreamRuntime
    ) -> IntegrationMergeCheckResult:
        """Check whether the integration PR for this workstream is merged.

        Args:
            workstream_runtime: Workstream runtime to check.

        Returns:
            IntegrationMergeCheckResult: Merge status and pre-merge SHA
            (when merged, derived from the merge commit's first parent).
        """
        ...


@runtime_checkable
class IntegrationAutoMerger(Protocol):
    """Merge a workstream's integration PR on the hosting platform."""

    def merge(self, workstream_runtime: WorkstreamRuntime) -> IntegrationMergeResult:
        """Merge the integration PR for this workstream.

        Args:
            workstream_runtime: Workstream runtime whose integration PR
                should be merged.

        Returns:
            IntegrationMergeResult: Pre-merge SHA for rollback support.

        Raises:
            RuntimeError: If the merge fails.
        """
        ...


__all__ = [
    "IntegrationAutoMerger",
    "IntegrationMergeCheckResult",
    "IntegrationMergeChecker",
    "IntegrationMergeResult",
    "IntegrationResult",
    "WorkstreamIntegrator",
    "WorkstreamPreparer",
    "WorkstreamTeardown",
]
