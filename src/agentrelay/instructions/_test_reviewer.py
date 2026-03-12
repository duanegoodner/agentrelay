"""Instruction builder for TEST_REVIEWER tasks."""

from __future__ import annotations

from agentrelay.instructions._common import (
    adr_step,
    commit_push_step,
    mark_failed_cmd,
    pr_create_step,
    spec_reading_step,
)
from agentrelay.instructions._context import InstructionContext


def build_test_reviewer(context: InstructionContext) -> str:
    """Build instructions for a TEST_REVIEWER task."""
    task = context.task
    review_file = f"{task.id}.md"
    spec_step = spec_reading_step(task)
    failed_cmd = mark_failed_cmd(context, "Tests are fundamentally broken: <reason>")

    step_num = 4
    adr_text = adr_step(context)
    adr_section = ""
    if adr_text:
        adr_section = f"{step_num}. {adr_text}\n\n"
        step_num += 1

    commit_text, step_num = commit_push_step(task, step_num, [review_file])
    pr_text, _ = pr_create_step(
        context,
        step_num,
        "<verdict and 1-2 sentence summary of the review>",
    )

    return (
        f"You are a worktree agent for the agentrelay project.\n\n"
        f"Your role: TEST REVIEWER\n\n"
        f"Your task: {task.description}\n\n"
        f"The test file(s) and stub module from the test-writer task are already "
        f"merged into the graph integration branch and available in your "
        f"worktree.\n\n"
        f"{spec_step}"
        f"Complete these steps in order:\n\n"
        f"1. Read the test file(s) and stub module.\n\n"
        f"2. Write a review file named {review_file} with the following "
        f"sections:\n"
        f"   ## Verdict\n"
        f"   APPROVED or CONCERNS\n\n"
        f"   ## Coverage assessment\n"
        f"   Which aspects of the feature are tested; what is missing.\n\n"
        f"   ## Comments\n"
        f"   Specific notes on individual tests or the stub API.\n\n"
        f"3. If the tests are fundamentally broken (import errors, wrong "
        f"assertions, untestable structure), signal failure and stop:\n"
        f"       {failed_cmd}\n\n"
        f"{adr_section}"
        f"{commit_text}\n\n"
        f"{pr_text}\n\n"
        f"The pixi.toml in the current directory provides the agentrelay "
        f"package.\n\n"
        f"Then stop — do not implement the feature.\n"
    )
