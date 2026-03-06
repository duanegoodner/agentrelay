# agentrelaysmall

> **This project is a work in progress and is not yet functional.** The core data model and test suite are in place; task execution, orchestration, and agent launch are not yet implemented.

A Python orchestration system for multi-agent coding workflows. The goal: define a graph of coding tasks, and have each task executed autonomously by a Claude Code agent in its own tmux pane and git worktree, with the orchestrator managing dependencies and merging results.

## Concept

Each task in the graph specifies what work to do (role, file paths, description) and how to do it (AI framework, model, execution environment). The orchestrator runs tasks in dependency order — each agent works in isolation, commits its output, and signals completion. The orchestrator merges results.

Planned task roles:

| Role | Purpose |
|------|---------|
| `generic` | General-purpose coding task |
| `spec_writer` | Writes a specification document |
| `test_writer` | Writes tests and a stub implementation |
| `test_reviewer` | Reviews and approves tests |
| `implementer` | Implements code to pass the tests |

The `test_writer → test_reviewer → implementer` sequence supports a TDD workflow.

## Current state

The v2 architecture has a typed, well-tested data model:

- `Task` — frozen specification of a unit of work (id, role, paths, dependencies, agent config)
- `TaskRuntime` — mutable execution envelope (status, worktree path, PR URL, agent handle)
- `Agent` / `TmuxAgent` — abstract and concrete types for running agent instances (stubbed)
- `AgentEnvironment` / `TmuxEnvironment` — pluggable execution environment config

467 tests pass. Orchestration, agent launch, and worktree management are not yet implemented.

## Requirements

- Python 3.12+
- [pixi](https://pixi.sh)
- git (with worktree support)
- tmux
- [Claude Code](https://github.com/anthropics/claude-code)

## Installation

```bash
git clone https://github.com/duanegoodner/agentrelaysmall.git
cd agentrelaysmall
pixi install
pixi run check   # format + typecheck + tests
```

## Development

```bash
pixi run test        # Run tests
pixi run typecheck   # Pyright static analysis
pixi run format      # black + isort
pixi run check       # All three
pixi run docs        # Serve docs at http://localhost:8000
```

See [docs/GUIDE.md](docs/GUIDE.md) for setup details and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for design overview.
