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
        return f"# Task: {manifest.task_id}\n\n{manifest.description}\n"

    template_text = _load_template(role.value, adapter_name)

    substitutions = {
        "role": role.value.upper(),
        "description": manifest.description or "",
        "src_paths": _format_paths(manifest.src_paths),
        "test_paths": _format_paths(manifest.test_paths),
        "spec_path": (
            str(manifest.spec_path)
            if manifest.spec_path is not None
            else _NONE_PLACEHOLDER
        ),
        "task_id": manifest.task_id,
    }

    return Template(template_text).substitute(substitutions)


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
