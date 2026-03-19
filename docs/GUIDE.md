# Guide

## Prerequisites

- Python 3.12+
- `pixi` (https://pixi.sh)
- `git` with worktree support
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
pixi run test          # run test suite
pixi run typecheck     # pyright static analysis
pixi run format        # black + isort
pixi run check         # format + typecheck + test
pixi run diagram       # render D2 diagrams
pixi run docs          # serve mkdocs locally
```

## Running a Graph

Validate a graph without running it:

```bash
pixi run python -m agentrelay.run_graph graphs/smoke/quick_chained.yaml --dry-run
```

Run a graph (from the target repo directory):

```bash
python -m agentrelay.run_graph /path/to/graphs/smoke/quick_chained.yaml
```

CLI flags:

| Flag | Description | Default |
|------|-------------|---------|
| `--dry-run` | Validate and print plan without running | |
| `--max-concurrency N` | Max concurrent task attempts | 1 |
| `--max-task-attempts N` | Max attempts per task | 1 |
| `--teardown-mode MODE` | `always`, `never`, or `on_success` | `on_success` |
| `--tmux-session NAME` | Override tmux session name | `agentrelay` |
| `--model MODEL` | Override model for all agents | per-task default |

## Resetting a Graph Run

After a run, reset the target repo to its pre-run state:

```bash
python -m agentrelay.reset_graph /path/to/graphs/smoke/quick_chained.yaml
python -m agentrelay.reset_graph /path/to/graphs/smoke/quick_chained.yaml --yes  # skip prompt
```

This closes open PRs, resets main to the starting HEAD, deletes graph branches,
and removes `.workflow/` and `.worktrees/` directories for the graph.

## E2E Testing Against a Target Repo

agentrelay ships test graphs in `graphs/` (organized by category) and helper
scripts for running them against an external "testing ground" repository
(e.g. `agentrelaydemos`).

Preflight check on a target repo:

```bash
pixi run e2e-check /path/to/target-repo
```

Run a graph in the target repo:

```bash
pixi run e2e graphs/smoke/quick_parallel.yaml /path/to/target-repo
pixi run e2e graphs/smoke/quick_chained.yaml /path/to/target-repo --dry-run
```

Reset a graph run in the target repo:

```bash
pixi run e2e-reset graphs/smoke/quick_parallel.yaml /path/to/target-repo
```

## Schema References

- [Task Graph Schema](SCHEMA.md)

## Prototype v01 (Legacy)

The v01 prototype is retained as a reference implementation. For new work, use
the commands above.

```bash
pixi run python -m agentrelay.prototypes.v01.run_graph graphs/<name>.yaml
pixi run python -m agentrelay.prototypes.v01.reset_graph graphs/<name>.yaml --yes
```

## Notes

- Prefer `pixi run <task>` over ad-hoc local environments.
- Run `pixi run check` before every PR.
