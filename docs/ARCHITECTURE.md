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
- `StepDispatch`: per-step dispatch table for framework/environment-specific implementations
- `WorkstreamRunner`: workstream-level lifecycle runner (holds per-step protocol fields directly)
- `build_standard_runner`: factory wiring `StandardTaskRunner` for worktree + tmux + Claude Code
- `build_standard_workstream_runner`: factory wiring `StandardWorkstreamRunner` for git + GitHub CLI
- `Orchestrator`: async dependency/workstream scheduler over graph runtimes
- `OrchestratorConfig`: run-level scheduling, retry, and teardown policy
- `errors`: typed integration failure model + expected/internal classification helper
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
- **Contract-first integrations**: external side effects are modeled as typed protocols/errors before concrete implementations.

## Execution Boundary

The current architecture layer includes a real orchestrator, task lifecycle runner,
workstream lifecycle runner, and a CLI entry point (`run_graph.py`). All production
side-effect integrations (worktree setup, tmux launch, signal polling, PR merge,
workstream prepare/merge/teardown) are wired through the composition layer.

## Orchestrator Behavior Contract

The orchestrator currently enforces:

- Dependency-aware scheduling (`TaskGraph.ready_ids(...)`).
- Workstream constraints:
  - one active task per workstream,
  - child workstreams wait for parent workstream `MERGED`,
  - ancestor workstream failure blocks descendants.
- Retry policy for expected task failures (`TaskRunner.run(...)` returns `FAILED`).
- Internal/system failure boundary for raised task-run exceptions:
  - traceback recorded in orchestrator result,
  - fail-fast path may cancel in-flight work (configurable).
- Task teardown policy forwarding through `OrchestratorConfig.task_teardown_mode`.

## Relationship To Prototype v01

Prototype docs and historical decisions are under `docs/prototypes/v01/`.
Use those docs for runnable workflow behavior today; use this page for the target architecture model.
