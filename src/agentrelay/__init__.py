"""Clean redesign of agentrelay architecture.

This package contains the core abstractions for multi-agent orchestration,
designed with careful architectural consideration rather than incremental refactoring.

Core types:
- Task: frozen specification of a unit of work
- TaskRuntime: mutable envelope with state, artifacts, and live agent
- Agent: abstract base for live running agent instance
- TmuxAgent: concrete agent running in a tmux pane
- TaskStatus: execution state (PENDING, RUNNING, PR_CREATED, PR_MERGED, FAILED)
- TaskState: operational state (status, worktree, branch, error, attempts)
- TaskArtifacts: outputs of agent work (pr_url, concerns)
- AgentAddress / TmuxAddress: addressing a running agent
- TmuxEnvironment: execution environment configuration (tmux pane)
- AgentEnvironment: type alias union of all supported environment types
- AgentEnvironmentT: TypeVar for generic code preserving concrete environment type
- Configuration types: AgentConfig, ReviewConfig, TaskPaths
- Enums: AgentRole, AgentFramework, AgentVerbosity

See also:
- archive: archived v1 implementation (reference only)
"""
