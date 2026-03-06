# agentrelaysmall

A lightweight custom multi-agent orchestration system for coding workflows.

## Overview

agentrelaysmall is a Python orchestrator that manages a graph of coding tasks, each executed by Claude Code running in its own tmux pane and git worktree. The system uses sentinel files for signaling, git worktrees for isolation, and dependency graphs for task orchestration.

## Key Features

- **Simple architecture** — built directly on Python subprocess and git, no heavyweight frameworks
- **Task graphs** — define workflows as DAGs with dependencies
- **Tmux integration** — run agents interactively in tmux panes for visibility
- **Git worktrees** — each task gets its own worktree and branch for isolation
- **Sentinel signals** — agents communicate status via files (`.done`, `.failed`, etc.)
- **PR automation** — agents create pull requests and signal completion

## Core Concepts

The system centers on a few key data types:

- **Task** — An immutable specification of work to be done (role, paths, description)
- **TaskRuntime** — Mutable runtime envelope tracking a task's execution state
- **Agent** — An abstract interface for running agents in different environments (tmux, cloud, etc.)
- **AgentEnvironment** — Type alias for different agent execution environments

## Documentation

See the [API Reference](api/task.md) for detailed class and module documentation.

For architecture and workflow details, see the project documentation:
- `docs/PROJECT_DESCRIPTION.md` — what this system does and why
- `docs/DESIGN_DECISIONS.md` — architectural rationale
- `docs/WORKFLOW_DESCRIPTION.md` — end-to-end workflow specification
