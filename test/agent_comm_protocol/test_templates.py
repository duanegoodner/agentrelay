"""Tests for agentrelay.agent_comm_protocol.templates — role template resolution."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agentrelay.agent_comm_protocol.manifest import TaskManifest
from agentrelay.agent_comm_protocol.templates import resolve_instructions
from agentrelay.sandbox import SandboxType
from agentrelay.task import AdrVerbosity, AgentRole


def _manifest(**overrides: object) -> TaskManifest:
    """Create a TaskManifest with sensible defaults."""
    kwargs: dict[str, object] = {
        "schema_version": "1",
        "task_id": "my_task",
        "role": AgentRole.TEST_WRITER,
        "description": "Write tests for greet module",
        "src_paths": (Path("src/greet.py"),),
        "test_paths": (Path("test/test_greet.py"),),
        "spec_path": None,
        "branch_name": "graph/demo/my_task",
        "integration_branch": "graph/demo",
        "attempt_num": 0,
        "graph_name": "demo",
        "dependencies": {},
    }
    kwargs.update(overrides)
    return TaskManifest(**kwargs)  # type: ignore[arg-type]


class TestResolveInstructions:
    """Tests for resolve_instructions."""

    def test_test_writer(self) -> None:
        """TEST_WRITER loads template and substitutes paths."""
        text = resolve_instructions(AgentRole.TEST_WRITER, _manifest())
        assert "TEST_WRITER" in text
        assert "src/greet.py" in text
        assert "test/test_greet.py" in text

    def test_spec_writer(self) -> None:
        """SPEC_WRITER loads template and substitutes paths."""
        m = _manifest(role=AgentRole.SPEC_WRITER)
        text = resolve_instructions(AgentRole.SPEC_WRITER, m)
        assert "SPEC_WRITER" in text
        assert "src/greet.py" in text

    def test_test_reviewer(self) -> None:
        """TEST_REVIEWER loads template and substitutes task_id."""
        text = resolve_instructions(AgentRole.TEST_REVIEWER, _manifest())
        assert "TEST_REVIEWER" in text

    def test_implementer(self) -> None:
        """IMPLEMENTER loads template and substitutes paths."""
        text = resolve_instructions(AgentRole.IMPLEMENTER, _manifest())
        assert "IMPLEMENTER" in text
        assert "src/greet.py" in text
        assert "test/test_greet.py" in text

    def test_generic_with_description(self) -> None:
        """GENERIC role puts description in What to Do section."""
        m = _manifest(description="Do something custom")
        text = resolve_instructions(AgentRole.GENERIC, m)
        assert "## What to Do" in text
        assert "Do something custom" in text

    def test_generic_without_description_raises(self) -> None:
        """GENERIC role with no description raises ValueError."""
        m = _manifest(description=None)
        with pytest.raises(ValueError, match="GENERIC.*description"):
            resolve_instructions(AgentRole.GENERIC, m)

    def test_nonexistent_adapter_falls_back_to_shared(self) -> None:
        """Unknown adapter_name falls back to shared template."""
        text = resolve_instructions(
            AgentRole.TEST_WRITER, _manifest(), adapter_name="nonexistent_adapter"
        )
        assert "TEST_WRITER" in text
        assert "src/greet.py" in text

    def test_no_leftover_placeholders(self) -> None:
        """Standard roles produce no leftover $var placeholders."""
        for role in (
            AgentRole.TEST_WRITER,
            AgentRole.SPEC_WRITER,
            AgentRole.TEST_REVIEWER,
            AgentRole.IMPLEMENTER,
        ):
            text = resolve_instructions(role, _manifest())
            leftover = re.findall(r"\$[a-z_]+", text)
            assert leftover == [], f"Role {role}: leftover placeholders {leftover}"

    def test_submission_includes_no_pr_option(self) -> None:
        """Submission section mentions agentrelay-complete-no-pr."""
        text = resolve_instructions(AgentRole.TEST_WRITER, _manifest())
        assert "agentrelay-complete-no-pr" in text

    def test_test_reviewer_mentions_no_pr_completion(self) -> None:
        """Test reviewer template mentions completing without a PR."""
        text = resolve_instructions(AgentRole.TEST_REVIEWER, _manifest())
        assert "complete without a PR" in text

    def test_empty_paths_show_placeholder(self) -> None:
        """Empty paths are shown as '(none specified)'."""
        m = _manifest(src_paths=(), test_paths=())
        text = resolve_instructions(AgentRole.TEST_WRITER, m)
        assert "(none specified)" in text


class TestDocumentStructure:
    """Tests for the work-order document structure."""

    def test_title_contains_task_id(self) -> None:
        text = resolve_instructions(AgentRole.TEST_WRITER, _manifest())
        assert "# Instructions for Task my_task" in text

    def test_role_section_present(self) -> None:
        text = resolve_instructions(AgentRole.SPEC_WRITER, _manifest())
        assert "## Role" in text
        assert "SPEC_WRITER" in text

    def test_tools_section_present_when_declared(self) -> None:
        m = _manifest(tools=("pixi",))
        text = resolve_instructions(AgentRole.TEST_WRITER, m)
        assert "## Tools" in text
        assert "pixi run" in text

    def test_tools_section_absent_when_no_tools(self) -> None:
        text = resolve_instructions(AgentRole.TEST_WRITER, _manifest())
        assert "## Tools" not in text

    def test_what_to_do_section_present(self) -> None:
        text = resolve_instructions(AgentRole.TEST_WRITER, _manifest())
        assert "## What to Do" in text

    def test_concerns_note_present(self) -> None:
        text = resolve_instructions(AgentRole.TEST_WRITER, _manifest())
        assert "agentrelay-concern" in text
        assert "agentrelay-ops-concern" in text

    def test_submission_section_present(self) -> None:
        text = resolve_instructions(AgentRole.TEST_WRITER, _manifest())
        assert "## Submitting Your Work" in text

    def test_task_details_present_for_role_with_description(self) -> None:
        text = resolve_instructions(AgentRole.SPEC_WRITER, _manifest())
        assert "## Task Details" in text
        assert "Write tests for greet module" in text

    def test_task_details_absent_for_generic(self) -> None:
        m = _manifest(description="Do something")
        text = resolve_instructions(AgentRole.GENERIC, m)
        assert "## Task Details" not in text

    def test_task_details_absent_when_no_description(self) -> None:
        m = _manifest(description=None)
        text = resolve_instructions(AgentRole.SPEC_WRITER, m)
        assert "## Task Details" not in text

    def test_generic_description_in_what_to_do(self) -> None:
        m = _manifest(description="Do something custom")
        text = resolve_instructions(AgentRole.GENERIC, m)
        assert "## What to Do" in text
        assert "Do something custom" in text


class TestConcernGuidance:
    """Tests that role templates include concern-discovery guidance."""

    def test_spec_writer_has_cross_check_step(self) -> None:
        """SPEC_WRITER template prompts cross-checking requirements."""
        m = _manifest(role=AgentRole.SPEC_WRITER)
        text = resolve_instructions(AgentRole.SPEC_WRITER, m)
        assert "contradict" in text.lower()

    def test_test_writer_has_contradiction_check(self) -> None:
        """TEST_WRITER template prompts checking for contradictory docstrings."""
        text = resolve_instructions(AgentRole.TEST_WRITER, _manifest())
        assert "contradict" in text.lower()

    def test_test_reviewer_has_consistency_check(self) -> None:
        """TEST_REVIEWER template prompts checking tests against docstrings."""
        text = resolve_instructions(AgentRole.TEST_REVIEWER, _manifest())
        assert "contradict" in text.lower()

    def test_implementer_has_cross_check(self) -> None:
        """IMPLEMENTER template prompts checking tests against docstrings."""
        text = resolve_instructions(AgentRole.IMPLEMENTER, _manifest())
        assert "contradict" in text.lower()

    def test_concerns_note_mentions_design_concerns(self) -> None:
        """Concerns note includes design concern guidance."""
        text = resolve_instructions(AgentRole.TEST_WRITER, _manifest())
        assert "agentrelay-concern" in text
        assert "design concern" in text.lower()


class TestAdrSection:
    """Tests for ADR section injection in instructions."""

    def test_adr_section_absent_when_none(self) -> None:
        """No ADR section when adr_verbosity is NONE (default)."""
        text = resolve_instructions(AgentRole.TEST_WRITER, _manifest())
        assert "## Architecture Decision Record" not in text

    def test_adr_section_present_when_standard(self) -> None:
        """ADR section appears when adr_verbosity is STANDARD."""
        text = resolve_instructions(
            AgentRole.TEST_WRITER, _manifest(), adr_verbosity=AdrVerbosity.STANDARD
        )
        assert "## Architecture Decision Record" in text
        assert "docs/adr/my_task.md" in text

    def test_adr_section_present_when_detailed(self) -> None:
        """ADR section appears with extra sections when DETAILED."""
        text = resolve_instructions(
            AgentRole.TEST_WRITER, _manifest(), adr_verbosity=AdrVerbosity.DETAILED
        )
        assert "## Architecture Decision Record" in text
        assert "Alternatives Considered" in text
        assert "Trade-offs" in text
        assert "Implementation Notes" in text

    def test_adr_section_present_when_educational(self) -> None:
        """ADR section appears with annotations when EDUCATIONAL."""
        text = resolve_instructions(
            AgentRole.TEST_WRITER, _manifest(), adr_verbosity=AdrVerbosity.EDUCATIONAL
        )
        assert "## Architecture Decision Record" in text
        assert "Alternatives Considered" in text
        assert "why" in text.split("## Architecture Decision Record")[1].lower()

    def test_adr_section_uses_task_id_in_path(self) -> None:
        """ADR output path includes the task_id."""
        m = _manifest(task_id="custom_task")
        text = resolve_instructions(
            AgentRole.TEST_WRITER, m, adr_verbosity=AdrVerbosity.STANDARD
        )
        assert "docs/adr/custom_task.md" in text

    def test_adr_section_for_generic_role(self) -> None:
        """ADR section works with GENERIC role too."""
        m = _manifest(description="Do something custom")
        text = resolve_instructions(
            AgentRole.GENERIC, m, adr_verbosity=AdrVerbosity.STANDARD
        )
        assert "## Architecture Decision Record" in text
        assert "docs/adr/my_task.md" in text

    def test_adr_section_before_submission(self) -> None:
        """ADR section appears before Submitting Your Work section."""
        text = resolve_instructions(
            AgentRole.TEST_WRITER, _manifest(), adr_verbosity=AdrVerbosity.STANDARD
        )
        adr_pos = text.index("## Architecture Decision Record")
        submission_pos = text.index("## Submitting Your Work")
        assert adr_pos < submission_pos

    def test_adr_section_after_what_to_do(self) -> None:
        """ADR section appears after What to Do section."""
        text = resolve_instructions(
            AgentRole.TEST_WRITER, _manifest(), adr_verbosity=AdrVerbosity.STANDARD
        )
        what_to_do_pos = text.index("## What to Do")
        adr_pos = text.index("## Architecture Decision Record")
        assert what_to_do_pos < adr_pos

    def test_standard_has_five_sections(self) -> None:
        """STANDARD verbosity requests five ADR sections."""
        text = resolve_instructions(
            AgentRole.TEST_WRITER, _manifest(), adr_verbosity=AdrVerbosity.STANDARD
        )
        for section in ("Title", "Status", "Context", "Decision", "Consequences"):
            assert f"**{section}**" in text

    def test_standard_omits_detailed_sections(self) -> None:
        """STANDARD verbosity does NOT include Alternatives or Implementation Notes."""
        text = resolve_instructions(
            AgentRole.TEST_WRITER, _manifest(), adr_verbosity=AdrVerbosity.STANDARD
        )
        assert "Alternatives Considered" not in text
        assert "Implementation Notes" not in text

    def test_no_leftover_placeholders_with_adr(self) -> None:
        """No leftover $var placeholders when ADR section is active."""
        for role in (
            AgentRole.TEST_WRITER,
            AgentRole.SPEC_WRITER,
            AgentRole.TEST_REVIEWER,
            AgentRole.IMPLEMENTER,
        ):
            text = resolve_instructions(
                role, _manifest(), adr_verbosity=AdrVerbosity.STANDARD
            )
            leftover = re.findall(r"\$[a-z_]+", text)
            assert leftover == [], f"Role {role}: leftover placeholders {leftover}"


class TestIsolationSection:
    """Tests for isolation boundary section injection in instructions."""

    def test_isolation_section_absent_when_none(self) -> None:
        """No isolation section when sandbox_type is None (default)."""
        text = resolve_instructions(AgentRole.TEST_WRITER, _manifest())
        assert "## Isolation Boundary" not in text

    def test_isolation_section_absent_when_sandbox_none(self) -> None:
        """No isolation section when sandbox_type is NONE."""
        text = resolve_instructions(
            AgentRole.TEST_WRITER, _manifest(), sandbox_type=SandboxType.NONE
        )
        assert "## Isolation Boundary" not in text

    def test_isolation_section_present_when_oci(self) -> None:
        """Isolation section appears when sandbox_type is OCI."""
        text = resolve_instructions(
            AgentRole.TEST_WRITER, _manifest(), sandbox_type=SandboxType.OCI
        )
        assert "## Isolation Boundary" in text

    def test_isolation_section_mentions_container(self) -> None:
        """Isolation section mentions running in a container."""
        text = resolve_instructions(
            AgentRole.TEST_WRITER, _manifest(), sandbox_type=SandboxType.OCI
        )
        assert "container" in text.lower()

    def test_isolation_section_mentions_worktree(self) -> None:
        """Isolation section describes worktree access."""
        text = resolve_instructions(
            AgentRole.TEST_WRITER, _manifest(), sandbox_type=SandboxType.OCI
        )
        assert "worktree" in text.lower()

    def test_isolation_section_mentions_signal_directory(self) -> None:
        """Isolation section describes signal directory access."""
        text = resolve_instructions(
            AgentRole.TEST_WRITER, _manifest(), sandbox_type=SandboxType.OCI
        )
        assert "signal directory" in text.lower()

    def test_isolation_section_mentions_git_read_only(self) -> None:
        """Isolation section describes git object store as read-only."""
        text = resolve_instructions(
            AgentRole.TEST_WRITER, _manifest(), sandbox_type=SandboxType.OCI
        )
        isolation_text = text.split("## Isolation Boundary")[1]
        assert "read-only" in isolation_text.lower()
        assert "git" in isolation_text.lower()

    def test_isolation_section_mentions_ops_concern(self) -> None:
        """Isolation section tells agents to use ops concern tool when blocked."""
        text = resolve_instructions(
            AgentRole.TEST_WRITER, _manifest(), sandbox_type=SandboxType.OCI
        )
        assert "agentrelay-ops-concern" in text.split("## Isolation Boundary")[1]

    def test_isolation_section_describes_beyond_boundary(self) -> None:
        """Isolation section describes what exists beyond the boundary."""
        text = resolve_instructions(
            AgentRole.TEST_WRITER, _manifest(), sandbox_type=SandboxType.OCI
        )
        isolation_text = text.split("## Isolation Boundary")[1]
        assert "orchestrator" in isolation_text.lower()

    def test_isolation_section_prohibits_self_remediation(self) -> None:
        """Isolation section warns against merging/cherry-picking."""
        text = resolve_instructions(
            AgentRole.TEST_WRITER, _manifest(), sandbox_type=SandboxType.OCI
        )
        isolation_text = text.split("## Isolation Boundary")[1].lower()
        assert "merging" in isolation_text or "cherry-picking" in isolation_text

    def test_isolation_section_after_what_to_do(self) -> None:
        """Isolation section appears after What to Do section."""
        text = resolve_instructions(
            AgentRole.TEST_WRITER, _manifest(), sandbox_type=SandboxType.OCI
        )
        what_to_do_pos = text.index("## What to Do")
        isolation_pos = text.index("## Isolation Boundary")
        assert what_to_do_pos < isolation_pos

    def test_isolation_section_before_submission(self) -> None:
        """Isolation section appears before Submitting Your Work section."""
        text = resolve_instructions(
            AgentRole.TEST_WRITER, _manifest(), sandbox_type=SandboxType.OCI
        )
        isolation_pos = text.index("## Isolation Boundary")
        submission_pos = text.index("## Submitting Your Work")
        assert isolation_pos < submission_pos

    def test_isolation_section_for_generic_role(self) -> None:
        """Isolation section works with GENERIC role too."""
        m = _manifest(description="Do something custom")
        text = resolve_instructions(AgentRole.GENERIC, m, sandbox_type=SandboxType.OCI)
        assert "## Isolation Boundary" in text

    def test_isolation_with_adr_ordering(self) -> None:
        """When both ADR and isolation are present, ADR comes first."""
        text = resolve_instructions(
            AgentRole.TEST_WRITER,
            _manifest(),
            adr_verbosity=AdrVerbosity.STANDARD,
            sandbox_type=SandboxType.OCI,
        )
        adr_pos = text.index("## Architecture Decision Record")
        isolation_pos = text.index("## Isolation Boundary")
        submission_pos = text.index("## Submitting Your Work")
        assert adr_pos < isolation_pos < submission_pos
