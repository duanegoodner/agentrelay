# Architecture

## Overview

`agentrelay` currently has a clean architecture layer plus a legacy prototype layer:

- **Current architecture**: `src/agentrelay/`
- **Prototype reference/runner**: `src/agentrelay/prototypes/v01/`

This page documents the current architecture layer only.

This page intentionally tracks architecture at the abstraction level rather than
by module/file listing. The API reference and design diagram are the source of
truth for concrete implementation details.

## Core Abstractions

- `TaskGraph`: immutable DAG of `Task` specifications plus workstream metadata
- `TaskGraphBuilder`: YAML/dict schema parser that builds validated `TaskGraph`
- `TaskRuntimeBuilder`: graph-to-runtime initializer for task execution state
- `WorkstreamRuntimeBuilder`: graph-to-runtime initializer for workstream lane state
- `TaskRunner`: one-task lifecycle state machine over `TaskRuntime`
- `TaskRunnerIO`: side-effect boundary used by `TaskRunner` (launch/poll/merge/teardown)
- `Orchestrator`: async dependency/workstream scheduler over graph runtimes
- `OrchestratorConfig`: run-level scheduling, retry, and teardown policy
- `WorkstreamSpec`: immutable definition of a task workstream lane
- `Task`: immutable specification of a unit of work
- `TaskRuntime`: mutable execution envelope attached to a `Task`
- `TaskState`: operational task state (status, worktree/branch, attempts, errors)
- `TaskArtifacts`: outputs produced during execution (for example PR URL and concerns)
- `TaskStatus`: lifecycle state enum used by the runtime
- `WorkstreamRuntime`: mutable execution envelope attached to a `WorkstreamSpec`
- `WorkstreamState`: operational lane state (status, worktree/branch, active task, errors)
- `WorkstreamArtifacts`: outputs produced during lane execution (for example merge PR URL and concerns)
- `WorkstreamStatus`: lifecycle state enum used by workstream runtime
- `Agent`: abstract interface for a live running coding agent
- `AgentAddress`: abstract location/identity for a running agent
- `AgentEnvironment`: execution-environment abstraction (currently tmux)

## Detailed References

- API details: [API Reference](api/index.md)
- Structural view: [DIAGRAM.md](DIAGRAM.md)

## Design Principles

- **Immutable spec vs mutable runtime**: execution never mutates the task definition.
- **Pluggable configuration**: framework and environment are explicit config fields.
- **Narrow interfaces**: `Agent`, `AgentAddress`, and environment typing keep launcher logic decoupled.

## Execution Boundary (What Is Not Implemented Here Yet)

The current architecture layer includes a real orchestrator and task lifecycle runner,
but production side-effect integrations remain incomplete. End-to-end behavior for tmux
launch, prompt dispatch, signal polling, and PR integration still primarily lives in
`src/agentrelay/prototypes/v01/`.

## Relationship To Prototype v01

Prototype docs and historical decisions are under `docs/prototypes/v01/`.
Use those docs for runnable workflow behavior today; use this page for the target architecture model.
