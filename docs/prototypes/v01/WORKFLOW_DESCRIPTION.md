# agentrelay v01 — Workflow Description

## Overview

The v01 prototype has two roles:

- **Orchestrator**: Python process that loads a graph, dispatches agents, and merges PRs
- **Worktree agent**: Claude Code process launched in an isolated worktree for one task

Coordination uses files in `.workflow/<graph-name>/signals/<task-id>/`.

---

## Directory Layout

```
<repo-root>/
  .workflow/
    <graph-name>/
      run_info.json
      signals/
        <task-id>/
          .done
          .merged
          .failed
          agent.log
          summary.md

<worktrees-root>/
  <graph-name>/
    <task-id>/
```

Git branches follow `task/<graph-name>/<task-id>`.

---

## Orchestrator Loop (v01)

1. Load graph YAML via `AgentTaskGraphBuilder`
2. Hydrate completed/failed status from signal files
3. Mark dependency-satisfied tasks as `READY`
4. For each ready task:
   - create worktree + branch
   - write task context
   - launch Claude in tmux
   - send role-specific instructions
5. Poll for `.done` or `.failed`
6. On `.done`, merge PR and write `.merged`
7. Remove worktree and refresh readiness

The loop runs with `asyncio` and dispatches ready tasks concurrently.

---

## Task Roles

v01 supports role-specific prompt templates:

- `GENERIC`
- `SPEC_WRITER`
- `TEST_WRITER`
- `TEST_REVIEWER`
- `IMPLEMENTER`
- `MERGER`

A common TDD chain is:

```
<feature>_tests -> <feature>_review -> <feature>_impl
```

Each task is a separate worktree + PR cycle.

---

## Signal Ownership

| Signal | Writer | Meaning |
|---|---|---|
| `.done` | Agent | Task finished; includes PR URL |
| `.failed` | Agent | Task failed; includes reason |
| `.merged` | Orchestrator | PR merged |
| `agent.log` | Orchestrator | Pane transcript |
| `summary.md` | Orchestrator | PR body snapshot |

---

## Tmux Targeting Note

Automation should target tmux panes by `pane_id` (for example `%3`), not by window index.
Window indices can renumber as windows close; `pane_id` remains stable.

---

## Resume Behavior

Signal directories are intentionally durable. Re-running a graph hydrates state from existing signals.
For a fresh run, delete `.workflow/<graph-name>/` first.
