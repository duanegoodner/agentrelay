# agentrelay

`agentrelay` is a Python orchestration system for multi-agent coding workflows.
It models work as a dependency graph of tasks and emphasizes observable, file-based coordination.

📚 **Full documentation site:** https://duanegoodner.github.io/agentrelay/

## Status

The project is currently split into two layers:

- `src/agentrelay/` (current architecture): core data model and interfaces (`Task`, `TaskRuntime`, `Agent`, `AgentEnvironment`)
- `src/agentrelay/prototypes/v01/` (working prototype): tmux + git worktree + signal-file orchestration

The core architecture is the long-term direction. End-to-end execution currently lives in `prototypes/v01` while launcher/orchestrator integration is rebuilt around the new interfaces.

## Goals

- Orchestrate dependent coding tasks with explicit state transitions
- Keep agent execution isolated via git worktrees and per-task branches
- Preserve a durable audit trail of task outcomes via filesystem artifacts
- Keep framework overhead low and favor debuggable Python primitives

## Design Philosophy

- **Immutable spec, mutable runtime**: `Task` describes work; `TaskRuntime` tracks execution state.
- **Pluggable execution**: framework and environment are configuration, not hard-coded behavior.
- **Simple coordination**: files and git are preferred over always-on services.
- **Incremental evolution**: prove behavior in prototypes, then promote stable abstractions.

## Repository Map

- `src/agentrelay/` - current architecture modules
- `src/agentrelay/prototypes/v01/` - runnable v01 prototype implementation
- `test/` - tests for both current architecture and prototype
- `graphs/` - example graph YAML definitions
- `docs/` - project docs and mkdocs site source

## Getting Started

### Requirements

- Python 3.12+
- [pixi](https://pixi.sh)
- git (with worktree support)
- tmux (for prototype execution)
- [Claude Code](https://github.com/anthropics/claude-code) (for prototype execution)

### Installation

```bash
git clone https://github.com/duanegoodner/agentrelay.git
cd agentrelay
pixi install
```

### Development Commands

```bash
pixi run test        # run tests
pixi run typecheck   # pyright
pixi run format      # black + isort
pixi run check       # format + typecheck + tests
pixi run docs        # serve docs locally
```
