"""Clean redesign of agentrelay architecture.

This package contains the core abstractions for multi-agent orchestration,
designed with careful architectural consideration rather than incremental refactoring.

Core types:
- TaskGraph: immutable DAG of Task specs                     [task_graph/graph.py]
- TaskGraphBuilder: YAML/dict -> TaskGraph builder           [task_graph/builder.py]
- TaskRuntimeBuilder: TaskGraph -> TaskRuntime map builder   [task_runtime/builder.py]
- WorkstreamRuntimeBuilder: TaskGraph -> WorkstreamRuntime map builder [workstream/core/runtime_builder.py]
- TaskRunner: one-task lifecycle state machine               [task_runner/core/runner.py]
- TaskRunnerIO: composed I/O boundary for TaskRunner         [task_runner/core/io.py]
- WorkstreamRunner: workstream lifecycle runner              [workstream/core/runner.py]
- WorkstreamRunnerIO: composed I/O boundary for WorkstreamRunner [workstream/core/io.py]
- Orchestrator: async graph scheduler over TaskRuntime        [orchestrator/orchestrator.py]
- OrchestratorConfig: scheduler/retry/teardown configuration [orchestrator/orchestrator.py]
- OrchestratorResult: terminal orchestration outcome         [orchestrator/orchestrator.py]
- WorkstreamSpec: immutable workstream configuration          [workstream/core/workstream.py]
- Task: frozen specification of a unit of work              [task.py]
- TaskPaths, AgentConfig, ReviewConfig: config dataclasses  [task.py]
- AgentRole, AgentFramework, AgentVerbosity: spec enums     [task.py]
- AgentEnvironment: type alias for all environment types    [environments.py]
- AgentEnvironmentT: TypeVar preserving concrete env type   [environments.py]
- TmuxEnvironment: tmux pane execution environment          [environments.py]
- AgentAddress: abstract base for addressing a running agent [agent/core/addressing.py]
- TmuxAddress: concrete tmux pane address                   [agent/implementations/tmux_address.py]
- Agent: abstract base for a live running agent instance    [agent/core/agent.py]
- TmuxAgent: concrete agent running in a tmux pane          [agent/implementations/tmux_agent.py]
- TaskStatus: execution state enum (PENDING -> FAILED)       [task_runtime/runtime.py]
- TaskState: mutable operational state of a running task    [task_runtime/runtime.py]
- TaskArtifacts: outputs of agent work (pr_url, concerns)   [task_runtime/runtime.py]
- TaskRuntime: mutable envelope with Task, state, artifacts [task_runtime/runtime.py]
- WorkstreamStatus: lane state enum (PENDING -> FAILED)      [workstream/core/runtime.py]
- WorkstreamState: mutable operational state of a lane       [workstream/core/runtime.py]
- WorkstreamArtifacts: outputs of lane execution             [workstream/core/runtime.py]
- WorkstreamRuntime: mutable lane envelope                   [workstream/core/runtime.py]
- LocalWorkspaceRef: resolved local workspace details        [workspace.py]
- WorkspaceRef: type alias for workspace references          [workspace.py]

See also:
- errors: typed integration failure model + classification helper
- prototypes.v01: v1 prototype implementation (reference only)
"""
