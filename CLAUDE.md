# agentrelay

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
| `python -m agentrelay.run_graph graphs/<name>.yaml` | Run a task graph |
| `python -m agentrelay.reset_graph graphs/<name>.yaml` | Reset repo to pre-run state |

## Module map

| File | Responsibility |
|---|---|
| `agent_task.py` | `AgentTask`, `AgentRole`, `TaskStatus`, `TaskState` data models |
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
tmux_session: agentrelay  # optional; default "agentrelay"
keep_panes: false              # optional; leave tmux windows open for debugging
model: claude-sonnet-4-6       # optional; graph-level default model for all agents
tasks:
  - id: my_task
    description: "..."
    role: generic              # optional; generic | test_writer | test_reviewer | implementer | spec_writer | merger
    model: claude-haiku-4-5-20251001  # optional; overrides graph-level model for this task
    paths:                     # optional; all sub-keys optional
      src:                     # list of source files (used by spec_writer, test_writer, implementer)
        - src/my_module.py
      test:                    # list of test files (used by test_writer, implementer)
        - tests/test_my_module.py
      spec: specs/my_spec.md   # supplementary spec file path (used by spec_writer, generic)
    dependencies: []
```

## Development workflow

When making changes to agentrelay itself:

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
- Update `docs/DIAGRAM.md` in every PR that touches `src/agentrelay/`; if the design
  did not change, add a note at the bottom of DIAGRAM.md confirming this — the file
  must still change so that diagram review is an explicit step in every PR

## Coding conventions

**No free functions.** If something could be a module-level function, make it a
`@staticmethod` in a class instead. When a class exists solely as a container of static
methods (no state, no `__init__`), it is intentionally stateless — a named namespace for
related operations.

Rationale: agentrelay uses Mermaid for design diagrams because Mermaid renders natively
in GitHub and VS Code without an export step, keeping diagrams alive rather than stale.
Mermaid's `classDiagram` cannot represent free functions. Rather than work around this
limitation with workarounds that obscure design, we eliminate free functions entirely.
Clean diagrammability is a forcing function for clean architecture: every module has an
explicit, nameable surface that appears in the diagram.

## Docs

- `docs/DIAGRAM.md` — authoritative design diagram (Mermaid); updated every PR
- `docs/ARCHITECTURE.md` — module map, design principles, extensibility notes
- `docs/WORKFLOW.md` — end-to-end workflow specification
- `docs/GUIDE.md` — installation, repo setup, development workflow
- `docs/HISTORY.md` — feature history (one entry per PR)
- `docs/BACKLOG.md` — ideas and future work (add here, don't interrupt current task)
