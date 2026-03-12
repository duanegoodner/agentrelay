"""Instruction builder for IMPLEMENTER tasks."""

from __future__ import annotations

from agentrelay.instructions._common import (
    adr_step,
    commit_push_step,
    pr_create_step,
    record_concern_cmd,
    spec_reading_step,
)
from agentrelay.instructions._context import InstructionContext


def build_implementer(context: InstructionContext) -> str:
    """Build instructions for an IMPLEMENTER task."""
    task = context.task
    review_file = task.id.removesuffix("_impl") + "_review.md"
    spec_step = spec_reading_step(task)
    concern_cmd = record_concern_cmd(context)

    if task.paths.src:
        src_paths_str = " ".join(task.paths.src)
        impl_step = (
            f"2. Implement the feature by replacing the NotImplementedError "
            f"stubs in {src_paths_str} with working code.\n"
            f"   When implementing, you MUST preserve all existing docstrings "
            f"in {src_paths_str} exactly. You may add Examples or Notes to a "
            f"docstring if they were absent, but do NOT alter the Args, Returns, "
            f"or Raises sections, do NOT change signatures, and do NOT remove or "
            f"weaken any documented behaviour or constraints. The docstrings are "
            f"the specification contract — they are reviewed by a merge agent "
            f"after you submit your PR.\n"
            f"   Add supporting modules as needed.\n"
        )
    else:
        impl_step = (
            "2. Implement the feature by replacing the NotImplementedError "
            "stubs with working code. Add supporting modules as needed.\n"
        )

    if task.paths.test:
        test_paths_str = " ".join(task.paths.test)
        run_tests_step = (
            f"3. Run the tests and fix any failures. Repeat until all tests "
            f"pass:\n"
            f"       pixi run pytest {test_paths_str}\n"
        )
    else:
        run_tests_step = (
            "3. Run the tests and fix any failures. Repeat until all tests "
            "pass:\n"
            "       pixi run pytest\n"
        )

    step_num = 5
    adr_text = adr_step(context)
    adr_section = ""
    if adr_text:
        adr_section = f"{step_num}. {adr_text}\n\n"
        step_num += 1

    commit_text, step_num = commit_push_step(task, step_num)
    pr_text, _ = pr_create_step(
        context,
        step_num,
        "<1-3 sentences describing the implementation>",
    )

    return (
        f"You are a worktree agent for the agentrelay project.\n\n"
        f"Your role: IMPLEMENTER\n\n"
        f"Your task: {task.description}\n\n"
        f"The test file(s), stub module, and review file are already merged "
        f"into the graph integration branch and available in your worktree.\n\n"
        f"{spec_step}"
        f"Complete these steps in order:\n\n"
        f"1. Read the test file(s) and {review_file} to understand what is "
        f"expected and any reviewer feedback.\n\n"
        f"{impl_step}\n"
        f"{run_tests_step}\n"
        f"4. If during implementation you encountered concerns about the spec, "
        f"tests, or architecture — whether or not you succeeded — document "
        f"each one:\n"
        f"       {concern_cmd}\n"
        f"   Do this for every distinct concern. If you have no concerns, skip "
        f"this step.\n\n"
        f"{adr_section}"
        f"{commit_text}\n\n"
        f"{pr_text}\n\n"
        f"The pixi.toml in the current directory provides the agentrelay "
        f"package.\n\n"
        f"Then stop.\n"
    )
