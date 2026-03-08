# Architecture

## Overview

`agentrelay` currently has a clean architecture layer plus a legacy prototype layer:

- **Current architecture**: `src/agentrelay/`
- **Prototype reference/runner**: `src/agentrelay/prototypes/v01/`

This page documents the current architecture layer only.

## Implemented Modules

### `task.py` (immutable task specification)

- `Task`: frozen definition of a unit of work
- `TaskPaths`: source/test/spec path set for a task
- `AgentConfig`: framework/model/environment configuration
- `ReviewConfig`: optional self-review configuration
- `AgentRole`, `AgentFramework`, `AgentVerbosity`: enums

### `task_runtime.py` (mutable execution envelope)

- `TaskStatus`: runtime status enum (`PENDING`, `RUNNING`, `PR_CREATED`, `PR_MERGED`, `FAILED`)
- `TaskState`: mutable operational state (worktree path, branch, attempt, errors)
- `TaskArtifacts`: runtime outputs (PR URL, concerns)
- `TaskRuntime`: groups immutable `Task` with mutable state/artifacts and optional live `Agent`

### `addressing.py` (how to locate running agents)

- `AgentAddress`: abstract address contract
- `TmuxAddress`: concrete `session:pane_id` address

### `environments.py` (where agents run)

- `TmuxEnvironment`: frozen config for tmux execution
- `AgentEnvironment`: type alias (currently `TmuxEnvironment`)
- `AgentEnvironmentT`: TypeVar bound to `AgentEnvironment`

### `agent.py` (live agent interface)

- `Agent`: abstract base with `send_kickoff()` and `address`
- `TmuxAgent`: concrete tmux-backed agent type
- `TmuxAgent.from_config()` and `TmuxAgent.send_kickoff()` are currently stubs (`NotImplementedError`)

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

## Tests

`pixi run pytest --collect-only -q` currently reports **467 tests collected** across current architecture and prototype modules.

## Diagram

The class-level design diagram is maintained in [DIAGRAM.md](DIAGRAM.md).
