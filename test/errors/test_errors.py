"""Tests for integration error hierarchy and classification helpers."""

from agentrelay.errors import (
    AgentLaunchIntegrationError,
    ExpectedTaskFailureError,
    IntegrationBoundary,
    IntegrationError,
    IntegrationFailureClass,
    InternalIntegrationError,
    PullRequestIntegrationError,
    SignalIntegrationError,
    WorkspaceIntegrationError,
    classify_integration_error,
)


def test_expected_task_failure_error_classification_and_boundary() -> None:
    exc = ExpectedTaskFailureError(
        "gate failed",
        boundary=IntegrationBoundary.SIGNAL,
    )

    assert isinstance(exc, IntegrationError)
    assert exc.failure_class == IntegrationFailureClass.EXPECTED_TASK_FAILURE
    assert exc.boundary == IntegrationBoundary.SIGNAL


def test_internal_integration_error_classification() -> None:
    exc = InternalIntegrationError(
        "unexpected launcher crash",
        boundary=IntegrationBoundary.AGENT_LAUNCH,
    )

    assert isinstance(exc, IntegrationError)
    assert exc.failure_class == IntegrationFailureClass.INTERNAL_ERROR
    assert exc.boundary == IntegrationBoundary.AGENT_LAUNCH


def test_boundary_specific_internal_errors_have_expected_boundaries() -> None:
    workspace = WorkspaceIntegrationError("workspace failure")
    signal = SignalIntegrationError("signal failure")
    pr = PullRequestIntegrationError("pr failure")
    launcher = AgentLaunchIntegrationError("launcher failure")

    assert workspace.boundary == IntegrationBoundary.WORKSPACE
    assert signal.boundary == IntegrationBoundary.SIGNAL
    assert pr.boundary == IntegrationBoundary.PULL_REQUEST
    assert launcher.boundary == IntegrationBoundary.AGENT_LAUNCH


def test_classify_integration_error_uses_failure_class_for_typed_errors() -> None:
    expected = ExpectedTaskFailureError(
        "task-level failure",
        boundary=IntegrationBoundary.PULL_REQUEST,
    )
    internal = WorkspaceIntegrationError("internal workspace problem")

    assert (
        classify_integration_error(expected)
        == IntegrationFailureClass.EXPECTED_TASK_FAILURE
    )
    assert (
        classify_integration_error(internal) == IntegrationFailureClass.INTERNAL_ERROR
    )


def test_classify_integration_error_defaults_non_integration_errors_to_internal() -> (
    None
):
    assert classify_integration_error(RuntimeError("boom")) == (
        IntegrationFailureClass.INTERNAL_ERROR
    )


def test_integration_error_cause_via_dunder_cause() -> None:
    cause = ValueError("bad input")
    try:
        raise SignalIntegrationError("signal parse error") from cause
    except SignalIntegrationError as exc:
        assert exc.__cause__ is cause
