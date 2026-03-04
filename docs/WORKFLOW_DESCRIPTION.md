# agentrelaysmall — Workflow Description

## Overview

The system has two roles:

- **Orchestrator** — a long-running Python process that manages the task graph,
  dispatches agents, merges PRs, and handles failures.
- **Worktree agent** — a short-lived Claude Code instance launched in an isolated git
  worktree to perform one atomic task. Each agent gets its own worktree and PR.
  TDD workflows (test-writer → reviewer → implementer) are expressed as three plain
  tasks with explicit roles.

All coordination happens through files: a `task_context.json` the orchestrator writes
into each worktree, and signal files that agents and the orchestrator write to
`.workflow/<graph-name>/signals/<task-id>/`.

---

## Directory Layout

```
<repo-root>/
  .workflow/
    <graph-name>/
      run_info.json           # Written at graph start: start HEAD + timestamp
      signals/
        <task-id>/
          .done               # Agent wrote: line 1 = timestamp, line 2 = PR URL
          .merged             # Orchestrator wrote: PR merged into main
          .failed             # Agent wrote: contains reason
          agent.log           # Orchestrator wrote: full tmux pane scrollback
          summary.md          # Orchestrator wrote: agent's PR body

<worktrees-root>/
  <graph-name>/
    <task-id>/                # Git worktree for this task
      task_context.json       # Written by orchestrator before agent launch
      context.md              # Optional: dependency outputs for this task
      <task_id>.md            # TEST_REVIEWER only: review verdict + notes
                              #   e.g. stats_module_review.md
```

Git branches follow the pattern `task/<graph-name>/<task-id>`.

---

## Orchestrator Process

### 1. Startup and hydration

On startup the orchestrator:

1. Loads the task graph from a workflow config file (via `AgentTaskGraphBuilder`).
2. Scans `.workflow/<graph-name>/signals/` and hydrates `TaskState` for each task:

| Signals present | Inferred status |
|---|---|
| `.merged` present | `DONE` — skip entirely |
| `.done` but no `.merged` | PR exists; attempt merge, then mark `DONE` |
| `.failed` present | `FAILED`; needs retry decision |
| No signals | `PENDING` |

3. Calls `_refresh_ready()` to promote any task whose dependencies are all `DONE` to `READY`.

### 2. Dispatch loop

The orchestrator continuously:

1. Calls `_refresh_ready()` to find newly unblocked tasks.
2. Dispatches each `READY` task (creates worktree, opens tmux window, sends prompt).
3. Polls signal directories for terminal signals from running agents.
4. On `.done`: merges PR, writes `.merged`, removes worktree and branch.
5. On `.failed`: logs the failure; the task is not retried automatically.
6. After each merge: calls `_refresh_ready()` — downstream tasks may now be unblocked.

---

## Per-Task Lifecycle

Every task follows the same lifecycle:

### Dispatch

1. Orchestrator creates git worktree and branch:
   - Path: `<worktrees-root>/<graph-name>/<task-id>/`
   - Branch: `task/<graph-name>/<task-id>`
2. Orchestrator writes `task_context.json` into the worktree root.
3. Orchestrator writes `context.md` into the worktree root (if the task has dependencies
   that produced content).
4. Orchestrator opens a tmux window, launches `claude --dangerously-skip-permissions`.
5. Orchestrator sends a role-specific prompt via `tmux send-keys`.

### Agent execution

The agent runs `WorktreeTaskRunner.from_config()`, does its work, creates a PR,
calls `runner.mark_done(pr_url)`, and exits. On unrecoverable failure it calls
`runner.mark_failed(reason)` and exits.

### Post-completion

1. Orchestrator detects `.done`, reads PR URL from file.
2. Captures tmux pane scrollback to `agent.log`; fetches PR body to `summary.md`.
3. Merges PR into `main` (`gh pr merge --merge`).
4. Writes `.merged` to signal directory.
5. Removes worktree and branch.
6. Calls `_refresh_ready()` — downstream tasks may now be unblocked.

---

## TDD Task Sequence

A TDD feature is expressed as three plain tasks dispatched sequentially.
Each is a full worktree-PR-merge cycle:

```
stats_module_tests  →  stats_module_review  →  stats_module_impl
(TEST_WRITER)          (TEST_REVIEWER)          (IMPLEMENTER)
```

### `TEST_WRITER` agent (`{id}_tests`)

1. Writes pytest tests covering the feature described in `description`.
2. Writes a stub module — function signatures only, bodies `raise NotImplementedError`.
3. Verifies test collection: `pixi run pytest --collect-only` (must pass, no implementation yet).
4. Commits, pushes, creates PR, calls `runner.mark_done(pr_url)`.

### `TEST_REVIEWER` agent (`{id}_review`)

The `_tests` PR has been merged to `main` before this agent starts, so the test files
are present in the worktree.

1. Reads the test files and stub module.
2. Writes `{task_id}.md` (e.g. `stats_module_review.md`) with:
   - `Verdict: APPROVED` or `Verdict: CONCERNS`
   - Coverage assessment
   - Specific comments on individual tests
3. If tests are fundamentally broken: calls `runner.mark_failed(reason)` and stops.
4. Otherwise: commits the review file, pushes, creates PR, calls `runner.mark_done(pr_url)`.

### `IMPLEMENTER` agent (`{id}_impl`)

The `_review` PR has been merged to `main`. The review file is available in the worktree.

1. Reads the test files (from worktree / main).
2. Reads the review file (`{review_task_id}.md`) for guidance.
3. Implements the feature in the stub module (replaces `NotImplementedError` bodies).
4. Runs `pixi run pytest` until all tests pass.
5. Commits, pushes, creates PR, calls `runner.mark_done(pr_url)`.

---

## Worktree Agent Process

Every agent (regardless of role) follows the same startup sequence:

```python
from agentrelaysmall import WorktreeTaskRunner
runner = WorktreeTaskRunner.from_config()   # reads task_context.json
context = runner.get_context()              # reads context.md if present
```

`WorktreeTaskRunner` provides only infrastructure — signal writing, path resolution,
context reading. All reasoning and code writing is done by the agent.

**GENERIC agent sequence:**
1. Read `runner.get_context()` for dependency outputs.
2. Perform the task described in the prompt.
3. `git add -A`, commit, push, `gh pr create`.
4. Call `runner.mark_done(pr_url)` and exit.

**TEST_WRITER agent sequence:**
1. Write pytest tests covering the described feature.
2. Write a stub module (signatures only, bodies `raise NotImplementedError`).
3. Run `pixi run pytest --collect-only` to verify test collection.
4. `git add -A`, commit, push, `gh pr create`.
5. Call `runner.mark_done(pr_url)` and exit.

**TEST_REVIEWER agent sequence:**
1. Read the test files and stub module.
2. Write `{task_id}.md` with verdict, coverage assessment, and comments.
3. If tests are fundamentally broken: `runner.mark_failed(reason)` and exit.
4. `git add {task_id}.md`, commit, push, `gh pr create`.
5. Call `runner.mark_done(pr_url)` and exit.

**IMPLEMENTER agent sequence:**
1. Read the test files and `{group_id}_review.md`.
2. Implement the feature in the stub module.
3. Run `pixi run pytest` until all tests pass.
4. `git add -A`, commit, push, `gh pr create`.
5. Call `runner.mark_done(pr_url)` and exit.
6. If blocked: `runner.mark_failed(reason)` and exit.

---

## Signal File Ownership

Signal files are written by exactly one role — never shared:

| Signal | Written by | Meaning |
|---|---|---|
| `.done` | Agent (worktree) | Task complete; line 2 is the PR URL |
| `.merged` | Orchestrator | PR merged into main |
| `.failed` | Agent (worktree) | Task failed; file contains reason |
| `agent.log` | Orchestrator | Full tmux pane scrollback |
| `summary.md` | Orchestrator | Agent's PR body (fetched before merge) |

---

## Resume Behaviour

Signal directories are **not deleted** after a successful run. They serve as a durable audit log. On re-run:

- **Resume (default)**: orchestrator hydrates state from existing signals; completed tasks are skipped.
- **Fresh run**: delete `.workflow/<graph-name>/` before starting. The pre-dispatch check (test-based verification) still catches tasks whose work is already in `main`, even with no signals.
