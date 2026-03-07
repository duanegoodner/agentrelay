"""Clean redesign of agentrelay architecture.

This package contains the core abstractions for multi-agent orchestration,
designed with careful architectural consideration rather than incremental refactoring.

Core types:
- Task: frozen specification of a unit of work              [task.py]
- TaskPaths, AgentConfig, ReviewConfig: config dataclasses  [task.py]
- AgentRole, AgentFramework, AgentVerbosity: spec enums     [task.py]
- AgentEnvironment: type alias for all environment types    [environments.py]
- AgentEnvironmentT: TypeVar preserving concrete env type   [environments.py]
- TmuxEnvironment: tmux pane execution environment          [environments.py]
- AgentAddress: abstract base for addressing a running agent [addressing.py]
- TmuxAddress: concrete tmux pane address                   [addressing.py]
- Agent: abstract base for a live running agent instance    [agent.py]
- TmuxAgent: concrete agent running in a tmux pane          [agent.py]
- TaskStatus: execution state enum (PENDING → FAILED)       [task_runtime.py]
- TaskState: mutable operational state of a running task    [task_runtime.py]
- TaskArtifacts: outputs of agent work (pr_url, concerns)   [task_runtime.py]
- TaskRuntime: mutable envelope with Task, state, artifacts [task_runtime.py]

See also:
- archive: archived v1 implementation (reference only)
"""
