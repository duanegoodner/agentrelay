# Workflow

## Current Architecture Layer (`src/agentrelay/`)

Implemented workflow behavior in the current architecture now includes:

1. Define immutable work with `Task` and `TaskGraph`.
2. Load graph YAML with `TaskGraphBuilder`.
3. Initialize runtime state with `TaskRuntimeBuilder` and `WorkstreamRuntimeBuilder`.
4. Execute one task lifecycle with `TaskRunner`.
5. Schedule the graph with `Orchestrator` using dependency + workstream rules.

This gives us a full in-process orchestration model and execution-state model.

## What Is Not Yet Implemented In This Layer

- Non-stub `TmuxAgent.from_config()` and `TmuxAgent.send_kickoff()`
- Production `TaskRunnerIO` adapter for side effects (worktree setup, signal polling, PR operations)
- End-user CLI flow that runs the non-prototype orchestrator with real side-effect integrations

## Where End-To-End Workflow Exists Today

The runnable orchestration flow is in the v01 prototype:

- [Prototype workflow description](prototypes/v01/WORKFLOW_DESCRIPTION.md)
- [Prototype operations guide](prototypes/v01/OPERATIONS.md)
