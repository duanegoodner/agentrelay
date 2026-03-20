"""Per-step protocols for workstream execution.

This module defines fine-grained protocol interfaces for each step of the
workstream lifecycle. :class:`~agentrelay.workstream.core.runner.WorkstreamRunner`
holds these protocol fields directly.

Protocols:
    WorkstreamPreparer: Provision worktree and integration branch.
    WorkstreamIntegrator: Create integration PR.
    WorkstreamTeardown: Clean up worktree and integration branch.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agentrelay.workstream.core.runtime import WorkstreamRuntime


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

    def create_integration_pr(self, workstream_runtime: WorkstreamRuntime) -> None:
        """Create a PR from the integration branch to the merge target.

        Args:
            workstream_runtime: Workstream runtime whose integration branch
                should be submitted as a PR.
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


__all__ = [
    "WorkstreamIntegrator",
    "WorkstreamPreparer",
    "WorkstreamTeardown",
]
