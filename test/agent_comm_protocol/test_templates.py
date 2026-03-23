"""Tests for agentrelay.agent_comm_protocol.templates — role template resolution."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agentrelay.agent_comm_protocol.manifest import TaskManifest
from agentrelay.agent_comm_protocol.templates import resolve_instructions
from agentrelay.task import AgentRole


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
