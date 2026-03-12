"""Typed integration error model and classification helpers.

This package provides boundary-aware exceptions for side-effect adapters and a
small classifier used to distinguish expected task-level failures from
internal/system integration failures.
"""

from __future__ import annotations

from enum import Enum


class IntegrationBoundary(str, Enum):
    """External boundary where an integration failure originated.

    Attributes:
        WORKSPACE: Workspace provisioning/cleanup operations.
        SIGNAL: Instruction/signal publication or completion polling.
        PULL_REQUEST: Pull-request create/merge/status operations.
        AGENT_LAUNCH: Agent process launch or kickoff behavior.
    """

    WORKSPACE = "workspace"
    SIGNAL = "signal"
    PULL_REQUEST = "pull_request"
    AGENT_LAUNCH = "agent_launch"


class IntegrationFailureClass(str, Enum):
    """Classification used for orchestration policy decisions.

    Attributes:
        EXPECTED_TASK_FAILURE: Expected task-level failure (retry policy may apply).
        INTERNAL_ERROR: Internal/system failure (usually fail-fast).
    """

    EXPECTED_TASK_FAILURE = "expected_task_failure"
    INTERNAL_ERROR = "internal_error"


class IntegrationError(Exception):
    """Base integration error carrying boundary and failure classification.

    Use ``raise IntegrationError(...) from original_exc`` to chain the
    underlying cause (accessible via ``__cause__``).

    Attributes:
        boundary: Integration boundary where failure originated.
        failure_class: Classification used by orchestration policy.
    """

    def __init__(
        self,
        message: str,
        *,
        boundary: IntegrationBoundary,
        failure_class: IntegrationFailureClass,
    ) -> None:
        """Initialize a boundary-aware integration error.

        Args:
            message: Human-readable error message.
            boundary: Boundary where the failure originated.
            failure_class: Classification for orchestration policy.
        """
        super().__init__(message)
        self.boundary = boundary
        self.failure_class = failure_class


class ExpectedTaskFailureError(IntegrationError):
    """Expected task-level failure from an integration boundary."""

    def __init__(
        self,
        message: str,
        *,
        boundary: IntegrationBoundary,
    ) -> None:
        """Initialize an expected task-level failure.

        Args:
            message: Human-readable error message.
            boundary: Boundary where the failure originated.
        """
        super().__init__(
            message,
            boundary=boundary,
            failure_class=IntegrationFailureClass.EXPECTED_TASK_FAILURE,
        )


class InternalIntegrationError(IntegrationError):
    """Internal/system integration failure from an external boundary."""

    def __init__(
        self,
        message: str,
        *,
        boundary: IntegrationBoundary,
    ) -> None:
        """Initialize an internal/system integration failure.

        Args:
            message: Human-readable error message.
            boundary: Boundary where the failure originated.
        """
        super().__init__(
            message,
            boundary=boundary,
            failure_class=IntegrationFailureClass.INTERNAL_ERROR,
        )


class WorkspaceIntegrationError(InternalIntegrationError):
    """Internal workspace integration failure."""

    def __init__(self, message: str) -> None:
        """Initialize a workspace integration failure.

        Args:
            message: Human-readable error message.
        """
        super().__init__(message, boundary=IntegrationBoundary.WORKSPACE)


class SignalIntegrationError(InternalIntegrationError):
    """Internal signal boundary integration failure."""

    def __init__(self, message: str) -> None:
        """Initialize a signal integration failure.

        Args:
            message: Human-readable error message.
        """
        super().__init__(message, boundary=IntegrationBoundary.SIGNAL)


class PullRequestIntegrationError(InternalIntegrationError):
    """Internal pull-request boundary integration failure."""

    def __init__(self, message: str) -> None:
        """Initialize a pull-request integration failure.

        Args:
            message: Human-readable error message.
        """
        super().__init__(
            message,
            boundary=IntegrationBoundary.PULL_REQUEST,
        )


class AgentLaunchIntegrationError(InternalIntegrationError):
    """Internal agent launch/kickoff integration failure."""

    def __init__(self, message: str) -> None:
        """Initialize an agent-launch integration failure.

        Args:
            message: Human-readable error message.
        """
        super().__init__(
            message,
            boundary=IntegrationBoundary.AGENT_LAUNCH,
        )


def classify_integration_error(exc: BaseException) -> IntegrationFailureClass:
    """Classify an exception for orchestration retry/fail-fast policy.

    Args:
        exc: Exception raised by integration code.

    Returns:
        IntegrationFailureClass: Expected task failure or internal error.
            Non-``IntegrationError`` exceptions default to ``INTERNAL_ERROR``.
    """
    if isinstance(exc, IntegrationError):
        return exc.failure_class
    return IntegrationFailureClass.INTERNAL_ERROR


__all__ = [
    "AgentLaunchIntegrationError",
    "ExpectedTaskFailureError",
    "IntegrationBoundary",
    "IntegrationError",
    "IntegrationFailureClass",
    "InternalIntegrationError",
    "PullRequestIntegrationError",
    "SignalIntegrationError",
    "WorkspaceIntegrationError",
    "classify_integration_error",
]
