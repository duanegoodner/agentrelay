"""Tests for :mod:`agentrelay.tools`."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agentrelay.tools import (
    TOOL_REGISTRY,
    ToolSpec,
    ToolValidationError,
    tool_guidance,
    validate_tools,
)

# --- ToolSpec ---


class TestToolSpec:
    def test_frozen(self) -> None:
        spec = ToolSpec(binary="pixi", agent_guidance="Use pixi run")
        with pytest.raises(AttributeError):
            spec.binary = "other"  # type: ignore[misc]


# --- TOOL_REGISTRY ---


class TestToolRegistry:
    def test_pixi_registered(self) -> None:
        assert "pixi" in TOOL_REGISTRY

    def test_pixi_binary(self) -> None:
        assert TOOL_REGISTRY["pixi"].binary == "pixi"

    def test_pixi_has_guidance(self) -> None:
        assert len(TOOL_REGISTRY["pixi"].agent_guidance) > 0


# --- validate_tools ---


class TestValidateTools:
    def test_empty_tools_succeeds(self) -> None:
        validate_tools(())

    def test_unknown_tool_raises(self) -> None:
        with pytest.raises(ToolValidationError, match="Unknown tool 'nosuch'"):
            validate_tools(("nosuch",))

    def test_known_tool_present_succeeds(self) -> None:
        with patch("agentrelay.tools.shutil.which", return_value="/usr/bin/pixi"):
            validate_tools(("pixi",))

    def test_known_tool_missing_raises(self) -> None:
        with patch("agentrelay.tools.shutil.which", return_value=None):
            with pytest.raises(ToolValidationError, match="not found on PATH"):
                validate_tools(("pixi",))

    def test_multiple_tools_all_checked(self) -> None:
        """If one tool is missing, validation fails even if others are present."""
        # Register a temporary second tool for testing
        TOOL_REGISTRY["testonly"] = ToolSpec(
            binary="testonly-bin", agent_guidance="test"
        )
        try:

            def fake_which(name: str) -> str | None:
                return "/usr/bin/pixi" if name == "pixi" else None

            with patch("agentrelay.tools.shutil.which", side_effect=fake_which):
                with pytest.raises(ToolValidationError, match="testonly-bin"):
                    validate_tools(("pixi", "testonly"))
        finally:
            del TOOL_REGISTRY["testonly"]


# --- tool_guidance ---


class TestToolGuidance:
    def test_empty_tools_returns_empty(self) -> None:
        assert tool_guidance(()) == ""

    def test_pixi_guidance(self) -> None:
        result = tool_guidance(("pixi",))
        assert "## Tools" in result
        assert "pixi" in result
        assert "pixi run" in result

    def test_unknown_tool_skipped(self) -> None:
        result = tool_guidance(("nonexistent",))
        assert "## Tools" in result
        assert "nonexistent" not in result.split("## Tools")[1]
