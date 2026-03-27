"""Core configuration types for agent sandboxing.

This module defines the data types that describe sandbox isolation levels,
token permission tiers, and execution contexts for sandboxed agents.

Enums:
    SandboxType: Type of sandbox execution boundary (none, container).
    TokenTier: Permission tier for credential injection.

Classes:
    IsolationConfig: Frozen, fully-resolved sandbox configuration.
    SandboxContext: Frozen execution context passed to sandbox operations.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class SandboxType(str, Enum):
    """Type of sandbox execution boundary.

    Attributes:
        NONE: No sandbox — agent runs directly on the host.
        CONTAINER: Agent runs inside a container (Docker/Podman).
    """

    NONE = "none"
    CONTAINER = "container"


class TokenTier(str, Enum):
    """Permission tier for credential injection into sandboxed agents.

    Attributes:
        READ_ONLY: Read-only access (e.g., repo clone, PR read).
        STANDARD: Standard access (e.g., push branches, create PRs).
        ELEVATED: Elevated access (e.g., merge PRs, admin operations).
    """

    READ_ONLY = "read_only"
    STANDARD = "standard"
    ELEVATED = "elevated"


@dataclass(frozen=True)
class IsolationConfig:
    """Fully-resolved sandbox configuration for an agent or task.

    All fields are required — partial/inherited configs are resolved
    during YAML parsing before constructing this type.

    Attributes:
        sandbox_type: Type of sandbox boundary (none or container).
        token_tier: Permission tier for credential injection.
        image: Container image name, or None for default.
        runtime: Container runtime binary (e.g., ``"docker"``, ``"podman"``),
            or None for default.
    """

    sandbox_type: SandboxType
    token_tier: TokenTier
    image: Optional[str] = None
    runtime: Optional[str] = None


@dataclass(frozen=True)
class SandboxContext:
    """Execution context passed to sandbox operations.

    Provides the sandbox implementation with the paths, identifiers, and
    environment variables it needs to set up and wrap agent commands.

    Attributes:
        worktree_path: Absolute path to the git worktree for this task.
        signal_dir: Absolute path to the signal directory for this task.
        repo_path: Absolute path to the main repository.
        task_id: Unique identifier of the task being sandboxed.
        graph_name: Name of the task graph being executed.
        env_vars: Environment variables to inject into the sandbox.
    """

    worktree_path: Path
    signal_dir: Path
    repo_path: Path
    task_id: str
    graph_name: str
    env_vars: dict[str, str] = field(default_factory=dict)
