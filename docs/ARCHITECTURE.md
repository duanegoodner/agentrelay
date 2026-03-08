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

- `Task`: immutable specification of a unit of work
- `TaskRuntime`: mutable execution envelope attached to a `Task`
- `TaskState`: operational task state (status, worktree/branch, attempts, errors)
- `TaskArtifacts`: outputs produced during execution (for example PR URL and concerns)
- `TaskStatus`: lifecycle state enum used by the runtime
- `Agent`: abstract interface for a live running coding agent
- `AgentAddress`: abstract location/identity for a running agent
- `AgentEnvironment`: execution-environment abstraction (currently tmux)

## Detailed References

- API details: [API Reference](api/task.md)
- Structural view: [DIAGRAM.md](DIAGRAM.md)

## Design Principles

- **Immutable spec vs mutable runtime**: execution never mutates the task definition.
- **Pluggable configuration**: framework and environment are explicit config fields.
- **Narrow interfaces**: `Agent`, `AgentAddress`, and environment typing keep launcher logic decoupled.

## Execution Boundary (What Is Not Implemented Here Yet)

The current architecture layer does not yet include a real orchestrator/launcher implementation.
End-to-end behavior (tmux launch, prompt dispatch, signal polling, PR merge flow) still lives in `src/agentrelay/prototypes/v01/`.

## Relationship To Prototype v01

Prototype docs and historical decisions are under `docs/prototypes/v01/`.
Use those docs for runnable workflow behavior today; use this page for the target architecture model.
