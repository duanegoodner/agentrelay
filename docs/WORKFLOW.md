# Workflow

## Current Architecture Layer (`src/agentrelay/`)

Implemented workflow behavior in the current architecture is intentionally minimal:

1. Define immutable work with `Task`
2. Wrap task execution state in `TaskRuntime`
3. Track lifecycle state through `TaskStatus`
4. Attach a live `Agent` instance when one exists

This gives us a clean execution model, but not a full orchestrator loop yet.

## What Is Not Yet Implemented In This Layer

- Task graph scheduler/dispatcher
- Worktree creation + teardown orchestration
- Signal directory polling/merge automation
- Non-stub tmux agent launch and kickoff logic

## Where End-To-End Workflow Exists Today

The runnable orchestration flow is in the v01 prototype:

- [Prototype workflow description](prototypes/v01/WORKFLOW_DESCRIPTION.md)
- [Prototype operations guide](prototypes/v01/OPERATIONS.md)
