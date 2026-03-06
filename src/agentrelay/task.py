"""Core data types for tasks in the agentrelay architecture.

This module defines frozen specifications for units of work in a task graph,
configuration types for agents and reviews, and enums for roles and execution states.

Classes:
    Task: A frozen specification of work to be done in the task graph.
    TaskPaths: File paths a task operates on (source, test, supplementary spec).
    AgentConfig: Framework and model configuration for executing an agent.
    ReviewConfig: Configuration for self-review before task completion.

Enums:
    AgentRole: The type of work a task performs.
    AgentFramework: The AI framework/platform executing an agent.
    AgentVerbosity: The detail level of Architecture Decision Records (ADRs).
    TaskStatus: The execution state of a task.

See also:
    environments: AgentEnvironment (type alias) and environment-specific types.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from agentrelay.environments import AgentEnvironment, TmuxEnvironment

# ── Enums ──


class AgentVerbosity(str, Enum):
    """Level of detail for Architecture Decision Records (ADRs) produced by agents.

    Attributes:
        NONE: No ADR produced.
        STANDARD: Basic ADR with key decisions.
        DETAILED: Comprehensive ADR with rationale and alternatives.
        EDUCATIONAL: Detailed ADR with educational explanations.
    """

    NONE = "none"
    STANDARD = "standard"
    DETAILED = "detailed"
    EDUCATIONAL = "educational"


class AgentFramework(str, Enum):
    """AI framework or platform that executes an agent.

    Attributes:
        CLAUDE_CODE: Claude Code (Anthropic's official CLI).

    Future frameworks (e.g., CODEX, COPILOT) can be added as needed.
    """

    CLAUDE_CODE = "claude_code"
    # Future: CODEX = "codex", COPILOT = "copilot", etc.


class AgentRole(str, Enum):
    """Type of work a task performs in the orchestration workflow.

    Attributes:
        SPEC_WRITER: Writes specifications for source files.
        TEST_WRITER: Writes test cases for source files.
        TEST_REVIEWER: Reviews tests written by test writers.
        IMPLEMENTER: Implements source code based on specs and tests.
        GENERIC: General-purpose task with no specific role.

    Note:
        MERGER is handled at the graph level, not as a task role.
    """

    SPEC_WRITER = "spec_writer"
    TEST_WRITER = "test_writer"
    TEST_REVIEWER = "test_reviewer"
    IMPLEMENTER = "implementer"
    GENERIC = "generic"
    # Note: MERGER is handled at graph level, not as a task role


class TaskStatus(str, Enum):
    """Execution state of a task during orchestration.

    Attributes:
        PENDING: Task is waiting to be executed.
        RUNNING: Task is currently being executed by an agent.
        PR_CREATED: Agent completed work; pull request exists against worktree branch.
        PR_MERGED: Pull request has been merged into the worktree primary branch.
        FAILED: Task execution failed.
    """

    PENDING = "pending"
    RUNNING = "running"
    PR_CREATED = "pr_created"  # Agent done; PR exists against worktree branch
    PR_MERGED = "pr_merged"  # PR merged into worktree primary branch
    FAILED = "failed"


# ── Configuration dataclasses ──


@dataclass(frozen=True)
class TaskPaths:
    """File paths a task operates on.

    Attributes:
        src: Tuple of source file paths to create or modify. Defaults to empty.
        test: Tuple of test file paths to create or modify. Defaults to empty.
        spec: Path to supplementary specification file, or None if not applicable.
    """

    src: tuple[str, ...] = ()
    test: tuple[str, ...] = ()
    spec: Optional[str] = None


@dataclass(frozen=True)
class AgentConfig:
    """Framework and model configuration for executing an agent.

    This configuration specifies which AI framework and model to use for
    executing an agent, where to run it, and how verbosely to document decisions.
    It is used for primary agents, review agents, and merger agents.

    Attributes:
        framework: The AI framework to use. Defaults to CLAUDE_CODE.
        model: The model identifier (e.g., "claude-opus-4-6"), or None to use
            the framework's default model.
        adr_verbosity: Level of detail for Architecture Decision Records produced
            by the agent. Defaults to NONE (no ADR produced).
        environment: Execution environment configuration (tmux, cloud, etc.).
            Defaults to TmuxEnvironment.
    """

    framework: AgentFramework = AgentFramework.CLAUDE_CODE
    model: Optional[str] = None
    adr_verbosity: AgentVerbosity = AgentVerbosity.NONE
    environment: AgentEnvironment = field(default_factory=TmuxEnvironment)


@dataclass(frozen=True)
class ReviewConfig:
    """Configuration for agent self-review before task completion.

    When specified, the agent will self-review its work before signaling
    task completion, starting from a specified attempt number.

    Attributes:
        agent: AgentConfig specifying which framework and model performs the review.
        review_on_attempt: The attempt number at which to begin self-review.
            Defaults to 1 (review on first attempt).
    """

    agent: AgentConfig
    review_on_attempt: int = 1


# ── Core task type ──


@dataclass(frozen=True)
class Task:
    """Frozen specification of a unit of work in the task graph.

    A Task defines WHAT work needs doing (role, paths, description).
    It does NOT track HOW the work is executed (Agent responsibility)
    or WHEN it runs (Orchestrator responsibility).

    Tasks are immutable and hashable, making them safe for use in
    dependency tuples and as dictionary keys.

    Attributes:
        id: Unique identifier for this task within the graph.
        role: The type of work this task performs (AgentRole enum).
        description: Optional human-readable description of the task.
        paths: File paths the task operates on (source, test, spec).
            Defaults to empty paths.
        dependencies: Tuple of Task objects that must complete before this
            task can run. Defaults to empty tuple.
        completion_gate: Optional shell command (exit code 0 = success)
            that determines if the task is complete. None = no gate.
        max_gate_attempts: Maximum number of gate execution attempts
            before the task fails. None = inherit from orchestrator.
        primary_agent: AgentConfig specifying which framework and model
            executes this task. Defaults to CLAUDE_CODE.
        review: Optional ReviewConfig for self-review before completion.
            None = no self-review.
    """

    id: str
    role: AgentRole
    description: Optional[str] = None
    paths: TaskPaths = field(default_factory=TaskPaths)
    dependencies: tuple["Task", ...] = ()
    completion_gate: Optional[str] = None
    max_gate_attempts: Optional[int] = None
    primary_agent: AgentConfig = field(default_factory=AgentConfig)
    review: Optional[ReviewConfig] = None
