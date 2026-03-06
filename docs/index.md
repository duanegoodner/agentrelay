# agentrelaysmall

A Python orchestrator for multi-agent coding workflows. Manage a graph of tasks, each executed by Claude Code in its own tmux pane and git worktree.

## Quick Links

- **[Architecture](ARCHITECTURE.md)** — Core design and module structure
- **[Workflow](WORKFLOW.md)** — How tasks are executed (coming soon)
- **[Guide](GUIDE.md)** — Setup and installation
- **[API Reference](api/task.md)** — Auto-generated from code
- **[Backlog](BACKLOG.md)** — Ideas and future work

## Current Status

The v2 architecture is in place with core data types (`Task`, `TaskRuntime`, `Agent`, `AgentEnvironment`) and comprehensive test coverage. Building toward a functional task execution workflow.
