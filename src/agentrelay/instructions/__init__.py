"""Per-role instruction builders for agentrelay task agents.

This package generates the ``instructions.md`` content that gets written to
each task's signal directory before agent launch. Instruction builders are
pure functions: :class:`InstructionContext` in, ``str`` out.

Public API:
    :func:`build_instructions` — dispatch to role-specific builder.
    :func:`build_context_content` — produce ``context.md`` text from
        dependency descriptions.
    :class:`InstructionContext` — frozen input for all builders.
    :func:`instruction_context_from_runtime` — convenience factory.
"""

from agentrelay.instructions._context import (
    InstructionContext,
    build_context_content,
    instruction_context_from_runtime,
)
from agentrelay.instructions._generic import build_generic as _build_generic
from agentrelay.instructions._implementer import build_implementer as _build_implementer
from agentrelay.instructions._spec_writer import build_spec_writer as _build_spec_writer
from agentrelay.instructions._test_reviewer import (
    build_test_reviewer as _build_test_reviewer,
)
from agentrelay.instructions._test_writer import build_test_writer as _build_test_writer
from agentrelay.task import AgentRole

_BUILDERS = {
    AgentRole.SPEC_WRITER: _build_spec_writer,
    AgentRole.TEST_WRITER: _build_test_writer,
    AgentRole.TEST_REVIEWER: _build_test_reviewer,
    AgentRole.IMPLEMENTER: _build_implementer,
    AgentRole.GENERIC: _build_generic,
}


def build_instructions(context: InstructionContext) -> str:
    """Build role-specific instructions for a task agent.

    Dispatches to the appropriate internal builder based on
    ``context.task.role``.

    Args:
        context: Frozen instruction context with all builder inputs.

    Returns:
        Complete ``instructions.md`` content as a string.
    """
    builder = _BUILDERS.get(context.task.role, _build_generic)
    return builder(context)


__all__ = [
    "InstructionContext",
    "build_context_content",
    "build_instructions",
    "instruction_context_from_runtime",
]
