"""Instruction builder for SPEC_WRITER tasks."""

from __future__ import annotations

from agentrelay.instructions._common import (
    adr_step,
    commit_push_step,
    pr_create_step,
)
from agentrelay.instructions._context import InstructionContext


def build_spec_writer(context: InstructionContext) -> str:
    """Build instructions for a SPEC_WRITER task."""
    task = context.task
    src_paths_str = " ".join(task.paths.src) if task.paths.src else "(see description)"

    steps: list[str] = []
    steps.append(
        f"1. For each file in {src_paths_str}:\n"
        f"   - Create the file with a module-level docstring describing the "
        f"module's purpose\n"
        f"   - Add all function/class signatures with full Python type "
        f"annotations\n"
        f"   - Write comprehensive Google-style docstrings on each function: "
        f"Args, Returns, Raises, Examples (with doctestable >>> lines where "
        f"appropriate)\n"
        f"   - Set all bodies to: raise NotImplementedError\n"
        f"   The docstrings ARE the spec — write them to be authoritative and "
        f"complete.\n"
        f"   Create any parent directories as needed."
    )

    step_num = 2
    if task.paths.spec:
        steps.append(
            f"{step_num}. Write a brief spec file at {task.paths.spec} that "
            f"serves as a high-level index/narrative pointing to the source "
            f"files for detailed specs. This is supplementary only. Do NOT "
            f"duplicate the docstring content. Create any parent directories "
            f"as needed."
        )
        step_num += 1

    steps.append(
        f"{step_num}. Verify the stub module(s) are importable "
        f'(e.g. `pixi run python -c "import <module>"`). Fix any import errors.'
    )
    step_num += 1

    adr_text = adr_step(context)
    if adr_text:
        steps.append(f"{step_num}. {adr_text}")
        step_num += 1

    all_paths = list(task.paths.src)
    if task.paths.spec:
        all_paths.append(task.paths.spec)

    commit_text, step_num = commit_push_step(
        task, step_num, all_paths if all_paths else None
    )
    steps.append(commit_text)

    pr_text, _ = pr_create_step(
        context,
        step_num,
        "<1-3 sentences describing the stubs and spec written>",
    )
    steps.append(pr_text)

    steps_text = "\n\n".join(steps)
    return (
        f"You are a worktree agent for the agentrelay project.\n\n"
        f"Your role: SPEC WRITER\n\n"
        f"Your task: {task.description}\n\n"
        f"Complete these steps in order:\n\n"
        f"{steps_text}\n\n"
        f"The pixi.toml in the current directory provides the agentrelay "
        f"package.\n\n"
        f"Do NOT implement any function or method bodies.\n\n"
        f"Then stop.\n"
    )
