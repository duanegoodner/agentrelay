# Guide

## Prerequisites

- Python 3.12+
- `pixi` (https://pixi.sh)
- `git` with worktree support

For running the v01 prototype orchestrator additionally:

- `tmux`
- `gh` (GitHub CLI, authenticated)
- Claude Code CLI

## Install

```bash
git clone https://github.com/duanegoodner/agentrelay.git
cd agentrelay
pixi install
```

## Verify

```bash
pixi run check
```

## Development Commands

```bash
pixi run test
pixi run typecheck
pixi run format
pixi run check
pixi run docs
```

## Prototype v01 Commands

Run a graph:

```bash
pixi run python -m agentrelay.prototypes.v01.run_graph graphs/<name>.yaml
```

Useful options:

```bash
pixi run python -m agentrelay.prototypes.v01.run_graph graphs/<name>.yaml --tmux-session <session>
pixi run python -m agentrelay.prototypes.v01.run_graph graphs/<name>.yaml --keep-panes
```

Reset a graph run:

```bash
pixi run python -m agentrelay.prototypes.v01.reset_graph graphs/<name>.yaml
pixi run python -m agentrelay.prototypes.v01.reset_graph graphs/<name>.yaml --yes
```

## Notes

- Prefer `pixi run <task>` over ad-hoc local environments.
- The current architecture modules are the long-term target; v01 is still the runnable implementation.
