"""Instruction builder for TEST_WRITER tasks."""

from __future__ import annotations

from agentrelay.instructions._common import (
    adr_step,
    commit_push_step,
    pr_create_step,
    spec_reading_step,
)
from agentrelay.instructions._context import InstructionContext


def build_test_writer(context: InstructionContext) -> str:
    """Build instructions for a TEST_WRITER task."""
    task = context.task
    spec_step = spec_reading_step(task)

    if task.paths.test:
        test_paths_str = " ".join(task.paths.test)
        write_step = f"1. Write pytest test files at: {test_paths_str}\n"
    else:
        write_step = (
            "1. Write a pytest test file covering the described feature. "
            "Place it at an appropriate path in the target module's test "
            "directory.\n"
        )

    stub_note = ""
    if task.paths.src:
        src_paths_str = " ".join(task.paths.src)
        stub_note = (
            f"   The stub module(s) at {src_paths_str} already exist — "
            f"do NOT create or overwrite them. Write test file(s) that import "
            f"from those stubs.\n"
        )

    step_num = 2
    verify_step = (
        f"{step_num}. Verify tests collect without import errors:\n"
        f"       pixi run pytest --collect-only"
    )
    step_num += 1

    adr_text = adr_step(context)
    adr_section = ""
    if adr_text:
        adr_section = f"{step_num}. {adr_text}"
        step_num += 1

    commit_text, step_num = commit_push_step(task, step_num)
    pr_text, _ = pr_create_step(
        context,
        step_num,
        "<1-3 sentences describing the tests written>",
    )

    parts = [
        f"You are a worktree agent for the agentrelay project.\n\n"
        f"Your role: TEST WRITER\n\n"
        f"Your task: {task.description}\n\n"
        f"{spec_step}"
        f"Complete these steps in order:\n\n"
        f"{write_step}"
        f"{stub_note}\n"
        f"{verify_step}\n",
    ]
    if adr_section:
        parts.append(f"\n{adr_section}\n")
    parts.append(
        f"\n{commit_text}\n\n"
        f"{pr_text}\n\n"
        f"The pixi.toml in the current directory provides the agentrelay "
        f"package.\n\n"
        f"Then stop — do not implement the feature.\n"
    )
    return "".join(parts)
