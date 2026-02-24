# agentrelaysmall — Workflow Description

## Overview

The system has two roles:

- **Orchestrator** — a long-running process (human-assisted Claude Code instance or a Python script) that manages the task graph, dispatches agents, reviews test output, merges PRs, and handles failures.
- **Worktree agent** — a short-lived Claude Code instance launched in an isolated git worktree to perform one task. Each task produces two agents: one for the test-writing phase, one for the implementation phase.

All coordination between roles happens through files: a `task_context.json` the orchestrator writes into the worktree, and signal files the orchestrator and agents write to `.workflow/<graph-name>/signals/<task-id>/`.

---

## Directory Layout

```
<repo-root>/
  .workflow/
    <graph-name>/
      signals/
        <task-id>/
          .tests-written      # Agent 1 wrote: test phase complete
          .tests-approved     # Orchestrator wrote: approved, launching Agent 2
          .done               # Agent 2 wrote: contains PR URL
          .merged             # Orchestrator wrote: PR merged into main
          .failed             # Agent wrote: contains reason
          .needs-human        # Orchestrator wrote: escalation required

<worktrees-root>/
  <graph-name>/
    <task-id>/                # Git worktree for this task
      task_context.json       # Written by orchestrator before agent launch
      context.md              # Optional: dependency outputs for this task
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
| `.tests-approved` but no `.done`/`.failed` | Agent 2 was killed mid-run; re-dispatch implementer |
| `.tests-written` but no `.tests-approved` | Agent 1 finished; re-run test review, then decide |
| `.failed` present | `FAILED`; needs retry decision |
| `.in-progress`, no terminal signal | Process killed unexpectedly; treat as `FAILED` |
| No signals | `PENDING` |

3. Calls `_refresh_ready()` to promote any task whose dependencies are all `DONE` to `READY`.

### 2. Dispatch loop

The orchestrator continuously:

1. Calls `_refresh_ready()` to find newly unblocked tasks.
2. For each `READY` task, runs the **pre-dispatch check** (see below).
3. Dispatches any task that passes the pre-dispatch check.
4. Polls signal directories for terminal signals from running agents.
5. On `.done`: reviews PR (or auto-merges), writes `.merged`, removes worktree and branch.
6. On `.failed` or timeout: decides to retry, escalate, or abort.

### 3. Pre-dispatch check

Before creating a worktree or launching any agent, the orchestrator checks whether the task is already complete:

```
Does a test file for this task exist in main?
│
├─ No → proceed to dispatch (fresh task)
│
└─ Yes → run structural check (pytest --collect-only)
    │
    ├─ Fails → tests malformed → write .needs-human, escalate
    │
    └─ Passes → run the tests
        │
        ├─ Tests PASS → task already done
        │               write .done + .merged in signals, skip dispatch
        │
        └─ Tests FAIL → consult signals + git to determine phase
            ├─ .failed exists          → retry; dispatch Agent 2 with failure context
            ├─ .tests-approved exists  → Agent 2 was killed; re-dispatch implementer
            ├─ .tests-written exists   → re-run orchestrator test review
            └─ No signals at all       → orphan tests; write .needs-human, escalate
```

---

## Per-Task Lifecycle

### Phase 1: Test-writing

1. Orchestrator creates git worktree and branch:
   - Path: `<worktrees-root>/<graph-name>/<task-id>/`
   - Branch: `task/<graph-name>/<task-id>`
2. Orchestrator writes `task_context.json` into the worktree root.
3. Orchestrator opens a tmux window, launches `claude` interactively.
4. Orchestrator sends the **test-writing prompt** via `tmux send-keys`.
5. Agent 1 runs `WorktreeTaskRunner.from_config()`, writes tests, calls `runner.mark_tests_written()`, and exits.

### Orchestrator test review

1. Orchestrator detects `.tests-written`.
2. Runs structural check (`pytest --collect-only`).
3. If automated: runs semantic check (LLM review of tests against task description).
4. If approved: writes `.tests-approved`, proceeds to Phase 2.
5. If rejected: writes `.needs-human` with reason; halts this task.

### Phase 2: Implementation

1. Orchestrator launches a **new** Claude Code instance in the **same worktree**.
2. Sends the **implementation prompt** via `tmux send-keys`.
3. Agent 2 runs `WorktreeTaskRunner.from_config()`, implements until tests pass, creates a PR, calls `runner.mark_done(pr_url)`, and exits.
4. On failure: Agent 2 calls `runner.mark_failed(reason)` and exits.

### Post-completion

1. Orchestrator detects `.done`, reads PR URL from file.
2. Merges PR into `main`.
3. Writes `.merged` to signal directory.
4. Removes worktree (`git worktree remove`).
5. Deletes branch (`git branch -d`).
6. Calls `_refresh_ready()` — downstream tasks may now be unblocked.

---

## Worktree Agent Process

Each agent (test-writer or implementer) follows the same startup sequence:

```python
from agentrelaysmall import WorktreeTaskRunner
runner = WorktreeTaskRunner.from_config()   # reads task_context.json
context = runner.get_context()              # reads context.md if present
```

`WorktreeTaskRunner` provides only infrastructure — signal writing, path resolution, context reading. All reasoning and code writing is done by the agent.

**Agent 1 (test-writer) sequence:**
1. Read `runner.get_context()` for dependency outputs.
2. Write tests that define what task completion looks like.
3. Call `runner.mark_tests_written()` and exit.

**Agent 2 (implementer) sequence:**
1. Read `runner.get_context()` for dependency outputs.
2. Implement code until `pytest` passes.
3. Create a PR.
4. Call `runner.mark_done(pr_url)` and exit.
5. If blocked: call `runner.mark_failed(reason)` and exit.

---

## Signal File Ownership

Signal files are written by exactly one role — never shared:

| Signal | Written by | Meaning |
|---|---|---|
| `.tests-written` | Agent (worktree) | Test phase complete |
| `.tests-approved` | Orchestrator | Tests reviewed and approved |
| `.done` | Agent (worktree) | Implementation complete, PR created |
| `.merged` | Orchestrator | PR merged into main |
| `.failed` | Agent (worktree) | Task failed; file contains reason |
| `.needs-human` | Orchestrator | Escalation required; file contains context |

---

## Resume Behaviour

Signal directories are **not deleted** after a successful run. They serve as a durable audit log. On re-run:

- **Resume (default)**: orchestrator hydrates state from existing signals; completed tasks are skipped.
- **Fresh run**: delete `.workflow/<graph-name>/` before starting. The pre-dispatch check (test-based verification) still catches tasks whose work is already in `main`, even with no signals.
