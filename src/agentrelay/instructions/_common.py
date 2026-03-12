"""Shared helpers for instruction builders.

Reusable text fragments for ADR steps, spec reading preambles,
agent signal commands, and git commit/push/PR steps.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from agentrelay.instructions._context import InstructionContext
from agentrelay.task import AgentVerbosity, Task


def adr_step(context: InstructionContext) -> str:
    """Return ADR-writing instructions if verbosity warrants it, else empty string."""
    verbosity = context.task.primary_agent.adr_verbosity
    if verbosity in (AgentVerbosity.NONE, AgentVerbosity.STANDARD):
        return ""
    today = date.today().isoformat()
    task = context.task
    adr_path = f"docs/decisions/{task.id}.md"
    extra_sections = ""
    if verbosity == AgentVerbosity.EDUCATIONAL:
        extra_sections = (
            "\n\n## Key Concepts\n"
            "Explain domain concepts that a reader unfamiliar with this area would need.\n\n"
            "## Alternatives Considered\n"
            "What else did you evaluate? Why did you choose this approach over the alternatives?"
        )
    role_value = task.role.value if task.role else "generic"
    graph_name = context.graph_name or "unknown"
    return (
        f"Write an ADR (Architecture Decision Record) to {adr_path}.\n"
        f"Create the parent directory if needed: mkdir -p docs/decisions\n"
        f"The file must contain this YAML front matter followed by the sections below:\n"
        f"---\n"
        f"task_id: {task.id}\n"
        f"graph: {graph_name}\n"
        f"role: {role_value}\n"
        f"date: {today}\n"
        f"verbosity: {verbosity.value}\n"
        f"---\n\n"
        f"## Context\n"
        f"What situation or codebase state did you find? What constraints existed?\n\n"
        f"## Decision\n"
        f"What did you choose to do and what were the key reasons?\n\n"
        f"## Consequences\n"
        f"What are the trade-offs? What should future contributors know?"
        f"{extra_sections}\n\n"
        f"Then stage the ADR file before committing:\n"
        f"    git add {adr_path}\n"
    )


def spec_reading_step(task: Task) -> str:
    """Return a spec-reading preamble if the task has src paths or a spec path."""
    if not task.paths.src and not task.paths.spec:
        return ""
    parts = ["Before starting, read the following to understand the API contract:\n"]
    if task.paths.src:
        paths_str = " ".join(task.paths.src)
        parts.append(
            f"  Source stubs (docstrings are the authoritative spec): {paths_str}\n"
        )
    if task.paths.spec:
        parts.append(f"  Supplementary spec file: {task.paths.spec}\n")
    parts.append("\n")
    return "".join(parts)


def mark_done_cmd(context: InstructionContext, pr_url_var: str = "$PR_URL") -> str:
    """Generate the ``mark_done()`` shell command for instruction text."""
    module = context.agent_api_module
    return (
        f'pixi run python -c "from {module} import WorktreeTaskRunner; '
        f"r = WorktreeTaskRunner.from_config(); "
        f"r.mark_done('{pr_url_var}')\""
    )


def mark_failed_cmd(context: InstructionContext, reason: str) -> str:
    """Generate the ``mark_failed()`` shell command for instruction text."""
    module = context.agent_api_module
    return (
        f'pixi run python -c "from {module} import WorktreeTaskRunner; '
        f"r = WorktreeTaskRunner.from_config(); "
        f"r.mark_failed('{reason}')\""
    )


def record_concern_cmd(context: InstructionContext) -> str:
    """Generate the ``record_concern()`` shell command for instruction text."""
    module = context.agent_api_module
    return (
        f'python -c "from {module} import WorktreeTaskRunner; \\\n'
        f"WorktreeTaskRunner.from_config().record_concern('your concern here')\""
    )


def record_gate_attempt_cmd(context: InstructionContext) -> str:
    """Generate the ``record_gate_attempt()`` shell command for instruction text."""
    module = context.agent_api_module
    return (
        f'python -c "\\\n'
        f"from {module}.worktree_task_runner import WorktreeTaskRunner;\\\n"
        f'WorktreeTaskRunner.from_config().record_gate_attempt(N, PASSED)\\\n"'
    )


def commit_push_step(
    task: Task,
    step_num: int,
    specific_paths: Optional[list[str]] = None,
) -> tuple[str, int]:
    """Return git add/commit/push instruction text and the next step number.

    Args:
        task: Task spec (used for commit message).
        step_num: Current step number in the instruction sequence.
        specific_paths: If provided, ``git add`` these paths explicitly.
            Otherwise uses ``git add -A``.

    Returns:
        Tuple of (instruction text, next step number).
    """
    short_desc = (task.description or task.id)[:60]
    if specific_paths:
        git_add_paths = " ".join(specific_paths)
    else:
        git_add_paths = "-A"
    text = (
        f"{step_num}. Stage, commit, and push:\n"
        f"       git add {git_add_paths}\n"
        f'       git commit -m "{task.id}: {short_desc}"\n'
        f"       git push -u origin HEAD"
    )
    return text, step_num + 1


def pr_create_step(
    context: InstructionContext,
    step_num: int,
    summary_hint: str,
) -> tuple[str, int]:
    """Return PR creation + mark_done instruction text and the next step number.

    Args:
        context: Instruction context.
        step_num: Current step number.
        summary_hint: Hint text for the PR summary section.

    Returns:
        Tuple of (instruction text, next step number).
    """
    done_cmd = mark_done_cmd(context)
    text = (
        f"{step_num}. Create a PR with a meaningful body, capture the URL, "
        f"and signal completion:\n"
        f'       PR_URL=$(gh pr create --title "{context.task.id}" '
        f"--body \"$(cat <<'PRBODY'\n"
        f"## Summary\n"
        f"{summary_hint}\n\n"
        f"## Files changed\n"
        f"<bullet list of the key files you created or modified>\n"
        f'PRBODY\n)" --base {context.graph_branch})\n'
        f"       {done_cmd}"
    )
    return text, step_num + 1
