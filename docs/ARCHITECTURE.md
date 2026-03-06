# Architecture

## Overview

agentrelaysmall is a Python orchestration system for multi-agent coding workflows. The core abstraction is a task graph: a DAG of tasks, each with a description, optional dependencies, and configuration specifying which AI framework and model should execute it.

## Current Modules

The current architecture lives at the root of `src/agentrelaysmall/`:

### Core Data Types

**`task.py`**
- `Task` — frozen specification of a unit of work (id, role, description, paths, dependencies, completion gate, etc.)
- `TaskPaths` — file paths a task operates on (src, test, spec)
- `TaskStatus` — enum for execution state (PENDING, RUNNING, PR_CREATED, PR_MERGED, FAILED)
- `AgentRole` — enum for task types (GENERIC, SPEC_WRITER, TEST_WRITER, TEST_REVIEWER, IMPLEMENTER)
- `AgentConfig` — framework + model configuration for executing agents
- `ReviewConfig` — configuration for self-review before task completion
- `AgentFramework` — enum for AI platforms (currently CLAUDE_CODE)
- `AgentVerbosity` — detail level for Architecture Decision Records

**`environments.py`**
- `TmuxEnvironment` — dataclass for tmux-based agent execution
- `AgentEnvironment` — type alias (currently bound to TmuxEnvironment; designed for future extensibility)
- `AgentEnvironmentT` — TypeVar for generic code working with agent environments

**`task_runtime.py`**
- `TaskRuntime` — mutable envelope wrapping a frozen Task with execution state
- `TaskState` — operational state of a running task (status, worktree path, branch, error, attempt count)
- `TaskArtifacts` — outputs produced by a task (PR URL, design concerns)
- `AgentAddress` — abstract base for addressing running agents
- `TmuxAddress` — concrete address for agents in tmux panes (session + pane_id)

**`agent.py`**
- `Agent` — abstract base for live running agent instances
- `TmuxAgent` — concrete implementation for agents in tmux panes
- Provides `from_config()` factory (currently stubbed) and `send_kickoff()` for agent initialization

### Design Principles

**Type Safety & Immutability**
- `Task` is frozen (immutable) — defines work to be done
- `TaskRuntime` is mutable — tracks execution progress
- Clear separation: spec (immutable) vs. state (mutable)

**Pluggability**
- `AgentEnvironment` is a type alias (not an empty ABC), allowing future environments (cloud agents, subprocess, etc.) to be added without modifying core interfaces
- `AgentConfig` accepts any AI framework; currently only CLAUDE_CODE is implemented
- Signal and coordination mechanisms are agent-environment-agnostic

**Simplicity**
- No frameworks (LangChain, LangGraph, etc.) — direct Python + subprocess
- File-based coordination (no message queues or APIs)
- Google-style docstrings throughout for auto-generated documentation

## Archive

The original implementation (`src/agentrelaysmall/archive/`) served as a proof-of-concept but lacked clean separation between specs and runtime state. The current architecture replaces it as the primary implementation.

See `docs/archive/v1/HISTORY.md` for detailed history of the prototype.

## Test Coverage

All modules are comprehensively tested (467 tests). Tests live in `test/` (current implementation) and `test/archive/` (reference tests for the prototype).

## Future Extensibility

The current architecture is designed to support:

- **Multiple agent environments** — beyond tmux (cloud APIs, subprocess, etc.)
- **Multiple AI frameworks** — beyond Claude Code (Copilot, Codex, etc.)
- **Rich task metadata** — room to add verbosity levels, ADR generation, cost tracking, etc.
- **Flexible signaling** — coordination mechanism can evolve without changing core types

These extensions are anticipated but not yet implemented. Decisions will be made only as real needs emerge.
