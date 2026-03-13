"""Workflow policies schema and builder — Layer 3 of the agent communication protocol.

Composable workflow configuration: each policy key is independently present or
``None``.  Framework adapters translate the abstract vocabulary into
framework-specific actions.

Constants:
    POLICIES_SCHEMA_VERSION: Current policies schema version string.

Classes:
    CommitPolicy: Commit and push configuration.
    PrPolicy: Pull request creation configuration.
    CompletionGatePolicy: Gate loop configuration.
    VerificationPolicy: Pre-completion verification commands.
    AdrPolicy: Architecture decision record configuration.
    ReviewPolicy: Self-review configuration.
    WorkflowPolicies: Frozen Layer-3 composed policies.

Functions:
    build_policies: Build :class:`WorkflowPolicies` from task spec and context.
    policies_to_dict: Serialize :class:`WorkflowPolicies` to a JSON-compatible dict.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from agentrelay.task import AgentRole, AgentVerbosity, Task

POLICIES_SCHEMA_VERSION = "1"


class WorkflowAction(str, Enum):
    """Abstract workflow actions that adapters translate to framework-specific commands.

    Defined by the agent communication protocol Layer 3 vocabulary.
    """

    COMMIT_AND_PUSH = "commit_and_push"
    CREATE_PR = "create_pr"
    SIGNAL_DONE = "signal_done"
    SIGNAL_FAILED = "signal_failed"
    RUN_COMPLETION_GATE = "run_completion_gate"
    RECORD_CONCERN = "record_concern"
    WRITE_ADR = "write_adr"
    RUN_VERIFICATION = "run_verification"


class PrBodySection(str, Enum):
    """Sections that can appear in an auto-generated PR body."""

    SUMMARY = "summary"
    FILES_CHANGED = "files_changed"


@dataclass(frozen=True)
class CommitPolicy:
    """Policy for committing work.

    Attributes:
        action: Workflow action for this policy.
    """

    action: WorkflowAction


@dataclass(frozen=True)
class PrPolicy:
    """Policy for creating pull requests.

    Attributes:
        action: Workflow action for this policy.
        base_branch: Branch the PR targets.
        title_template: Template for the PR title (e.g. ``"{task_id}"``).
        body_sections: Sections to include in the PR body.
    """

    action: WorkflowAction
    base_branch: str
    title_template: str
    body_sections: tuple[PrBodySection, ...]


@dataclass(frozen=True)
class CompletionGatePolicy:
    """Policy for running a completion gate command with retry logic.

    Attributes:
        command: Shell command to execute (exit code 0 = pass).
        max_attempts: Maximum number of gate attempts.
        output_file: Filename for capturing last gate output.
    """

    command: str
    max_attempts: int
    output_file: str


@dataclass(frozen=True)
class VerificationPolicy:
    """Policy for pre-completion verification commands.

    Attributes:
        commands: Shell commands to run for verification.
    """

    commands: tuple[str, ...]


@dataclass(frozen=True)
class AdrPolicy:
    """Policy for architecture decision record writing.

    Attributes:
        verbosity: Detail level for ADR output.
    """

    verbosity: AgentVerbosity


@dataclass(frozen=True)
class ReviewPolicy:
    """Policy for self-review.

    Attributes:
        model: Model identifier for the review agent, or ``None``.
        review_on_attempt: Attempt number at which to start review.
    """

    model: Optional[str]
    review_on_attempt: int


@dataclass(frozen=True)
class WorkflowPolicies:
    """Frozen Layer-3 policies: composable workflow configuration.

    Each optional field is independently ``None`` (behavior absent) or
    present (behavior active).  Framework adapters read these policies and
    translate them into framework-specific actions.

    Attributes:
        schema_version: Schema version string.
        commit_policy: Commit and push policy, or ``None``.
        pr_policy: PR creation policy, or ``None``.
        completion_gate: Gate loop policy, or ``None``.
        review: Self-review policy, or ``None``.
        adr: ADR writing policy, or ``None``.
        verification: Verification command policy, or ``None``.
    """

    schema_version: str
    commit_policy: Optional[CommitPolicy]
    pr_policy: Optional[PrPolicy]
    completion_gate: Optional[CompletionGatePolicy]
    review: Optional[ReviewPolicy]
    adr: Optional[AdrPolicy]
    verification: Optional[VerificationPolicy]


def build_policies(
    task: Task,
    integration_branch: str,
    default_max_gate_attempts: int = 5,
) -> WorkflowPolicies:
    """Build :class:`WorkflowPolicies` from a task spec and contextual data.

    Derives policies from the task's configuration:

    - ``commit_policy``: always present (``commit_and_push``).
    - ``pr_policy``: always present; ``base_branch`` from *integration_branch*.
    - ``completion_gate``: present if ``task.completion_gate`` is set.
    - ``review``: present if ``task.review`` is set.
    - ``adr``: present if ``task.primary_agent.adr_verbosity`` is not ``NONE``.
    - ``verification``: present for ``TEST_WRITER`` and ``TEST_REVIEWER`` roles
      (default ``pytest --collect-only``).

    Args:
        task: Frozen task specification.
        integration_branch: Branch for PR base.
        default_max_gate_attempts: Fallback when ``task.max_gate_attempts``
            is ``None`` but ``task.completion_gate`` is set.

    Returns:
        Composable workflow configuration.
    """
    commit_policy = CommitPolicy(action=WorkflowAction.COMMIT_AND_PUSH)

    pr_policy = PrPolicy(
        action=WorkflowAction.CREATE_PR,
        base_branch=integration_branch,
        title_template="{task_id}",
        body_sections=(PrBodySection.SUMMARY, PrBodySection.FILES_CHANGED),
    )

    completion_gate: Optional[CompletionGatePolicy] = None
    if task.completion_gate is not None:
        completion_gate = CompletionGatePolicy(
            command=task.completion_gate,
            max_attempts=task.max_gate_attempts or default_max_gate_attempts,
            output_file="gate_last_output.txt",
        )

    review: Optional[ReviewPolicy] = None
    if task.review is not None:
        review = ReviewPolicy(
            model=task.review.agent.model,
            review_on_attempt=task.review.review_on_attempt,
        )

    adr: Optional[AdrPolicy] = None
    if task.primary_agent.adr_verbosity != AgentVerbosity.NONE:
        adr = AdrPolicy(verbosity=task.primary_agent.adr_verbosity)

    verification: Optional[VerificationPolicy] = None
    if task.role in (AgentRole.TEST_WRITER, AgentRole.TEST_REVIEWER):
        verification = VerificationPolicy(commands=("pytest --collect-only",))

    return WorkflowPolicies(
        schema_version=POLICIES_SCHEMA_VERSION,
        commit_policy=commit_policy,
        pr_policy=pr_policy,
        completion_gate=completion_gate,
        review=review,
        adr=adr,
        verification=verification,
    )


def _serialize_value(value: object) -> object:
    """Serialize a single value for JSON output."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_serialize_value(v) for v in value]
    return value


def _policy_to_dict(policy: object) -> dict[str, Any]:
    """Convert a frozen policy dataclass to a dict, handling enums and tuples."""
    return {key: _serialize_value(value) for key, value in policy.__dict__.items()}


def policies_to_dict(policies: WorkflowPolicies) -> dict[str, Any]:
    """Serialize :class:`WorkflowPolicies` to a JSON-compatible dict.

    The dict structure matches the Layer-3 schema defined in
    ``docs/AGENT_COMM_PROTOCOL.md``.  ``None``-valued policies become
    JSON ``null``.

    Args:
        policies: Frozen policies to serialize.

    Returns:
        Dict with ``schema_version`` and one key per policy type.
    """
    return {
        "schema_version": policies.schema_version,
        "commit_policy": (
            _policy_to_dict(policies.commit_policy)
            if policies.commit_policy is not None
            else None
        ),
        "pr_policy": (
            _policy_to_dict(policies.pr_policy)
            if policies.pr_policy is not None
            else None
        ),
        "completion_gate": (
            _policy_to_dict(policies.completion_gate)
            if policies.completion_gate is not None
            else None
        ),
        "review": (
            _policy_to_dict(policies.review) if policies.review is not None else None
        ),
        "adr": (_policy_to_dict(policies.adr) if policies.adr is not None else None),
        "verification": (
            _policy_to_dict(policies.verification)
            if policies.verification is not None
            else None
        ),
    }


__all__ = [
    "POLICIES_SCHEMA_VERSION",
    "AdrPolicy",
    "CommitPolicy",
    "CompletionGatePolicy",
    "PrBodySection",
    "PrPolicy",
    "ReviewPolicy",
    "VerificationPolicy",
    "WorkflowAction",
    "WorkflowPolicies",
    "build_policies",
    "policies_to_dict",
]
