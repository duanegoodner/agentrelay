"""Generic instruction builder for tasks with no specialized role."""

from __future__ import annotations

from agentrelay.instructions._common import (
    adr_step,
    commit_push_step,
    mark_failed_cmd,
    pr_create_step,
    record_gate_attempt_cmd,
    spec_reading_step,
)
from agentrelay.instructions._context import InstructionContext


def build_generic(context: InstructionContext) -> str:
    """Build instructions for a GENERIC task."""
    task = context.task

    # Context note for tasks with dependencies.
    context_note = ""
    if context.dependency_descriptions:
        context_note = (
            "Before starting, if the file at $AGENTRELAY_SIGNAL_DIR/context.md "
            "exists, read it — it describes what prerequisite tasks produced.\n\n"
        )

    # Completion gate section.
    gate_step = ""
    if task.completion_gate:
        gate_cmd = task.completion_gate
        conditional_review = ""
        if task.review and task.review.review_on_attempt >= 2:
            attempt = task.review.review_on_attempt
            review_model = task.review.agent.model or "default"
            conditional_review = (
                f"  (Attempt {attempt}+) Before running the gate on attempt "
                f"{attempt} or later, spawn a self-review subagent:\n"
                f'    - Use the Task tool with model="{review_model}"\n'
                f"    - Pass it your task description, work done, and any "
                f"previous gate output\n"
                f"    - Ask it to identify what's failing and suggest fixes\n"
                f"    - Incorporate its feedback before running the gate\n"
            )
        record_cmd = record_gate_attempt_cmd(context)
        effective = context.effective_gate_attempts
        failed_cmd = mark_failed_cmd(context, "summary of what was tried")
        gate_step = (
            f"Before calling mark_done(), you must pass the completion gate.\n"
            f"You have up to {effective} attempts. Each gate run counts as one "
            f"attempt.\n\n"
            f"Gate command:\n"
            f"    {gate_cmd}\n\n"
            f"The gate command's exit code is the only accepted truth. If it exits\n"
            f"non-zero, the attempt has failed — regardless of what you observed "
            f"during\nyour work session. Do not let prior test runs or your own "
            f"assessment\noverride a non-zero gate exit.\n\n"
            f"For each attempt:\n"
            f"{conditional_review}"
            f"1. Run the gate command, saving its output and checking the exit "
            f"code:\n"
            f'       {gate_cmd} > "$AGENTRELAY_SIGNAL_DIR/gate_last_output.txt"'
            f" 2>&1\n"
            f"       gate_exit=$?\n"
            f'       cat "$AGENTRELAY_SIGNAL_DIR/gate_last_output.txt"\n'
            f"2. Record the attempt:\n"
            f"       {record_cmd}\n"
            f"   Replace N with the attempt number (1, 2, ...) and PASSED with "
            f"True or False.\n"
            f"3. If gate_exit is 0 (passed), proceed to mark_done().\n"
            f"4. If gate_exit is non-zero (failed), diagnose the output, fix the "
            f"issue, and retry.\n\n"
            f"After {effective} failed attempts, call mark_failed() with a "
            f"summary of what\nyou tried. The full output of the last gate run "
            f"is already saved to\n"
            f"$AGENTRELAY_SIGNAL_DIR/gate_last_output.txt.\n"
            f"Do NOT call mark_done() until gate_exit is 0.\n\n"
            f"If all attempts fail:\n"
            f"       {failed_cmd}\n\n"
        )

    # Self-review before gate (review_on_attempt <= 1).
    review_step = ""
    if task.review and task.review.review_on_attempt <= 1:
        review_model = task.review.agent.model or "default"
        review_step = (
            f"Before running the completion gate, spawn a self-review subagent:\n"
            f'  - Use the Task tool with model="{review_model}"\n'
            f"  - Pass it your full task description and the work you've done\n"
            f"  - Ask it to verify correctness, edge cases, and alignment with "
            f"the description\n"
            f"  - Incorporate any feedback before running the completion gate\n\n"
        )

    spec_step = spec_reading_step(task)
    adr_text = adr_step(context)
    adr_section = ""

    # Build numbered steps.
    step_num = 1
    work_step = f"{step_num}. Do the work described in your task.\n"
    step_num += 1

    if adr_text:
        adr_section = f"\n{step_num}. {adr_text}\n"
        step_num += 1

    commit_text, step_num = commit_push_step(task, step_num)
    pr_text, _ = pr_create_step(
        context, step_num, "<1-3 sentences describing what you did and why>"
    )

    return (
        f"You are a worktree agent for the agentrelay project.\n\n"
        f"Your task: {task.description}\n\n"
        f"{context_note}"
        f"{review_step}"
        f"Complete these steps in order:\n\n"
        f"{spec_step}"
        f"{work_step}\n"
        f"{gate_step}"
        f"{adr_section}"
        f"{commit_text}\n\n"
        f"{pr_text}\n\n"
        f"The pixi.toml in the current directory provides the agentrelay package.\n\n"
        f"Then stop — do not do anything else.\n"
    )
