"""v2: Clean redesign of agentrelaysmall architecture.

This package contains a reimplementation of the core abstractions,
designed with careful architectural consideration rather than incremental refactoring.

Core types:
- Task: frozen specification of a unit of work
- TaskRuntime: mutable envelope with state, artifacts, and live agent
- Agent: live running agent instance
- TaskStatus: execution state (PENDING, RUNNING, PR_CREATED, PR_MERGED, FAILED)
- TaskState: operational state (status, worktree, branch, error, attempts)
- TaskArtifacts: outputs of agent work (pr_url, concerns)
- AgentAddress / TmuxAddress: addressing a running agent
- Configuration types: AgentConfig, ReviewConfig, TaskPaths
- Enums: AgentRole, AgentFramework, AgentVerbosity
"""
