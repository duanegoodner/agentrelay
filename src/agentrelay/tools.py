"""Declared tool validation and agent guidance.

Graphs declare required tools (e.g., ``pixi``) so the orchestrator can
validate availability before launch and inject usage guidance into agent
instructions.

Classes:
    ToolSpec: Validation command and agent guidance for a single tool.

Functions:
    validate_tools: Check that all declared tools are available.
    tool_guidance: Return agent guidance text for a list of tools.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSpec:
    """Validation and guidance metadata for a declared tool.

    Attributes:
        binary: Name of the binary to check (via ``shutil.which``).
        agent_guidance: Markdown text telling agents how to use the tool.
    """

    binary: str
    agent_guidance: str


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "pixi": ToolSpec(
        binary="pixi",
        agent_guidance=(
            "Use `pixi run` to execute all Python commands, tests, and scripts. "
            "Do not use bare `python`, `pytest`, or `pip` — always prefix with `pixi run`."
        ),
    ),
}
"""Registry of known tools. Keyed by the name used in graph YAML."""


class ToolValidationError(RuntimeError):
    """Raised when a declared tool fails validation."""


def validate_tools(tools: tuple[str, ...]) -> None:
    """Validate that all declared tools are available.

    For each tool name, looks up the registry entry and checks that the
    binary is on PATH via :func:`shutil.which`.

    Args:
        tools: Tool names declared in the graph YAML.

    Raises:
        ToolValidationError: If a tool is unknown or its binary is not found.
    """
    for name in tools:
        spec = TOOL_REGISTRY.get(name)
        if spec is None:
            known = ", ".join(sorted(TOOL_REGISTRY))
            raise ToolValidationError(
                f"Unknown tool '{name}' declared in graph YAML. "
                f"Known tools: {known}"
            )
        if shutil.which(spec.binary) is None:
            raise ToolValidationError(
                f"Tool '{name}' is declared but '{spec.binary}' was not found on PATH.\n"
                f"Install it or remove '{name}' from the graph's tools list."
            )


def tool_guidance(tools: tuple[str, ...]) -> str:
    """Build agent guidance text for the declared tools.

    Args:
        tools: Tool names declared in the graph YAML.

    Returns:
        Markdown text with guidance for each tool, or empty string if no
        tools are declared.
    """
    if not tools:
        return ""
    lines: list[str] = []
    for name in tools:
        spec = TOOL_REGISTRY.get(name)
        if spec is not None:
            lines.append(f"- **{name}**: {spec.agent_guidance}")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "ToolSpec",
    "TOOL_REGISTRY",
    "ToolValidationError",
    "validate_tools",
    "tool_guidance",
]
