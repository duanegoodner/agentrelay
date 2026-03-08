# agentrelay

A Python orchestration system for multi-agent coding workflows. 

## Description

**agentrelay** allows users to define a collection of interdependent coding tasks as nodes in a graph. Each task specifies its role (e.g., spec writer, test writer, implementer), file paths, and dependencies.  An orchestrator manages the execution order, launching of coding agents that complete the tasks, and merging of results. Communication between the orchestrator and agents is handled primarily through the filesystem. When launching an agent, the orchestrator sends it a minimial prompt indicating where (in the filesystem) to find the task specification. The agent works in isolation, commits its changes, and signals completion by writing to a designated file.

## Status

An end-to-end prototype implemented in `./src/agentrelay/prototypes/v01/` loads YAML-defined graph, launches tmux-backed Claude Code agents to work on tasks in isolated git worktrees, and merges results via PRs. The prototype supports TDD workflows with distinct `test_writer`, `test_reviewer`, and `implementer` roles.

Current work is focused on formalizing interfaces for the core abstractions that emerged during prototyping and re-building the tmux + Claude Code workflow as implementations of those interfaces. Future work will extend support to cloud environments and additional agent frameworks.


## Documentation
See https://duanegoodner.github.io/agentrelay/


## Getting Started

### Requirements

- Python 3.12+
- [pixi](https://pixi.sh)
- git (with worktree support)
- tmux
- [Claude Code](https://github.com/anthropics/claude-code)

### Installation

```bash
git clone https://github.com/duanegoodner/agentrelay.git
cd agentrelay
pixi install
pixi run check   # format + typecheck + tests
```

### Development

```bash
pixi run test        # Run tests
pixi run typecheck   # Pyright static analysis
pixi run format      # black + isort
pixi run check       # All three
pixi run docs        # Serve docs at http://localhost:8000
```


