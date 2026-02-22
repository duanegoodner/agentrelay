# agentrelay

Lightweight, declarative workflow framework for multi-agent Claude Code pipelines.

## Project overview

This is an exploratory project studying multi-agent coordination patterns. The framework
describes and executes pipelines where multiple Claude Code agents collaborate on tasks
through a sequence of Steps connected by Gates (verification checkpoints).

## Repository layout

- `src/agentrelay/` — Python package (the orchestrator framework)
- `tests/` — pytest tests for the framework
- `experiments/` — one subdirectory per experiment (01-manual through 07-agent-orchestrator)
- `.workflow/specs/` — YAML workflow definitions (version controlled)
- `.workflow/{signals,retry-context,state,audit}/` — runtime state (gitignored)
- `docs/` — planning and design documents

## Bare repo + worktree setup

This repo uses a bare-repo + linked-worktree pattern:

```
/data/git/agentrelay/
├── .git-bare/     # bare repo — all git objects, remote origin
├── .claude/       # Claude Code project settings
└── main/          # linked worktree on `main` branch
```

**Inside a worktree:** Normal `git` commands work as usual.

**Repo-level commands** (from `/data/git/agentrelay/`):

```bash
GIT_DIR=/data/git/agentrelay/.git-bare git worktree list
GIT_DIR=/data/git/agentrelay/.git-bare git worktree add /data/git/agentrelay/<name> -b <branch>
GIT_DIR=/data/git/agentrelay/.git-bare git worktree remove /data/git/agentrelay/<name>
```

## Environment

- **Python**: managed by pixi (pyproject.toml)
- **Run tests**: `pixi run pytest`
- **Run the orchestrator**: `pixi run python -m agentrelay <command>`

## Development workflow

### Branching rules

- **Never commit directly to main.** All changes go through PRs. Branch protection enforces this server-side; a pre-push hook enforces it locally.
- **Default: feature branch in `main/`.** For most work, create a branch, make changes, push, open a PR, merge, pull.
- **Create a new worktree only when:**
  - Two or more tasks are genuinely in progress simultaneously
  - Handing off a branch to a dedicated Claude Code instance that shouldn't switch branches
  - A long-running task should not block `main/` from staying on the main branch

### Feature branch flow (in main/)

```bash
git checkout -b <branch-name>
# ... make changes, commit ...
git push -u origin <branch-name>
gh pr create --title "..." --body "..."
# after review/merge on GitHub:
git checkout main
git pull origin main
git branch -d <branch-name>
```

### Worktree flow (parallel work)

```bash
# Create worktree (from repo root, not inside a worktree)
GIT_DIR=/data/git/agentrelay/.git-bare git worktree add /data/git/agentrelay/<name> -b <branch-name>
cd /data/git/agentrelay/<name>
# ... make changes, commit ...
git push -u origin <branch-name>
gh pr create
# after merge:
GIT_DIR=/data/git/agentrelay/.git-bare git worktree remove /data/git/agentrelay/<name>
cd /data/git/agentrelay/main && git pull origin main
```

### PR conventions

- One logical change per PR — keep PRs focused
- PR title: short imperative, under 70 chars
- PR body: summary bullets + test plan
- Merge strategy: squash merge (keeps main history clean)

## Key documents

- `docs/PROJECT_PLAN.md` — project plan, vocabulary, and experiment roadmap
- `docs/DECISIONS.md` — design rationale for key choices (name, format, layout, tooling)
- `docs/AGENT_WORKFLOWS_KNOWLEDGE_CAPTURE.md` — background research on multi-agent patterns

## Key conventions

- Workflow specs are YAML files in `.workflow/specs/`
- Each experiment lives in `experiments/<NN>-<name>/` with its own README and spec files
- Tests use pytest; run with `pixi run pytest`
- Keep task content trivial in experiments — the focus is workflow mechanics, not the work itself
