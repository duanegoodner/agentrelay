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
agentrelay dry-run graphs/smoke/quick_chained.yaml
agentrelay run graphs/smoke/quick_chained.yaml --dry-run  # equivalent
```

Run a graph (from the target repo directory):

```bash
agentrelay run graphs/smoke/quick_chained.yaml
agentrelay run graphs/smoke/quick_chained.yaml --target-repo /path/to/repo
```

CLI flags:

| Flag | Description | Default |
|------|-------------|---------|
| `--target-repo PATH` | Path to the target repository | current directory |
| `-d, --dry-run` | Validate and print plan without running | |
| `-c, --max-concurrency N` | Max concurrent tasks | 1 |
| `-a, --max-task-attempts N` | Max attempts per task | 1 |
| `-T, --teardown-mode MODE` | `always`, `never`, or `on_success` | `on_success` |
| `-s, --tmux-session NAME` | Override tmux session name | auto-detected |
| `-m, --model MODEL` | Override model for all agents | per-task default |
| `-C, --credentials PATH` | Path to credentials YAML for sandboxed agents | |
| `-A, --anthropic-credential NAME` | Name of Anthropic credential from credentials YAML | |
| `-W, --fail-fast-workstream` | Stop preparing new workstreams after failure | `false` |
| `-I, --fail-fast-internal` | Stop on internal orchestrator errors | `true` |
| `-k, --keep-panes` | Keep tmux panes open after task completion | `false` |
| `-v, --verbose` | Show detailed step-level output | |

## Preflight Checks

Run preflight checks on a target repository:

```bash
agentrelay check
agentrelay check --target-repo /path/to/repo
agentrelay check --env docker
```

## Resetting a Graph Run

After a run, reset the target repo to its pre-run state:

```bash
agentrelay reset graphs/smoke/quick_chained.yaml
agentrelay reset graphs/smoke/quick_chained.yaml --target-repo /path/to/repo --yes
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
