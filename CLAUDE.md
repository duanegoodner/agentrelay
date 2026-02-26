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
| `agent_task.py` | `AgentTask`, `TaskStatus`, `TaskState` data models |
| `agent_task_graph.py` | `AgentTaskGraph` — all path computation; `AgentTaskGraphBuilder.from_yaml()` |
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
tasks:
  - id: my_task
    description: "..."
    dependencies: []
```

## Docs

- `docs/PROJECT_DESCRIPTION.md` — what this is
- `docs/DESIGN_DECISIONS.md` — why things are the way they are
- `docs/WORKFLOW_DESCRIPTION.md` — end-to-end workflow specification
- `docs/REPO_SETUP.md` — setting up a new target repo
- `docs/OPERATIONS.md` — day-to-day running guide
- `docs/HISTORY.md` — feature history (one entry per PR)
