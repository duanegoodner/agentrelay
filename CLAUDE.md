# agentorch

Lightweight, declarative workflow framework for multi-agent Claude Code pipelines.

## Project overview

This is an exploratory project studying multi-agent coordination patterns. The framework
describes and executes pipelines where multiple Claude Code agents collaborate on tasks
through a sequence of Steps connected by Gates (verification checkpoints).

## Repository layout

- `agentorch/` — Python package (the orchestrator framework)
- `tests/` — pytest tests for the framework
- `experiments/` — one subdirectory per experiment (01-manual through 07-agent-orchestrator)
- `.workflow/specs/` — YAML workflow definitions (version controlled)
- `.workflow/{signals,retry-context,state,audit}/` — runtime state (gitignored)
- `docs/` — planning and design documents

## Bare repo + worktree setup

This repo uses a bare-repo + linked-worktree pattern:

```
/data/git/agentorch/
├── .git-bare/     # bare repo — all git objects, remote origin
├── .claude/       # Claude Code project settings
└── main/          # linked worktree on `main` branch
```

**Inside a worktree:** Normal `git` commands work as usual.

**Repo-level commands** (from `/data/git/agentorch/`):

```bash
GIT_DIR=/data/git/agentorch/.git-bare git worktree list
GIT_DIR=/data/git/agentorch/.git-bare git worktree add /data/git/agentorch/<name> -b <branch>
GIT_DIR=/data/git/agentorch/.git-bare git worktree remove /data/git/agentorch/<name>
```

## Environment

- **Python**: managed by pixi (pyproject.toml)
- **Run tests**: `pixi run pytest`
- **Run the orchestrator**: `pixi run python -m agentorch <command>`

## Key conventions

- Workflow specs are YAML files in `.workflow/specs/`
- Each experiment lives in `experiments/<NN>-<name>/` with its own README and spec files
- Tests use pytest; run with `pixi run pytest`
- Keep task content trivial in experiments — the focus is workflow mechanics, not the work itself
