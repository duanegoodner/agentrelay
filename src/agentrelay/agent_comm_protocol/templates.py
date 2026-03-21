"""Role template resolution — Layer 2 of the agent communication protocol.

Resolves role-appropriate markdown instruction templates, substituting
manifest data using ``string.Template`` (``$var`` syntax).

Functions:
    resolve_instructions: Load and parameterize a role template.
"""

from __future__ import annotations

from pathlib import Path
from string import Template
from typing import Optional

from agentrelay.agent_comm_protocol.manifest import TaskManifest
from agentrelay.task import AgentRole
from agentrelay.tools import tool_guidance

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

_NONE_PLACEHOLDER = "(none specified)"


def _format_paths(paths: tuple[Path, ...]) -> str:
    """Join paths with spaces, or return a placeholder if empty."""
    return " ".join(str(p) for p in paths) if paths else _NONE_PLACEHOLDER


def resolve_instructions(
    role: AgentRole,
    manifest: TaskManifest,
    adapter_name: Optional[str] = None,
) -> str:
    """Resolve work instructions by loading and parameterizing a role template.

    Resolution order:

    1. Adapter-specific: ``templates/<adapter_name>/<role>.md``
    2. Shared: ``templates/<role>.md``
    3. Fallback for ``GENERIC`` role: returns task description as instructions.

    Template variables (``$var`` syntax via :class:`string.Template`):

    - ``$role`` — uppercase role name
    - ``$description`` — task description
    - ``$src_paths`` — space-joined source paths, or ``"(none specified)"``
    - ``$test_paths`` — space-joined test paths, or ``"(none specified)"``
    - ``$spec_path`` — spec path, or ``"(none specified)"``
    - ``$task_id`` — task identifier

    Args:
        role: Agent role determining which template to load.
        manifest: Task manifest providing substitution values.
        adapter_name: Optional adapter name for adapter-specific override.

    Returns:
        Resolved markdown instruction text.

    Raises:
        FileNotFoundError: If no template found for a non-GENERIC role.
        ValueError: If GENERIC role has no description.
    """
    if role == AgentRole.GENERIC:
        if manifest.description is None:
            raise ValueError(
                f"GENERIC role requires a task description, but task "
                f"'{manifest.task_id}' has description=None."
            )
        work_section = f"# Task: {manifest.task_id}\n\n{manifest.description}\n"
    else:
        template_text = _load_template(role.value, adapter_name)

        description_section = (
            f"## Task Description\n\n{manifest.description}\n"
            if manifest.description
            else ""
        )

        substitutions = {
            "role": role.value.upper(),
            "description": manifest.description or "",
            "description_section": description_section,
            "src_paths": _format_paths(manifest.src_paths),
            "test_paths": _format_paths(manifest.test_paths),
            "spec_path": (
                str(manifest.spec_path)
                if manifest.spec_path is not None
                else _NONE_PLACEHOLDER
            ),
            "task_id": manifest.task_id,
        }

        work_section = Template(template_text).substitute(substitutions)

    return work_section + _workflow_footer(manifest)


def _workflow_footer(manifest: TaskManifest) -> str:
    """Build the standard workflow completion steps appended to all instructions.

    Tells the agent how to commit, push, and use the CLI commands to create
    a PR and signal the orchestrator. Includes tool guidance if tools are
    declared in the graph.
    """
    tools_section = tool_guidance(manifest.tools)
    if tools_section:
        tools_section = "\n" + tools_section + "\n"

    return f"""{tools_section}
## Workflow — completion steps

After completing the work above:

1. **Commit and push** all changes to branch `{manifest.branch_name}`.
2. **Record any design concerns** you encountered (optional — skip if none):
   ```bash
   agentrelay-concern --message "description of concern"
   ```
3. **Complete the task** (creates PR and signals the orchestrator):
   ```bash
   agentrelay-complete --title "short summary of changes" --body "## Summary

   - what was done"
   ```
   Provide a meaningful PR title (concise) and body (markdown with a ## Summary section).
   Any recorded concerns are automatically appended to the PR body.

If you cannot complete the work, signal failure instead:
   ```bash
   agentrelay-failed --reason "reason for failure"
   ```

**Important**: The orchestrator is waiting for the signal. Do not skip step 3.
"""


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
