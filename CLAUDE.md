# agentrelaysmall

Multi-agent orchestration system: a Python orchestrator manages a graph of coding
tasks, each executed by a Claude Code instance in its own tmux pane and git worktree.
Each agent commits its work, creates a PR, and signals completion via a sentinel file.
The orchestrator merges PRs in dependency order.

## Commands

| Command | Purpose |
|---|---|
| `pixi run test` | Run full test suite |
| `pixi run typecheck` | Pyright static analysis |
| `pixi run format` | black + isort |
| `pixi run check` | format + typecheck + test (pre-PR verification) |
| `python -m agentrelaysmall.run_graph graphs/<name>.yaml` | Run a task graph |
| `python -m agentrelaysmall.reset_graph graphs/<name>.yaml` | Reset repo to pre-run state |

## Module map

| File | Responsibility |
|---|---|
| `agent_task.py` | `AgentTask`, `AgentRole`, `TaskStatus`, `TaskState` data models |
| `agent_task_graph.py` | `AgentTaskGraph` — all path computation; `AgentTaskGraphBuilder.from_yaml()` (expands `tdd_groups:`) |
| `run_graph.py` | Orchestrator loop — dispatches tasks, polls signals, merges PRs |
| `task_launcher.py` | Low-level infrastructure: worktrees, tmux, signal files, PR operations |
| `worktree_task_runner.py` | Agent-side API — runs inside worktrees, writes signal files |
| `reset_graph.py` | Full graph reset: closes PRs, resets main, deletes branches |

## Signal files

Per-task directory: `.workflow/<graph>/signals/<task-id>/`

| File | Written by | Meaning |
|---|---|---|
| `.done` | Agent | Task complete; line 2 is the PR URL |
| `.failed` | Agent | Task failed; line 2 is the reason |
| `.merged` | Orchestrator | PR merged successfully |
| `agent.log` | Orchestrator | tmux pane scrollback captured after task |
| `summary.md` | Orchestrator | PR body fetched before merge |

Graph-level: `.workflow/<graph>/run_info.json` — start HEAD + timestamp (for reset).

## Graph YAML

```yaml
name: my-graph
tmux_session: agentrelaysmall  # optional; default "agentrelaysmall"
keep_panes: false              # optional; leave tmux windows open for debugging
model: claude-sonnet-4-6       # optional; graph-level default model for all agents
tasks:                         # optional; plain tasks (one agent each)
  - id: my_task
    description: "..."
    model: claude-haiku-4-5-20251001  # optional; overrides graph-level model for this task
    dependencies: []
tdd_groups:                    # optional; each expands to 3 tasks: _tests, _review, _impl
  - id: my_feature
    description: "..."
    model: claude-sonnet-4-6   # optional; group default (applies to all 3 sub-tasks)
    models:                    # optional; per-role overrides
      tests: claude-haiku-4-5-20251001
      review: claude-haiku-4-5-20251001
      impl: claude-opus-4-6
    dependencies: []           # group IDs resolve to {id}_impl; plain task IDs pass through
```

## Development workflow

When making changes to agentrelaysmall itself:

1. **Create a feature branch** — `git checkout -b feat/<short-name>`
2. **Make changes** — edit source, tests, or docs
3. **Verify** — `pixi run check` (format + typecheck + test) must pass
4. **Commit** — `git add <files> && git commit -m "type: description"`
5. **Push** — `git push -u origin feat/<short-name>`
6. **Open PR** — `gh pr create` with a `## Summary` and `## Test plan` checklist
7. **Iterate** — address review feedback; `pixi run check` after each change
8. **Merge** — `gh pr merge <url> --merge` once the human approves

Rules:
- Never commit directly to `main`
- Always run `pixi run check` before creating a PR
- PR body must include a `## Test plan` checklist (automated + human-verifiable items)
- Update `docs/HISTORY.md` with a new entry for each merged PR

## Docs

- `docs/PROJECT_DESCRIPTION.md` — what this is
- `docs/DESIGN_DECISIONS.md` — why things are the way they are
- `docs/WORKFLOW_DESCRIPTION.md` — end-to-end workflow specification
- `docs/REPO_SETUP.md` — setting up a new target repo
- `docs/OPERATIONS.md` — day-to-day running guide
- `docs/HISTORY.md` — feature history (one entry per PR)
- `docs/BACKLOG.md` — ideas and future work (add here, don't interrupt current task)
