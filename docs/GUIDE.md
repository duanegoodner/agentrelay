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

## Current Architecture Smoke Check

Validate one of the checked-in TaskGraph schema examples:

```bash
pixi run python -c "from pathlib import Path; from agentrelay.task_graph import TaskGraphBuilder; g = TaskGraphBuilder.from_yaml(Path('docs/examples/workstreams.yaml')); print(g.name, g.task_ids())"
```

Schema and migration references:

- [Task Graph Schema](SCHEMA.md)
- [Migration Guide](MIGRATION.md)

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
