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
        m = _manifest(
            role=AgentRole.SPEC_WRITER,
            spec_path=Path("specs/greet.md"),
        )
        text = resolve_instructions(AgentRole.SPEC_WRITER, m)
        assert "SPEC_WRITER" in text
        assert "specs/greet.md" in text

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
        """GENERIC role returns description-based instructions."""
        m = _manifest(description="Do something custom")
        text = resolve_instructions(AgentRole.GENERIC, m)
        assert "Do something custom" in text
        assert "my_task" in text

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

    def test_empty_paths_show_placeholder(self) -> None:
        """Empty paths are shown as '(none specified)'."""
        m = _manifest(src_paths=(), test_paths=())
        text = resolve_instructions(AgentRole.TEST_WRITER, m)
        assert "(none specified)" in text
