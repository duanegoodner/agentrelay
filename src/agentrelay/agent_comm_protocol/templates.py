"""Role template resolution — Layer 2 of the agent communication protocol.

Resolves role-appropriate markdown instruction templates, substituting
manifest data using ``string.Template`` (``$var`` syntax).  The assembled
document is structured as a work order: role, tools, what to do, how to
submit, and (for non-generic roles) task details from the graph author.

Functions:
    resolve_instructions: Load and parameterize a role template.
"""

from __future__ import annotations

from pathlib import Path
from string import Template
from typing import Optional

from agentrelay.agent_comm_protocol.manifest import TaskManifest
from agentrelay.sandbox import SandboxType
from agentrelay.task import AdrVerbosity, AgentRole
from agentrelay.tools import tool_guidance

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

_NONE_PLACEHOLDER = "(none specified)"

_ROLE_SENTENCES: dict[AgentRole, str] = {
    AgentRole.SPEC_WRITER: (
        "You are a SPEC_WRITER tasked with writing specifications "
        "for part of a software project."
    ),
    AgentRole.TEST_WRITER: (
        "You are a TEST_WRITER tasked with writing tests "
        "for part of a software project."
    ),
    AgentRole.TEST_REVIEWER: (
        "You are a TEST_REVIEWER tasked with reviewing tests "
        "written by another agent."
    ),
    AgentRole.IMPLEMENTER: (
        "You are an IMPLEMENTER tasked with writing working code "
        "that passes existing tests."
    ),
    AgentRole.GENERIC: "You are tasked with a custom assignment.",
}


def _format_paths(paths: tuple[Path, ...]) -> str:
    """Join paths with spaces, or return a placeholder if empty."""
    return " ".join(str(p) for p in paths) if paths else _NONE_PLACEHOLDER


def resolve_instructions(
    role: AgentRole,
    manifest: TaskManifest,
    adapter_name: Optional[str] = None,
    adr_verbosity: AdrVerbosity = AdrVerbosity.NONE,
    sandbox_type: Optional[SandboxType] = None,
) -> str:
    """Resolve work instructions by loading and parameterizing a role template.

    The assembled document is structured as a work order:

    1. **Role** — who the agent is and what it's doing.
    2. **Tools** — environment tools available (if any).
    3. **What to Do** — role-specific steps from the template, or the
       task description for GENERIC roles.
    4. **Architecture Decision Record** — ADR writing instructions (if
       ``adr_verbosity`` is not ``NONE``).
    5. **Isolation Boundary** — what the agent can/cannot access and
       what exists beyond its boundary (if ``sandbox_type`` is ``OCI``).
    6. **Submitting Your Work** — how to commit, create a PR, and signal
       the orchestrator.
    7. **Task Details** — the task author's description (non-generic only,
       when present).

    Template variables (``$var`` syntax via :class:`string.Template`):

    - ``$description`` — task description
    - ``$src_paths`` — space-joined source paths, or ``"(none specified)"``
    - ``$test_paths`` — space-joined test paths, or ``"(none specified)"``
    - ``$spec_path`` — spec path, or ``"(none specified)"``
    - ``$task_id`` — task identifier

    Args:
        role: Agent role determining which template to load.
        manifest: Task manifest providing substitution values.
        adapter_name: Optional adapter name for adapter-specific override.
        adr_verbosity: ADR detail level. ``NONE`` (default) omits the section.
        sandbox_type: Sandbox type. When ``OCI``, an isolation boundary
            section is included describing what the agent can and cannot
            access.

    Returns:
        Resolved markdown instruction text.

    Raises:
        FileNotFoundError: If no template found for a non-GENERIC role.
        ValueError: If GENERIC role has no description.
    """
    parts = [
        f"# Instructions for Task {manifest.task_id}",
        (
            f"## Role\n\n{_ROLE_SENTENCES[role]} "
            "Follow the instructions below to complete the task."
        ),
    ]

    # Tools (flat H2, only if declared).
    tools_text = tool_guidance(manifest.tools)
    if tools_text:
        parts.append("## Tools\n\n" + tools_text.strip())

    # What to Do.
    if role == AgentRole.GENERIC:
        if manifest.description is None:
            raise ValueError(
                f"GENERIC role requires a task description, but task "
                f"'{manifest.task_id}' has description=None."
            )
        parts.append(
            "## What to Do\n\n" + manifest.description + "\n\n" + _concerns_note()
        )
    else:
        template_text = _load_template(role.value, adapter_name)
        substitutions = {
            "description": manifest.description or "",
            "src_paths": _format_paths(manifest.src_paths),
            "test_paths": _format_paths(manifest.test_paths),
            "spec_path": (
                str(manifest.spec_path)
                if manifest.spec_path is not None
                else _NONE_PLACEHOLDER
            ),
            "task_id": manifest.task_id,
            "concerns_note": _concerns_note(),
        }
        resolved = Template(template_text).substitute(substitutions)
        parts.append("## What to Do\n\n" + resolved.strip())

    # Architecture Decision Record (conditional, cross-cutting).
    adr_text = _adr_section(adr_verbosity, manifest.task_id)
    if adr_text:
        parts.append(adr_text)

    # Isolation Boundary (conditional, cross-cutting).
    isolation_text = _isolation_section(sandbox_type)
    if isolation_text:
        parts.append(isolation_text)

    parts.append(_submission_section(manifest))

    # Task Details (non-generic, when description exists).
    if role != AgentRole.GENERIC and manifest.description:
        parts.append("## Task Details\n\n" + manifest.description)

    return "\n\n".join(parts) + "\n"


def _concerns_note() -> str:
    """Build the concerns guidance note appended to the What to Do section."""
    return (
        "Throughout your work on this task, watch for and record any concerns you encounter:\n"
        "- **Design concerns** (spec contradictions, ambiguous requirements, "
        "conflicting behaviors): report with "
        '`agentrelay-concern --message "describe the concern"`\n'
        "- **Ops concerns** (build errors, missing deps, tooling friction): "
        'report with `agentrelay-ops-concern --message "describe the concern"`'
    )


def _adr_section(verbosity: AdrVerbosity, task_id: str) -> str:
    """Build the Architecture Decision Record section for the given verbosity.

    Returns a complete ``## Architecture Decision Record`` section when
    *verbosity* is not ``NONE``, or an empty string otherwise.

    Args:
        verbosity: Requested ADR detail level.
        task_id: Task identifier used to derive the output file path.

    Returns:
        Markdown section text, or ``""`` when no ADR is requested.
    """
    if verbosity == AdrVerbosity.NONE:
        return ""

    output_path = f"docs/adr/{task_id}.md"

    lines = [
        "## Architecture Decision Record",
        "",
        "As part of this task, write an Architecture Decision Record (ADR) "
        "documenting the key technical decisions you make.",
        "",
        f"**Output file:** `{output_path}`",
        "",
        "Create the file and commit it alongside your other changes.",
    ]

    if verbosity == AdrVerbosity.STANDARD:
        lines += [
            "",
            "Include the following sections:",
            "",
            "- **Title** — Short name for the decision",
            "- **Status** — Proposed, Accepted, Deprecated, or Superseded",
            "- **Context** — What situation or problem prompted this decision",
            "- **Decision** — What was decided and why",
            "- **Consequences** — What follows from this decision "
            "(positive and negative)",
        ]
    elif verbosity == AdrVerbosity.DETAILED:
        lines += [
            "",
            "Include the following sections:",
            "",
            "- **Title** — Short name for the decision",
            "- **Status** — Proposed, Accepted, Deprecated, or Superseded",
            "- **Context** — What situation or problem prompted this decision",
            "- **Decision** — What was decided and why",
            "- **Alternatives Considered** — Other options evaluated and why "
            "they were rejected",
            "- **Trade-offs** — Key trade-offs involved in the chosen approach",
            "- **Consequences** — What follows from this decision "
            "(positive and negative)",
            "- **Implementation Notes** — Relevant technical details " "or constraints",
        ]
    elif verbosity == AdrVerbosity.EDUCATIONAL:
        lines += [
            "",
            "Include the following sections. For each section, add a brief "
            "annotation explaining what the section captures and why it "
            "matters.",
            "",
            "- **Title** — Short name for the decision",
            "- **Status** — Proposed, Accepted, Deprecated, or Superseded",
            "- **Context** — What situation or problem prompted this decision. "
            "Explain why capturing context is important for future readers.",
            "- **Decision** — What was decided and why. "
            "Explain the value of recording rationale alongside the decision "
            "itself.",
            "- **Alternatives Considered** — Other options evaluated and why "
            "they were rejected. Explain why documenting rejected alternatives "
            "helps future maintainers.",
            "- **Trade-offs** — Key trade-offs involved in the chosen approach. "
            "Explain how explicit trade-off documentation aids future "
            "decision-making.",
            "- **Consequences** — What follows from this decision "
            "(positive and negative). Explain why anticipated consequences "
            "should be documented upfront.",
            "- **Implementation Notes** — Relevant technical details "
            "or constraints. Explain how this section bridges the gap between "
            "decision and execution.",
        ]

    return "\n".join(lines)


def _isolation_section(sandbox_type: Optional[SandboxType]) -> str:
    """Build the Isolation Boundary section for containerized agents.

    Returns a complete ``## Isolation Boundary`` section when
    *sandbox_type* is :attr:`SandboxType.OCI`, or an empty string
    otherwise.

    Args:
        sandbox_type: Sandbox type, or ``None`` for default (no section).

    Returns:
        Markdown section text, or ``""`` when no isolation applies.
    """
    if sandbox_type is None or sandbox_type != SandboxType.OCI:
        return ""

    lines = [
        "## Isolation Boundary",
        "",
        "You are running inside an isolated container. This section describes "
        "what you can and cannot access, and what exists beyond your boundary.",
        "",
        "### What You Can Access",
        "",
        "- **Your worktree** (read-write): the checked-out source tree for "
        "your task branch. All file reads and writes should happen here.",
        "- **Your signal directory** (read-write): where you write completion "
        "and failure signals via the `agentrelay-complete` / "
        "`agentrelay-failed` commands.",
        "- **The git object store** (read-only): you can read all branches "
        "and commits in the repository via `git log`, `git show`, `git diff`, "
        "etc. This is useful for understanding upstream changes and "
        "dependencies. You cannot modify the `.git` directory directly.",
        "",
        "### What You Cannot Access",
        "",
        "- The host filesystem outside your mounted paths.",
        "- The Docker socket or any container management tools.",
        "- Other tasks' worktrees or signal directories.",
        "- Host user credentials, SSH keys, or home directory.",
        "- Network resources outside the graph-scoped Docker network.",
        "",
        "### What Exists Beyond Your Boundary",
        "",
        "Other agents are running concurrently in their own containers, each "
        "with their own worktree and task branch. An orchestrator on the host "
        "coordinates task scheduling, monitors signal files, and manages PR "
        "merges. If you encounter a situation where access to an external "
        "resource would help you complete your task, record that observation "
        "as an ops concern — this information helps the orchestrator and "
        "human operators improve the system.",
        "",
        "### When You Are Blocked",
        "",
        "If you cannot complete your task due to an access limitation or "
        "environmental issue:",
        "",
        "1. Record an ops concern: "
        '`agentrelay-ops-concern --message "describe what you need and why"`',
        "2. If the issue is unrecoverable, signal failure with an actionable "
        "reason: "
        '`agentrelay-failed --reason "what went wrong and what would fix it"`',
        "",
        "Do **not** attempt to work around access limitations by merging PRs, "
        "cherry-picking from other branches, or copying files from outside "
        "your worktree. These actions violate the coordination model and may "
        "cause failures in other tasks.",
    ]
    return "\n".join(lines)


def _submission_section(manifest: TaskManifest) -> str:
    """Build the Submitting Your Work section with signaling steps."""
    return f"""## Submitting Your Work

After completing the work above:

1. **Commit and push** all changes to branch `{manifest.branch_name}`.
2. **Complete the task** (creates PR and signals the orchestrator):
   ```bash
   agentrelay-complete --title "short summary of changes" --body "## Summary

   - what was done"
   ```
   Provide a meaningful PR title (concise) and body (markdown with a ## Summary section).
   Any recorded concerns are automatically appended to the PR body.

If you made no code changes (e.g., review-only work), complete without a PR:
   ```bash
   agentrelay-complete-no-pr
   ```

If you cannot complete the work, signal failure instead:
   ```bash
   agentrelay-failed --reason "reason for failure"
   ```

**Important**: The orchestrator is waiting for the signal. Do not skip step 2."""


def _load_template(role_value: str, adapter_name: Optional[str]) -> str:
    """Load template text, trying adapter-specific then shared.

    Args:
        role_value: Role enum value string (e.g. ``"test_writer"``).
        adapter_name: Optional adapter name for override lookup.

    Returns:
        Raw template text.

    Raises:
        FileNotFoundError: If no template file exists.
    """
    filename = f"{role_value}.md"

    if adapter_name is not None:
        adapter_path = _TEMPLATES_DIR / adapter_name / filename
        if adapter_path.is_file():
            return adapter_path.read_text()

    shared_path = _TEMPLATES_DIR / filename
    if shared_path.is_file():
        return shared_path.read_text()

    raise FileNotFoundError(
        f"No template found for role '{role_value}'. "
        f"Searched: {_TEMPLATES_DIR / filename}"
    )


__all__ = [
    "resolve_instructions",
]
