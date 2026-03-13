"""Tests for agentrelay.agent_comm_protocol.policies — WorkflowPolicies and builders."""

from __future__ import annotations

import json

import pytest

from agentrelay.agent_comm_protocol.policies import (
    POLICIES_SCHEMA_VERSION,
    AdrPolicy,
    CommitPolicy,
    CompletionGatePolicy,
    PrBodySection,
    PrPolicy,
    ReviewPolicy,
    VerificationPolicy,
    WorkflowAction,
    WorkflowPolicies,
    build_policies,
    policies_to_dict,
)
from agentrelay.task import (
    AgentConfig,
    AgentRole,
    AgentVerbosity,
    ReviewConfig,
    Task,
)


def _task(**overrides: object) -> Task:
    """Create a Task with sensible defaults."""
    kwargs: dict[str, object] = {"id": "t1", "role": AgentRole.GENERIC}
    kwargs.update(overrides)
    return Task(**kwargs)  # type: ignore[arg-type]


class TestPolicyDataclasses:
    """Frozen dataclass construction for individual policy types."""

    def test_commit_policy(self) -> None:
        p = CommitPolicy(action=WorkflowAction.COMMIT_AND_PUSH)
        assert p.action == WorkflowAction.COMMIT_AND_PUSH
        with pytest.raises(AttributeError):
            p.action = WorkflowAction.CREATE_PR  # type: ignore[misc]

    def test_pr_policy(self) -> None:
        p = PrPolicy(
            action=WorkflowAction.CREATE_PR,
            base_branch="main",
            title_template="{task_id}",
            body_sections=(PrBodySection.SUMMARY,),
        )
        assert p.base_branch == "main"

    def test_completion_gate_policy(self) -> None:
        p = CompletionGatePolicy(
            command="pytest", max_attempts=3, output_file="out.txt"
        )
        assert p.max_attempts == 3

    def test_verification_policy(self) -> None:
        p = VerificationPolicy(commands=("pytest --collect-only",))
        assert p.commands == ("pytest --collect-only",)

    def test_adr_policy(self) -> None:
        p = AdrPolicy(verbosity=AgentVerbosity.STANDARD)
        assert p.verbosity == AgentVerbosity.STANDARD

    def test_review_policy(self) -> None:
        p = ReviewPolicy(model="claude-sonnet-4-6", review_on_attempt=1)
        assert p.model == "claude-sonnet-4-6"


class TestWorkflowPolicies:
    """Tests for the composed WorkflowPolicies dataclass."""

    def test_all_none(self) -> None:
        """All optional policies can be None."""
        p = WorkflowPolicies(
            schema_version="1",
            commit_policy=None,
            pr_policy=None,
            completion_gate=None,
            review=None,
            adr=None,
            verification=None,
        )
        assert p.commit_policy is None
        assert p.verification is None

    def test_frozen(self) -> None:
        p = WorkflowPolicies(
            schema_version="1",
            commit_policy=None,
            pr_policy=None,
            completion_gate=None,
            review=None,
            adr=None,
            verification=None,
        )
        with pytest.raises(AttributeError):
            p.schema_version = "2"  # type: ignore[misc]


class TestBuildPolicies:
    """Tests for build_policies."""

    def test_minimal_task(self) -> None:
        """Minimal task gets commit + PR policies, everything else None."""
        policies = build_policies(_task(), integration_branch="graph/demo")
        assert policies.schema_version == POLICIES_SCHEMA_VERSION
        assert policies.commit_policy is not None
        assert policies.commit_policy.action == WorkflowAction.COMMIT_AND_PUSH
        assert policies.pr_policy is not None
        assert policies.pr_policy.base_branch == "graph/demo"
        assert policies.completion_gate is None
        assert policies.review is None
        assert policies.adr is None
        assert policies.verification is None

    def test_completion_gate(self) -> None:
        """Task with completion_gate produces gate policy."""
        task = _task(completion_gate="pytest test/test_a.py", max_gate_attempts=3)
        policies = build_policies(task, integration_branch="main")
        assert policies.completion_gate is not None
        assert policies.completion_gate.command == "pytest test/test_a.py"
        assert policies.completion_gate.max_attempts == 3
        assert policies.completion_gate.output_file == "gate_last_output.txt"

    def test_completion_gate_default_max_attempts(self) -> None:
        """Uses default_max_gate_attempts when task.max_gate_attempts is None."""
        task = _task(completion_gate="pytest")
        policies = build_policies(
            task, integration_branch="main", default_max_gate_attempts=10
        )
        assert policies.completion_gate is not None
        assert policies.completion_gate.max_attempts == 10

    def test_review(self) -> None:
        """Task with review config produces review policy."""
        task = _task(
            review=ReviewConfig(
                agent=AgentConfig(model="claude-sonnet-4-6"),
                review_on_attempt=2,
            )
        )
        policies = build_policies(task, integration_branch="main")
        assert policies.review is not None
        assert policies.review.model == "claude-sonnet-4-6"
        assert policies.review.review_on_attempt == 2

    def test_adr_nonzero_verbosity(self) -> None:
        """ADR policy present when adr_verbosity != NONE."""
        task = _task(primary_agent=AgentConfig(adr_verbosity=AgentVerbosity.STANDARD))
        policies = build_policies(task, integration_branch="main")
        assert policies.adr is not None
        assert policies.adr.verbosity == AgentVerbosity.STANDARD

    def test_adr_none_verbosity(self) -> None:
        """ADR policy absent when adr_verbosity == NONE."""
        task = _task(primary_agent=AgentConfig(adr_verbosity=AgentVerbosity.NONE))
        policies = build_policies(task, integration_branch="main")
        assert policies.adr is None

    def test_test_writer_verification(self) -> None:
        """TEST_WRITER role gets default verification policy."""
        task = _task(role=AgentRole.TEST_WRITER)
        policies = build_policies(task, integration_branch="main")
        assert policies.verification is not None
        assert "pytest --collect-only" in policies.verification.commands

    def test_test_reviewer_verification(self) -> None:
        """TEST_REVIEWER role gets default verification policy."""
        task = _task(role=AgentRole.TEST_REVIEWER)
        policies = build_policies(task, integration_branch="main")
        assert policies.verification is not None

    def test_implementer_no_verification(self) -> None:
        """IMPLEMENTER role does not get default verification."""
        task = _task(role=AgentRole.IMPLEMENTER)
        policies = build_policies(task, integration_branch="main")
        assert policies.verification is None

    def test_integration_branch_flows_to_pr_policy(self) -> None:
        """integration_branch is used as pr_policy.base_branch."""
        policies = build_policies(_task(), integration_branch="feat/my-branch")
        assert policies.pr_policy is not None
        assert policies.pr_policy.base_branch == "feat/my-branch"


class TestPoliciesToDict:
    """Tests for policies_to_dict."""

    def test_structure(self) -> None:
        """Dict has expected top-level keys."""
        policies = build_policies(_task(), integration_branch="main")
        d = policies_to_dict(policies)
        assert set(d.keys()) == {
            "schema_version",
            "commit_policy",
            "pr_policy",
            "completion_gate",
            "review",
            "adr",
            "verification",
        }

    def test_none_policies_are_null(self) -> None:
        """None-valued policies become None in the dict."""
        policies = build_policies(_task(), integration_branch="main")
        d = policies_to_dict(policies)
        assert d["completion_gate"] is None
        assert d["review"] is None
        assert d["adr"] is None
        assert d["verification"] is None

    def test_present_policies_are_dicts(self) -> None:
        """Present policies are serialized as dicts."""
        policies = build_policies(_task(), integration_branch="main")
        d = policies_to_dict(policies)
        assert isinstance(d["commit_policy"], dict)
        assert d["commit_policy"]["action"] == "commit_and_push"

    def test_tuples_become_lists(self) -> None:
        """Tuple fields are serialized as lists for JSON compatibility."""
        task = _task(role=AgentRole.TEST_WRITER)
        policies = build_policies(task, integration_branch="main")
        d = policies_to_dict(policies)
        assert isinstance(d["verification"]["commands"], list)
        assert isinstance(d["pr_policy"]["body_sections"], list)

    def test_json_serializable(self) -> None:
        """Round-trip through JSON works."""
        task = _task(
            role=AgentRole.TEST_WRITER,
            completion_gate="pytest",
            review=ReviewConfig(agent=AgentConfig()),
            primary_agent=AgentConfig(adr_verbosity=AgentVerbosity.DETAILED),
        )
        policies = build_policies(task, integration_branch="main")
        d = policies_to_dict(policies)
        text = json.dumps(d)
        assert json.loads(text) == d
