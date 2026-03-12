"""Clean redesign of agentrelay architecture.

This package contains the core abstractions for multi-agent orchestration,
designed with careful architectural consideration rather than incremental refactoring.

Core types:
- TaskGraph: immutable DAG of Task specs                     [task_graph/graph.py]
- TaskGraphBuilder: YAML/dict -> TaskGraph builder           [task_graph/builder.py]
- TaskRuntimeBuilder: TaskGraph -> TaskRuntime map builder   [task_runtime/builder.py]
- WorkstreamRuntimeBuilder: TaskGraph -> WorkstreamRuntime map builder [workstream/runtime_builder.py]
- TaskRunner: one-task lifecycle state machine               [task_runner/runner.py]
- TaskRunnerIO: composed I/O boundary for TaskRunner         [task_runner/io.py]
- WorkstreamRunner: workstream lifecycle runner              [workstream/runner.py]
- WorkstreamRunnerIO: composed I/O boundary for WorkstreamRunner [workstream/io.py]
- Orchestrator: async graph scheduler over TaskRuntime        [orchestrator.py]
- OrchestratorConfig: scheduler/retry/teardown configuration [orchestrator.py]
- OrchestratorResult: terminal orchestration outcome         [orchestrator.py]
- WorkstreamSpec: immutable workstream configuration          [workstream/workstream.py]
- Task: frozen specification of a unit of work              [task.py]
- TaskPaths, AgentConfig, ReviewConfig: config dataclasses  [task.py]
- AgentRole, AgentFramework, AgentVerbosity: spec enums     [task.py]
- AgentEnvironment: type alias for all environment types    [environments.py]
- AgentEnvironmentT: TypeVar preserving concrete env type   [environments.py]
- TmuxEnvironment: tmux pane execution environment          [environments.py]
- AgentAddress: abstract base for addressing a running agent [agent/addressing.py]
- TmuxAddress: concrete tmux pane address                   [agent/addressing.py]
- Agent: abstract base for a live running agent instance    [agent/agent.py]
- TmuxAgent: concrete agent running in a tmux pane          [agent/agent.py]
- TaskStatus: execution state enum (PENDING -> FAILED)       [task_runtime/runtime.py]
- TaskState: mutable operational state of a running task    [task_runtime/runtime.py]
- TaskArtifacts: outputs of agent work (pr_url, concerns)   [task_runtime/runtime.py]
- TaskRuntime: mutable envelope with Task, state, artifacts [task_runtime/runtime.py]
- WorkstreamStatus: lane state enum (PENDING -> FAILED)      [workstream/runtime.py]
- WorkstreamState: mutable operational state of a lane       [workstream/runtime.py]
- WorkstreamArtifacts: outputs of lane execution             [workstream/runtime.py]
- WorkstreamRuntime: mutable lane envelope                   [workstream/runtime.py]
- LocalWorkspaceRef: resolved local workspace details        [workspace.py]
- RemoteWorkspaceRef: resolved remote workspace details      [workspace.py]

See also:
- errors: typed integration failure model + classification helper
- prototypes.v01: v1 prototype implementation (reference only)
"""
