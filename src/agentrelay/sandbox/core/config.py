"""Core configuration types for agent sandboxing.

This module defines the data types that describe sandbox isolation levels,
token permission tiers, container runtimes, credential types, and execution
contexts for sandboxed agents.

Enums:
    SandboxType: Type of sandbox execution boundary (none, OCI container).
    TokenTier: Permission tier for credential injection.
    ContainerRuntime: Container runtime binary (docker, podman).
    CredentialType: Type of Anthropic credential (API key, OAuth).

Classes:
    IsolationConfig: Frozen, fully-resolved sandbox configuration.
    AnthropicCredential: Resolved Anthropic credential for agent auth.
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
        OCI: Agent runs inside an OCI container (Docker/Podman).
    """

    NONE = "none"
    OCI = "oci"


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


class ContainerRuntime(str, Enum):
    """Container runtime binary for OCI sandbox execution.

    Attributes:
        DOCKER: Docker container runtime.
        PODMAN: Podman container runtime.
    """

    DOCKER = "docker"
    PODMAN = "podman"


class CredentialType(str, Enum):
    """Type of Anthropic credential for agent authentication.

    Attributes:
        API_KEY: Pay-per-token API key (injected as env var).
        OAUTH: Max plan OAuth token file (``.credentials.json``).
    """

    API_KEY = "api_key"
    OAUTH = "oauth"


@dataclass(frozen=True)
class AnthropicCredential:
    """Resolved Anthropic credential for agent authentication.

    Holds a named credential entry from the credentials YAML
    ``anthropic`` section, with type-specific fields populated.

    Attributes:
        name: Key from the YAML ``anthropic`` section (e.g.,
            ``"dev_api_key"``, ``"max_plan"``).
        credential_type: Whether this is an API key or OAuth credential.
        api_key: The API key string.  Set when ``credential_type``
            is :attr:`CredentialType.API_KEY`, ``None`` otherwise.
        oauth_path: Path to the ``.credentials.json`` file.  Set when
            ``credential_type`` is :attr:`CredentialType.OAUTH`,
            ``None`` otherwise.
    """

    name: str
    credential_type: CredentialType
    api_key: Optional[str] = None
    oauth_path: Optional[Path] = None


@dataclass(frozen=True)
class IsolationConfig:
    """Fully-resolved sandbox configuration for an agent or task.

    All fields are required — partial/inherited configs are resolved
    during YAML parsing before constructing this type.

    Attributes:
        sandbox_type: Type of sandbox boundary (none or OCI container).
        token_tier: Permission tier for credential injection.
        image: Container image name, or None for default.
        runtime: Container runtime, or None for default (Docker).
    """

    sandbox_type: SandboxType
    token_tier: TokenTier
    image: Optional[str] = None
    runtime: Optional[ContainerRuntime] = None


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
