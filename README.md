# agentrelay

> **Early development — active work in progress.** Core abstractions are being established; end-to-end execution is not yet functional.

A Python orchestration system for multi-agent coding workflows. The goal: define a graph of coding tasks, and have each task executed autonomously by a Claude Code agent in its own tmux pane and git worktree, with the orchestrator managing dependencies and merging results.

## Concept

Each task in the graph specifies what work to do (role, file paths, description) and how to do it (AI framework, model, execution environment). The orchestrator runs tasks in dependency order — each agent works in isolation, commits its output, and signals completion. The orchestrator merges results.

Task roles:

| Role | Purpose |
|------|---------|
| `generic` | General-purpose coding task |
| `spec_writer` | Writes a specification document |
| `test_writer` | Writes tests and a stub implementation |
| `test_reviewer` | Reviews and approves tests |
| `implementer` | Implements code to pass the tests |

The `test_writer → test_reviewer → implementer` sequence supports a TDD workflow.

## Current state

The core data model is in place and well-tested:

- `Task` — frozen specification of a unit of work (id, role, paths, dependencies, agent config)
- `TaskRuntime` — mutable execution envelope (status, worktree path, PR URL, agent handle)
- `Agent` / `TmuxAgent` — abstract and concrete types for running agent instances
- `AgentEnvironment` / `TmuxEnvironment` — pluggable execution environment config

118 tests cover the current architecture; 349 more cover the v1 prototype. The orchestrator, agent launch, graph loading, and worktree management are under active development.

## Requirements

- Python 3.12+
- [pixi](https://pixi.sh)
- git (with worktree support)
- tmux
- [Claude Code](https://github.com/anthropics/claude-code)

## Installation

```bash
git clone https://github.com/duanegoodner/agentrelay.git
cd agentrelay
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
