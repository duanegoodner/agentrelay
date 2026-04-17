# Sprint Plan — 2026-04-12: Graph Resumption (MVP)

> **Status: In progress.** PR A (#191), PR B (#192), PR B2 (#193), PR C (#194), and PR D (#196) merged.

## Goal

When a graph is re-launched and `.workflow/<graph>/` already exists,
probe the actual state on disk and resume instead of refusing. Completed
tasks skip, failed tasks retry, unstarted tasks proceed. Users can also
force a fresh restart that preserves previous run history, and
selectively undo tasks, workstream infrastructure, or workstream merges
using a uniform stack-based undo model.

This is Phase 4 of the pre-Rust roadmap — the highest-value user-facing
improvement before the Python feature freeze.

## Context

Sprint 2026-04-09 completed Phase 3 — 1467 tests, all 21 e2e graphs
pass, uniform per-attempt signal directories, run_config.json. The
signal file architecture (status derived from disk, per-attempt artifact
directories) was designed with resumption in mind.

**Key existing building blocks:**
- `_read_task_status_from_signals()` and `_read_status_from_signals()`
  already derive task/workstream status from signal files on disk.
- `Orchestrator.run()` accepts optional pre-built `task_runtimes` and
  `workstream_runtimes` — the init path already handles pre-existing
  completed tasks, failed-task-retry normalization, and workstream state
  refresh.
- `_initialize_attempts_used()` computes attempt counts from runtime
  state. `_normalize_failed_for_retry()` converts FAILED→PENDING when
  retries remain.
- The orchestrator only calls `workstream_runner.prepare()` when a
  workstream is PENDING, and only dispatches PENDING tasks — so
  reconstructing runtimes with the right status causes completed work to
  be skipped automatically.

**What currently blocks re-runs:** `_check_for_conflicts()` in
`run_graph.py:225-244` checks for `.workflow/<graph>/` or
`.worktrees/<graph>/` and raises `_ConflictError`, directing the user to
run `agentrelay reset`.

**The gap:** No code exists to reconstruct `TaskRuntime` /
`WorkstreamRuntime` objects from on-disk state, and no logic handles
"stale" in-progress states (RUNNING / PR_CREATED) from a prior
orchestrator session that was interrupted.

## Design decisions

### Per-run directories

Each invocation of `agentrelay run` creates a numbered run directory
under `.workflow/<graph>/runs/<N>/`. This mirrors the per-attempt
pattern already used for tasks.

```
.workflow/<graph>/
├── runs/
│   ├── 0/
│   │   ├── signals/<task-id>/
│   │   │   ├── status/
│   │   │   ├── attempts/<N>/
│   │   │   ├── manifest.json
│   │   │   ├── resolved.json      ← written on task completion
│   │   │   └── ...
│   │   ├── workstreams/<ws-id>/
│   │   │   ├── pending
│   │   │   ├── active
│   │   │   ├── ...
│   │   │   └── resolved.json      ← written on workstream merge
│   │   ├── run_info.json
│   │   ├── run_config.json
│   │   └── graph.yaml
│   └── 1/
│       └── ...
```

**Why per-run directories:**
- **Fresh restart is clean.** `--force-fresh` increments the run number.
  Previous runs are intact and inspectable — no decision about what to
  delete vs. preserve.
- **Graph modification is tractable.** Each run has its frozen
  `graph.yaml`. We validate that completed tasks from run N still exist
  with compatible definitions in run N+1's graph.
- **History is preserved.** Compare runs, debug regressions, inspect
  what an agent did in run 0 vs. run 1.
- **Consistent with per-attempt pattern.** The codebase already uses
  numbered subdirectories for task attempts. Per-run directories apply
  the same principle one level up.

**Worktrees are NOT per-run.** Worktrees at `.worktrees/<graph>/<ws-id>`
are ephemeral infrastructure. On resume (same run), they are reused
as-is. On fresh restart (new run), stale worktrees/branches are cleaned
up — a subset of what `reset_graph.py` does, without resetting main to
start_head.

**Path plumbing impact:** Code that currently computes paths from
`.workflow/<graph>/` changes to `.workflow/<graph>/runs/<N>/`. The
touchpoints are concentrated in ~6 places that construct the root
directory. Internal structure within a run is identical. Most code
already receives `signal_dir` or computed paths, so the change is
localized.

### Definition graph vs. execution graph

Two views of the graph coexist:

- **Definition graph** — what `graph.yaml` + CLI resolution produces.
  This is the *plan*.
- **Execution graph** — what actually happened. This is a *logical view*
  reconstructed from per-task artifacts (`resolved.json`, status
  signals, `.done` files). It is never serialized as a single file.

When a fresh run starts, the execution graph is empty and the definition
graph drives everything. As tasks complete, they become frozen facts in
the execution graph. On resume, the execution graph is the starting
point — completed tasks use their recorded state, pending tasks use the
current definition graph.

**The execution graph always wins.** Completed tasks use `resolved.json`
unconditionally. The current YAML/CLI resolution for those tasks is
irrelevant — it is never consulted for scheduling, instruction
generation, or anything else. If the current YAML differs from what
actually ran, the user sees an informational override report, but the
system proceeds using the frozen values. This is not an error — the
user can update their YAML to match reality or leave it.

The only genuine error is a completed task ID *missing* from the current
graph, because the orchestrator's DAG needs the node for dependency
resolution.

### Frozen records

Two levels of frozen records capture the execution graph:

#### Task-level: `resolved.json` in signal directory

Written when a task reaches a terminal success state (PR_MERGED or
COMPLETED):

```json
{
  "task_id": "write_tests",
  "workstream_id": "ws-main",
  "dependencies": ["write_spec"],
  "inputs_from": [{"task": "write_spec", "category": "stubs"}],
  "role": "test_writer",
  "model": "claude-sonnet-4-6",
  "tagged_paths": [{"path": "tests/test_foo.py", "category": "test"}],
  "branch_name": "agentrelay/my-graph/write_tests",
  "integration_branch": "agentrelay/my-graph/ws-main/integration",
  "integration_branch_before_merge": "abc123",
  "completed_at_attempt": 0,
  "pr_url": "https://github.com/..."
}
```

`integration_branch_before_merge` records the integration branch commit
SHA just before the task's PR was merged. Enables `reset-task` to
cleanly roll back the integration branch without commit archaeology.

#### Workstream-level: `resolved.json` in workstream signal directory

Written when a workstream's integration PR is merged into its target
branch (typically `main`):

```json
{
  "workstream_id": "ws-1",
  "integration_pr_url": "https://github.com/...",
  "target_branch": "main",
  "target_branch_before_merge": "def456",
  "merged_at": "2026-04-12T14:30:00Z"
}
```

`target_branch_before_merge` records the target branch (usually `main`)
commit SHA just before the integration PR was merged. Enables
`reset-workstream` to cleanly roll back the target branch without commit
archaeology.

**Why `resolved.json` and not just `manifest.json`:** `manifest.json` is
oriented toward agent instructions (dependency descriptions, tool lists).
`resolved.json` captures the orchestration-relevant attributes needed to
validate and reconstruct the execution graph, plus the pre-merge SHAs
needed for stack-based undo.

### Frozen task validation

On resume, completed tasks are validated against the current definition
graph:

1. **Task ID must exist** in the current graph. A completed task that
   has been removed is an error — its node is needed for DAG dependency
   resolution.
2. **Attribute differences produce an informational override report**,
   not an error. The execution graph wins unconditionally — the frozen
   `resolved.json` values are used for the completed task regardless of
   what the current YAML says.

Override report (printed only when differences exist):

```
Frozen task overrides (current YAML/CLI differs from executed values):

  write_spec:
    model: claude-sonnet-4-6 (current: claude-opus-4-6)
    description: changed (frozen value preserved)

  write_tests:
    role: test_writer (current: generic)
```

This report serves as a safety check — the user sees exactly what's
being overridden and can choose to accept it, update their YAML to
match, or use `reset-task` / `agentrelay reset` to undo completed
work and re-run with different settings.

The comparison is a pure function: resolve the current graph, load
`resolved.json` for each frozen task, diff per-attribute, produce a
list of overrides for the console to format.

**Pending/failed tasks are free to change.** New tasks can be added,
pending tasks can have any attribute modified, failed tasks can be
reconfigured. Only completed (frozen) tasks use their recorded values.

### Worktree preservation for mid-workstream resume

Worktrees must be preserved during resume because they contain the
execution state for in-progress workstreams. Concretely:

For a workstream with A → B → C where A completed and B failed:
- The worktree contains the integration branch with A's merged code
- B's task branch may have WIP commits (pushed or unpushed)
- Deleting the worktree would lose B's unpushed work
- The existing retry logic in `WorktreeTaskPreparer` (force-create
  branch) preserves the agent's prior commits so they can fix their
  code — this only works if the worktree survives

| Run mode | Worktree handling |
|---|---|
| Resume (same run) | Reused as-is. Idempotent preparer skips creation. |
| Force-fresh (new run) | Cleaned up (branches deleted, worktrees removed). New worktrees created from current base. |
| Fresh (no prior run) | Normal creation. |

### Stale state normalization

When the orchestrator is interrupted, some tasks may be left in
transient states (RUNNING, PR_CREATED) that don't reflect reality.
These must be normalized before the orchestrator can resume:

**RUNNING tasks** — the agent process is dead (orchestrator restarted).
Check the current attempt directory for agent completion signals:
1. `.done` exists → agent finished. Read line 2 for PR URL. Write
   `pr_created` or `completed` status signal.
2. `.failed` exists → agent reported failure. Write `failed` status
   signal.
3. Neither exists → agent was killed mid-run. Write `failed` status
   signal.

After normalization, no task remains in RUNNING state.

**PR_CREATED tasks** — the task PR was created but the orchestrator
didn't get to merge it. Check PR status:
1. PR already merged (manually or by CI) → write `pr_merged` signal.
2. PR still open → attempt `gh pr merge`. If success → write
   `pr_merged` signal. If merge fails → write `failed` signal (retry
   will preserve the agent's prior commits via the existing
   force-create-branch logic in `WorktreeTaskPreparer`).

After normalization, no task remains in PR_CREATED state. The
orchestrator's existing init code
(`_initialize_attempts_used()` at orchestrator.py:310-323) then handles
all remaining states without changes.

### Workstream state follows from task state

Workstreams don't need independent normalization. The orchestrator's
`_refresh_workstream_terminal_states()` and
`_process_merge_ready_workstreams()` already recompute workstream state
from task states during init. We reconstruct workstream runtimes with
their on-disk signal state, and the orchestrator's init path handles
the rest.

One edge case: **workstream PR_CREATED** — the integration PR was
created but the orchestrator died before detecting its merge. This is
handled by the existing `_poll_integration_merges()` in the main loop,
which checks open integration PRs and writes merge sentinels. No new
code needed.

### Config compatibility

On resume, the previous run's `run_config.json` exists. The MVP
approach:
- Load and log the previous config for the user.
- If current CLI flags differ from the previous config on key fields
  (`max_concurrency`, `max_task_attempts`, `sandbox`), emit a warning
  but proceed. The current session's config wins.
- `run_info.json` is not rewritten (preserves the original start HEAD
  for reset).
- `run_config.json` is updated to reflect the current session's config.

### Resume summary table

On resume, the console prints a status table before the orchestrator
starts:

```
Resuming graph 'my-graph' (run 0)

  Task            Status     Action
  ─────────────── ────────── ──────────────────
  write_spec      completed  skipping (frozen)
  write_tests     completed  skipping (frozen)
  write_impl      failed     retrying (attempt 2/3)
  review          pending    starting
```

The word "frozen" signals that the task is locked — not just skipped.

On a fresh restart (new run number), the table also appears but with
context:

```
Starting graph 'my-graph' (run 1, previous run: 0)

  Task            Previous   Action
  ─────────────── ────────── ──────────────────
  write_spec      completed  skipping (frozen from run 0)
  write_tests     completed  skipping (frozen from run 0)
  write_impl      failed     starting fresh
  review          pending    starting fresh
  new_task        (new)      starting fresh
```

### Stack-based undo model

The same stack-based undo pattern applies at three levels of the
execution hierarchy. At each level, work is merged sequentially into a
target branch, forming a stack. Undo can only peel from the tip.

| Level | Stack of merges into | Peel command | Pre-merge SHA field |
|---|---|---|---|
| Task | Integration branch | `reset-task` | `integration_branch_before_merge` in task `resolved.json` |
| Workstream | Target branch (main) | `reset-workstream` | `target_branch_before_merge` in workstream `resolved.json` |
| Graph | Everything | `agentrelay reset` | `start_head` in `run_info.json` |

Additionally, `teardown-workstream` removes workstream infrastructure
(worktree, integration branch) without touching the target branch.
This is not an undo operation — it's infrastructure cleanup for
workstreams that have had all their tasks peeled back.

The stack model defines which states are safe to reach. But it does not
constrain the execution model — once a target state is validated as
reachable, the system can jump directly to it rather than popping
sequentially. See `reset-to` below.

#### `reset-task`

```
agentrelay reset-task <graph.yaml> --task <task-id>
agentrelay reset-task <graph.yaml> --workstream <ws-id>   # auto-detect tip
```

Resets the most recently touched task in its workstream — peeling back
execution state from the tip of the workstream's execution stack.

**Stack-based undo model.** Within a workstream, tasks execute strictly
one at a time (enforced by the existing `_workstream_can_run()`
serialization logic). This means the execution history is a stack, and
`reset-task` can only peel from the tip.

If `--task` is provided, validates that the given task is the tip —
errors with guidance if it isn't. If `--workstream` is provided
instead, auto-detects the tip task in that workstream. One of the two
must be specified — in a multi-workstream graph, the tip is ambiguous
without knowing which workstream.

**For a non-merged task** (FAILED, RUNNING, or stale PR_CREATED):
1. Delete the task's signal directory
2. Delete the task's remote and local branches
3. Switch worktree back to the integration branch (if task branch was
   checked out)

**For a merged task** (PR_MERGED or COMPLETED):
1. Reset the integration branch to `integration_branch_before_merge`
   from `resolved.json` (safe because the stack constraint guarantees
   nothing was merged after this task)
2. Force-push the integration branch
3. Delete the task's signal directory
4. Delete the task's remote and local branches

After reset, the task has no signal dir → probe treats it as PENDING.
Re-running the graph gives a clean start on that task.

**Successive resets** peel back the workstream one task at a time:
```bash
agentrelay reset-task my-graph.yaml --task task-c   # C was failed
agentrelay reset-task my-graph.yaml --task task-b   # B was merged
agentrelay reset-task my-graph.yaml --task task-a   # A was merged
```

After all tasks are peeled, the integration branch is back at its
original branch point (wherever `base_branch` was when the workstream
was first prepared). Workstream infrastructure (worktree, integration
branch) remains in place. Re-running gives a clean start on Task A
using the existing infrastructure.

**Note on base branch staleness:** If `main` has moved since the
workstream was first prepared, the integration branch's base is stale.
For a quick retry this is fine. For a full redo with fresh `main`, use
`teardown-workstream` after peeling all tasks to rebuild infrastructure
from current `main`.

#### `teardown-workstream`

```
agentrelay teardown-workstream <graph.yaml> --workstream <ws-id>
```

Removes workstream infrastructure — worktree, integration branch,
workstream signal directory. This is infrastructure cleanup, not an
undo of merged work. Only valid when all tasks in the workstream have
been peeled back (no task has a signal directory). Errors with guidance
if any task still has state.

**Operation:**
1. Validate precondition: all tasks in the workstream have no signal
   dirs (all peeled back via `reset-task`). Error if any task still has
   state.
2. Remove the worktree (`git worktree remove .worktrees/<graph>/<ws-id>`)
3. Delete the integration branch (local + remote)
4. Delete the workstream signal directory
5. Prune stale git worktree refs

After this, the workstream is back to PENDING (no signal dir → probe
returns PENDING). On next `agentrelay run`, `GitWorkstreamPreparer`
creates a fresh worktree and integration branch off current `main`.

**Typical workflow for full workstream redo with fresh base:**
```bash
# Peel back all tasks
agentrelay reset-task my-graph.yaml --task task-c
agentrelay reset-task my-graph.yaml --task task-b
agentrelay reset-task my-graph.yaml --task task-a

# Wipe infrastructure to get fresh main
agentrelay teardown-workstream my-graph.yaml --workstream ws-1

# Re-run — fresh worktree off current main
agentrelay run my-graph.yaml
```

#### `reset-workstream`

```
agentrelay reset-workstream <graph.yaml> --workstream <ws-id>
```

Peels a fully merged workstream from its target branch (typically
`main`). This is the workstream-level equivalent of `reset-task` — it
undoes the integration PR merge. Only valid when the workstream is the
most recently merged workstream on its target branch (stack constraint).

**Preconditions:**
1. The workstream must be in MERGED status (its integration PR was
   merged into the target branch).
2. The workstream must be the most recently merged workstream on its
   target branch. Error with guidance if a later workstream was merged
   after it.

**Operation:**
1. Read `target_branch_before_merge` from the workstream's
   `resolved.json`
2. Reset the target branch to that SHA
3. Force-push the target branch
4. Clean up all workstream state: close/delete integration PR, delete
   integration branch, remove worktree, delete all task signal
   directories, delete all task branches, delete workstream signal
   directory
5. Prune stale git worktree refs
6. Print confirmation: "Reset workstream 'ws-2'. Target branch 'main'
   rolled back. All workstream state removed."

After this, the workstream and all its tasks are gone — as if they
never ran. The target branch is back to where it was before this
workstream's integration PR was merged. Re-running the graph starts
this workstream from scratch.

**Example — four-workstream graph:**
```
WS-1 (merged) → WS-2 (merged) → WS-3 (interrupted) → WS-4 (interrupted)
```

```bash
# Using reset-to (one command, direct jump):
agentrelay reset-to my-graph.yaml --after ws-1

# Or using primitive commands (step-by-step):
agentrelay reset-task my-graph.yaml --task task-i   # WS-3 tip
agentrelay reset-task my-graph.yaml --task task-h   # WS-3
agentrelay reset-task my-graph.yaml --task task-g   # WS-3
agentrelay teardown-workstream my-graph.yaml --workstream ws-3

agentrelay reset-task my-graph.yaml --task task-l   # WS-4 tip
agentrelay reset-task my-graph.yaml --task task-k   # WS-4
agentrelay reset-task my-graph.yaml --task task-j   # WS-4
agentrelay teardown-workstream my-graph.yaml --workstream ws-4

agentrelay reset-workstream my-graph.yaml --workstream ws-2

# Either way, re-run — WS-1 frozen, WS-2/3/4 start fresh
agentrelay run my-graph.yaml
```

#### `reset-to` — direct-jump batch rollback

```
agentrelay reset-to <graph.yaml> --after <task-or-workstream-id>
```

Rolls the graph back to an arbitrary reachable state in a single
command. The user specifies the target ("keep everything up to and
including X"), and the system computes the minimum set of operations
to reach that state, displays a plan, and executes after confirmation.

**Target specification:**
- `--after task-b` — keep task B and everything before it in its
  workstream. Peel later tasks. Other workstreams untouched.
- `--after ws-1` — keep WS-1 and everything merged before it on its
  target branch. Remove later merged workstreams from the target
  branch, tear down in-progress workstreams.

**Direct jump, not sequential pops.** The stack model defines which
states are reachable, but once the target is validated, the system
jumps directly rather than popping one-by-one. Each `resolved.json`
has the exact SHA to reset to, so:

- Removing 3 tasks from an integration branch = 1 branch reset +
  1 force-push (to the first removed task's
  `integration_branch_before_merge`), then batch-delete signal dirs
  and branches.
- Removing 2 workstreams from main = 1 main reset + 1 force-push
  (to the first removed workstream's `target_branch_before_merge`),
  then batch cleanup of all workstream state.

This is more efficient than sequential pops (fewer force-pushes) and
simpler conceptually (one atomic operation).

**Execution plan display:**
```
$ agentrelay reset-to my-graph.yaml --after ws-1

Plan:
  Reset main to abc123 (before ws-2 merge)
  Remove WS-2: delete integration branch, worktree, 3 task branches,
    all signal files
  Remove WS-3: delete worktree, 2 task branches, signal files
    (was in-progress, not merged to main)
  Remove WS-4: delete worktree, 1 task branch, signal files
    (was in-progress, not merged to main)

  1 force-push (main)
  3 worktrees removed
  6 branches deleted
  10 signal directories deleted

Proceed? [y/N]
```

The plan distinguishes between workstreams being unmerged from the
target branch (destructive) vs. those simply being cleaned up
(infrastructure removal). The user sees exactly what will happen.

**Validation rules:**
1. The target must exist and be completed (in a success state).
2. Everything after the target must form a valid removal set — no
   completed task can remain that depends on a task being removed
   (would break the execution graph).
3. Workstreams being removed from the target branch must be in
   stack-tip order (most recently merged first).

**Shared utility layer.** `reset-to`, `reset-task`,
`reset-workstream`, and `teardown-workstream` all use the same
underlying operations:
- `_reset_branch(repo_path, branch, target_sha)` — reset + force-push
- `_delete_task_state(run_dir, task_id, graph_name, repo_path)` —
  signal dir + branch cleanup
- `_delete_workstream_state(run_dir, ws_id, graph_name, repo_path)` —
  worktree + integration branch + signal dir cleanup

The primitive commands (`reset-task`, `reset-workstream`,
`teardown-workstream`) validate constraints and call these utilities
for a single target. `reset-to` validates the target state, computes
the full operation set, and calls the same utilities in batch.

### Idempotent preparation as a safety net

The orchestrator only calls `workstream_runner.prepare()` for PENDING
workstreams, so reconstructed ACTIVE/MERGE_READY/etc. workstreams skip
preparation entirely. However, defensive idempotency in the workstream
preparer prevents crashes if reconstruction misclassifies a state. This
is a small, low-risk change.

### MVP scope boundaries

**In scope:**
- Per-run directory layout
- `resolved.json` written on task completion (includes pre-merge SHA)
- Workstream-level `resolved.json` on integration PR merge (includes
  target branch pre-merge SHA)
- Auto-detect resume vs. fresh run
- `--force-fresh` CLI flag to start a new run
- Reconstruct task/workstream runtimes from signal files on disk
- Frozen task validation (informational override report, error only on
  missing task ID)
- Normalize stale RUNNING/PR_CREATED states
- Skip completed tasks, retry failed tasks, proceed with unstarted
- Resume-safe workstream preparation
- Resume summary table
- Stale worktree/branch cleanup on fresh restart
- `reset-task` command (stack-based undo from workstream tip)
- `teardown-workstream` command (wipe empty workstream infrastructure)
- `reset-workstream` command (stack-based undo from target branch tip)
- `reset-to` command (direct-jump batch rollback to any reachable state)

**Explicitly deferred to Rust:**
- Corruption detection / worktree validation
- Cherry-pick re-run of individual tasks (re-run task B but keep C
  and D — requires reordering merged work, not just peeling from tip)
- Human-triggered re-run of a completed task in place ("rewind" — redo
  task B with different instructions without disturbing later tasks)
- Carry-forward of `resolved.json` across runs (MVP references backward
  to the previous run's resolved files rather than copying them into
  the new run directory)

## Plan

### PR A: Per-run directory layout — #191 Merged

**Scope:** Structural foundation. Must land first — all subsequent PRs
build on the new directory layout.

**Changes:**

1. **Introduce run directory computation.** New helper function (likely
   in `run_graph.py` or a small utility) that determines the current
   run directory:
   - Fresh run: `runs/0/` (or next available number)
   - Resume: latest existing `runs/<N>/`
   - Force-fresh: `runs/<N+1>/`

2. **Update path construction** in the ~6 places that build paths from
   the workflow directory root:
   - `_record_run_start()` → writes to `runs/<N>/run_info.json`
   - `_record_run_config()` → writes to `runs/<N>/run_config.json`
   - `_copy_graph_yaml()` → copies to `runs/<N>/graph.yaml`
   - `GitWorkstreamPreparer` → signal_dir under `runs/<N>/workstreams/`
   - `WorktreeTaskPreparer` → signal_dir under `runs/<N>/signals/`
   - Agent instructions: `graph_yaml_path` and `signals_base_path`
     under `runs/<N>/`

3. **Propagate run directory.** The run directory path needs to flow
   from `run_graph()` through to the builders. Options:
   - Pass `run_dir: Path` instead of `graph_name` + `repo_path` where
     paths are constructed, or
   - Add a `run_dir` parameter alongside existing params and use it
     for path construction while keeping `graph_name` for naming.

   The exact threading will become clear during implementation; the key
   constraint is that no code should compute
   `.workflow/<graph>/signals/...` directly anymore — it should go
   through the run directory.

4. **Update `reset_graph.py`** to handle per-run layout:
   - Reads `run_info.json` from the latest run directory
   - Removes the entire `.workflow/<graph>/` tree (all runs)

5. **Diagram update**: update module diagram annotations if any new
   classes/functions are added.

**Files touched:**
- `src/agentrelay/run_graph.py`
- `src/agentrelay/workstream/implementations/workstream_preparer.py`
- `src/agentrelay/task_runner/implementations/task_preparer.py`
- `src/agentrelay/reset_graph.py`
- Tests for all affected files

**Tests:**
- Run directory numbering: first run → `runs/0/`, second → `runs/1/`
- Signal files written to correct run directory
- Reset reads from latest run directory
- Existing test suite passes with updated paths

### PR B: Frozen records and validation — #192 Merged

**Scope:** Core resumption data model. Can develop in parallel with
PR A once the directory layout contract is agreed (even if PR A hasn't
landed, PR B can use the agreed path convention).

**Changes:**

1. **Write task `resolved.json` on task completion.** In the task
   runner's completion path (after PR_MERGED or COMPLETED status is
   written):
   - Build a `ResolvedTask` dataclass from the runtime's task spec and
     execution state
   - Record `integration_branch_before_merge` SHA (read from git just
     before the merge step)
   - Serialize to `signal_dir/resolved.json`

2. **Write workstream `resolved.json` on integration merge.** In the
   workstream runner's merge detection path (when the integration PR
   merge is detected):
   - Build a `ResolvedWorkstream` dataclass
   - Record `target_branch_before_merge` SHA (read from git just
     before the merge, or from the integration PR merge event)
   - Serialize to workstream `signal_dir/resolved.json`

3. **`ResolvedTask` dataclass** — captures the frozen task definition:
   ```python
   @dataclass(frozen=True)
   class ResolvedTask:
       task_id: str
       workstream_id: str
       dependencies: tuple[str, ...]
       inputs_from: tuple[InputsFromSpec, ...]
       role: str
       model: Optional[str]
       tagged_paths: tuple[TaggedPathSpec, ...]
       branch_name: str
       integration_branch: str
       integration_branch_before_merge: Optional[str]
       completed_at_attempt: int
       pr_url: Optional[str]
   ```

4. **`ResolvedWorkstream` dataclass** — captures the frozen workstream
   merge:
   ```python
   @dataclass(frozen=True)
   class ResolvedWorkstream:
       workstream_id: str
       integration_pr_url: Optional[str]
       target_branch: str
       target_branch_before_merge: str
       merged_at: str
   ```

5. **Validation function**: `validate_frozen_tasks(frozen: dict[str,
   ResolvedTask], current_graph: TaskGraph) -> FrozenValidation`
   - For each frozen task: check existence in current graph
   - Missing task ID → hard error (DAG needs the node)
   - Attribute differences → collected as informational overrides
   - Returns structured result with errors and overrides

6. **Override comparison**: `compare_resolved(frozen: ResolvedTask,
   current_resolution: ResolvedTask) -> list[Override]` — pure function
   that diffs two resolved tasks and returns per-attribute overrides
   for the console to format.

7. **Diagram update**: add `ResolvedTask` and `ResolvedWorkstream` to
   the diagram.

**Files touched:**
- `src/agentrelay/orchestrator/resolved.py` (new — dataclasses +
  serialization + validation)
- `src/agentrelay/task_runner/core/runner.py` (write resolved.json on
  completion, capture pre-merge SHA)
- `src/agentrelay/workstream/core/runner.py` or integration path (write
  workstream resolved.json on merge detection)
- `docs/diagrams/uml/diagram-detailed.d2`
- `test/orchestrator/test_resolved.py` (new)
- `test/task_runner/core/test_runner.py` (resolved.json written)

**Tests:**
- `ResolvedTask` round-trip serialization (write + read)
- `ResolvedWorkstream` round-trip serialization (write + read)
- `validate_frozen_tasks()`: matching graph passes, missing task errors,
  attribute differences produce overrides (not errors)
- `compare_resolved()`: identical tasks → no overrides, each differing
  attribute produces an override entry
- Integration: task runner writes `resolved.json` after PR_MERGED
- Integration: task runner writes `resolved.json` after COMPLETED
- Integration: `integration_branch_before_merge` SHA is captured
- Integration: workstream `resolved.json` written on merge detection
- Integration: `target_branch_before_merge` SHA is captured
- Edge case: task with no PR (COMPLETED) → `pr_url` is null,
  `integration_branch_before_merge` is null
- Edge case: workstream with no commits ahead → no integration PR,
  `integration_pr_url` is null

### PR B2: Fix tmux kickoff prompt submission — #193 Merged

**Scope:** Quick fix for agent kickoff — Claude Code 2.1.105 changed
prompt submission behavior so a single Enter no longer submits the
prompt. Agents sit idle until a human presses Enter in the tmux pane.

**Root cause:** `tmux send-keys ... Enter` types the kickoff message
and presses Enter once. Newer Claude Code versions appear to require
a second Enter (or the initial Enter is interpreted as a newline rather
than a submit). The `wait_for_tui_ready()` marker detection ("bypass
permissions") still works — the issue is specifically in the submit
step.

**Changes:**

1. **Investigate the exact submission behavior.** In a fresh tmux pane
   running `claude`, test whether:
   - Double Enter submits
   - A short delay + second Enter submits
   - The behavior depends on prompt length or content

2. **Fix `send_kickoff()` in `tmux_agent.py`** to reliably submit the
   prompt. Likely: send a second `Enter` after a brief delay, or
   switch to sending Enter as a separate `send-keys` call.

3. **Verify with e2e.** Run `no_commit_single` (fastest graph) without
   manual intervention to confirm agents start automatically.

**Files touched:**
- `src/agentrelay/agent/implementations/tmux_agent.py`
- `src/agentrelay/ops/tmux.py` (if `send_keys` needs a retry/delay)
- Possibly OCI container configuration if the issue affects containers

**Tests:**
- Existing `test_task_runner.py` and `test_tmux_agent.py` still pass
- E2E: `no_commit_single` completes without manual Enter

### PR C: State probing and runtime reconstruction — #194 Merged

**Scope:** Core probe logic. Depends on PR A (path layout) and PR B
(resolved.json format).

**Changes:**

1. **New `orchestrator/probe.py` module** — state probing functions:

   - `probe_graph_state(repo_path, graph_name, graph, run_dir)
     -> GraphProbe` — top-level entry point. Returns a `GraphProbe`
     dataclass with reconstructed task/workstream runtimes and frozen
     task records.

   - `_probe_task_state(run_dir, task_id)` — reads a single task's
     on-disk state:
     - Compute `signal_dir` = `run_dir / "signals" / task_id`
     - Read status via `_read_task_status_from_signals(signal_dir)`
     - Determine `attempt_num` from highest-numbered
       `attempts/<N>/` subdirectory
     - Read PR URL from `.done` file (line 2) if in a completed state
     - Load `resolved.json` if present (frozen task)
     - Derive `branch_name` from convention:
       `agentrelay/<graph_name>/<task_id>`

   - `_probe_workstream_state(run_dir, ws_id)` — reads a single
     workstream's on-disk state:
     - Compute `signal_dir` = `run_dir / "workstreams" / ws_id`
     - Read status via `_read_status_from_signals(signal_dir)`
     - Read `worktree_path` =
       `repo_path / ".worktrees" / graph_name / ws_id`
     - Derive `branch_name`:
       `agentrelay/<graph_name>/<ws_id>/integration`
     - Read `merge_pr_url` from `pr_created` signal file content
     - Load workstream `resolved.json` if present

   - `_normalize_stale_running(signal_dir, attempt_dir)` — check
     `.done`/`.failed` in the attempt directory, write the appropriate
     status signal, return the resolved status.

   - `_normalize_stale_pr_created(signal_dir, pr_url)` — check PR
     merge status via `gh pr view`, attempt merge if open, write the
     resolved status signal.

2. **`TaskRuntimeBuilder.from_disk()` class method** in `builders.py`:
   - For each task in graph: call `_probe_task_state()`, construct
     `TaskRuntime` with populated `TaskState` and `TaskArtifacts`.
   - Return `dict[str, TaskRuntime]` matching `from_graph()` signature.

3. **`WorkstreamRuntimeBuilder.from_disk()` class method** in
   `builders.py`:
   - For each workstream in graph: call `_probe_workstream_state()`,
     construct `WorkstreamRuntime` with populated state/artifacts.
   - Return `dict[str, WorkstreamRuntime]` matching `from_graph()`
     signature.

4. **Diagram update**: add `probe.py` to
   `docs/diagrams/uml/diagram-detailed.d2` under the `orchestrator`
   module. Re-render with `pixi run diagram`.

**Files touched:**
- `src/agentrelay/orchestrator/probe.py` (new)
- `src/agentrelay/orchestrator/__init__.py` (export)
- `src/agentrelay/orchestrator/builders.py` (new class methods)
- `docs/diagrams/uml/diagram-detailed.d2` (new node)
- `test/orchestrator/test_probe.py` (new)
- `test/orchestrator/test_builders.py` (new from_disk tests)

**Tests:**
- `_probe_task_state()` with each status: PENDING, COMPLETED,
  PR_MERGED, FAILED, RUNNING (with/without `.done`), PR_CREATED
- `_probe_workstream_state()` with each status, including MERGED
  (with `resolved.json`)
- `_normalize_stale_running()` — all three outcomes (done, failed,
  neither)
- `_normalize_stale_pr_created()` — merged, mergeable, unmergeable
- `from_disk()` end-to-end with mocked filesystem + gh calls
- Edge case: signal_dir does not exist (task never started)
- Edge case: zero attempt directories (task was pending)
- Edge case: `resolved.json` present → frozen task loaded into probe

**Notes from implementation (2026-04-15):**

- **Method naming:** shipped as `TaskRuntimeBuilder.from_probe()` /
  `WorkstreamRuntimeBuilder.from_probe()` rather than `from_disk()` —
  the builders take a `GraphProbe` object (not a filesystem path),
  since the probe module owns all filesystem reads.  Keeps the
  builders pure and testable without tmp_path fixtures.
- **New protocol `TaskPrProber`** in `workstream/core/io.py` with
  `is_merged(pr_url) -> bool` and `try_merge(pr_url) -> bool`.  Small
  two-method protocol so the probe module can normalize stale
  `PR_CREATED` tasks without depending directly on `ops/gh.py`,
  matching the protocol-isolation pattern used by `TaskMerger`,
  `IntegrationMergeChecker`, and `IntegrationAutoMerger`.
  `GhTaskPrProber` is the implementation.  `try_merge` is explicitly
  best-effort — wraps `gh.pr_merge` in try/except and returns `False`
  on `CalledProcessError` rather than raising.
- **Lazy `attempts/<N>/` creation:** the preparer only creates
  `signal_dir` + `status/pending`; the per-attempt directory is
  created lazily by the agent's first `TaskHelper` call.  That means
  there is a real window where `status/running` exists but
  `attempts/<N>/` does not.  `_normalize_stale_running` handles this
  correctly without special code because `signals.read_signal_file()`
  returns `None` when the parent directory is missing, routing the
  task through the "no terminal signal" branch to `FAILED`.  This
  edge case is documented in the `probe.py` module and
  `_normalize_stale_running` docstrings so it flows into the
  auto-generated API reference.
- **Stale status signal files accumulate without cleanup.** When
  normalization writes a new status signal file on top of an existing
  one (e.g., `status/running` + newly-written `status/pr_merged`),
  the latest-in-sequence rule in `_read_task_status_from_signals`
  resolves correctly with `FAILED` taking absolute priority.  No
  cleanup needed — verified against real `quick-chained/runs/0/` layout.
- **Validation beyond unit tests:**
  1. Python smoke test against a real prior run directory
     (`/data/git/agentrelaydemos/main/.workflow/quick-chained/runs/0/`)
     — reconstructed `pr_merged` status for both tasks, loaded real
     PR URLs, `resolved.json` records with pre-merge SHAs, and a
     workstream in `PR_CREATED` state with its integration PR URL.
     Confirmed path resolution, status reading, and `resolved.json`
     loading all work against a real orchestrator-written layout.
  2. Synthetic stale-state injection: 5 scenarios on fresh copies of
     the real run dir (stripped to force `RUNNING` with various
     attempt-dir contents), exercising all four `_normalize_stale_running`
     branches plus all four `_normalize_stale_pr_created` branches
     plus the chained `RUNNING → PR_CREATED → {PR_MERGED, FAILED}`
     paths.  5/5 pass.
- **Full end-to-end "kill orchestrator, restart, verify resumption"
  e2e** is **blocked on PR E** — the probe isn't wired into
  `run_graph.py` yet.
- **Backlog items added during PR C:**
  - Local-only (no-remote) execution mode — the protocol layer
    isolates from GitHub specifically but still assumes *some* remote
    exists.  Backlogged under Integration rather than shoehorning
    into PR C.
  - CLI tool `agentrelay probe` for inspecting existing run state.
    Can be built any time after PR C since the probe machinery now
    exists.  Notes the design tension around the mutation side effect
    (stale-state normalization) — a CLI named "probe" would need
    either a `--dry-run` default or a refactor separating read-only
    reconstruction from normalization.
- **Test delta:** +46 new tests (1507 → 1553).  `pixi run check`
  passes.  PR #194.

### PR D: Idempotent workstream preparation — #196 Merged

**Scope:** Small, defensive. Develop in parallel with PR B and PR C.
Depends on PR A (path layout).

**Changes:**

1. **`GitWorkstreamPreparer.prepare_workstream()`** — add an existence
   check before `git.worktree_add()`:
   ```python
   if worktree_path.is_dir():
       # Worktree already exists (resume scenario). Skip creation,
       # just populate state from existing infrastructure.
       pass
   else:
       git.fetch_branch(...)
       git.update_local_ref(...)
       git.worktree_add(...)
       git.push_branch(...)
       git.set_config(...)
   ```
   State assignment (`signal_dir`, `worktree_path`, `branch_name`,
   `mark_pending()`) happens unconditionally — idempotent on existing
   signal files.

**Files touched:**
- `src/agentrelay/workstream/implementations/workstream_preparer.py`
- `test/workstream/implementations/test_workstream_preparer.py`

**Tests:**
- Existing tests continue to pass (fresh-run path unchanged)
- New test: prepare with pre-existing worktree directory → skips git
  operations, sets state correctly
- New test: prepare with pre-existing worktree + existing signal_dir →
  no crash, state set correctly

### PR E: Wire resumption into run_graph.py + CLI

**Scope:** Integration glue. Depends on PR A, B, C, and D.

**Design simplification (2026-04-16):** The original plan had three run
modes (FRESH, RESUME reusing the same run dir, FORCE_FRESH creating a
new one with `--force-fresh` / `-F` flag). This was simplified to a
single resume mode: if a prior run exists, always create a new
`runs/<N+1>/` directory, always restart in-flight tasks from scratch,
always copy `resolved.json` forward. No `--force-fresh` flag. The user
uses `agentrelay reset` for a full wipe including frozen tasks.

Key decisions driving the simplification:
- Every orchestrator session gets its own run directory — no invisible
  resume boundaries within a single run dir.
- In-flight tasks always restart fresh (source file changes discarded).
  Agents can reference prior run artifacts (logs, concerns) through
  instructions for context.
- `resolved.json` is always copied into the new run dir — each run dir
  is self-contained. Backward-reference approach was rejected because
  chained resumes (run 0 → run 1 → run 2) would lose frozen records.
- `outputs.json` is copied alongside `resolved.json` so downstream
  non-frozen tasks can resolve `inputs_from`.
- Worktrees remain shared (not per-run). PR D's idempotent prep handles
  reuse.
- `start_head` is propagated from the original run so
  `agentrelay reset` always finds the correct pre-graph HEAD.

**Changes:**

1. **Replace `_resolve_run_dir()`** with `_resolve_run_context()`:
   ```python
   @dataclasses.dataclass(frozen=True)
   class _RunContext:
       run_dir: Path
       prior_run_dir: Optional[Path]  # None for fresh runs
       is_resume: bool
       run_number: int
       prior_run_number: Optional[int]

   def _resolve_run_context(repo_path, graph_name) -> _RunContext:
       workflow_dir = repo_path / ".workflow" / graph_name
       if not workflow_dir.is_dir():
           # Fresh: create runs/0/
           ...
       # Resume: find latest run, create runs/<N+1>/
       ...
   ```
   Auto-detect: no CLI flag needed.

2. **Remove `_ConflictError`** — no longer raised. Resume replaces the
   conflict-and-refuse behavior.

3. **Copy frozen artifacts** into new run dir:
   - For frozen tasks: `resolved.json`, `outputs.json` (if exists),
     `status/` signal files.
   - For MERGED workstreams: `resolved.json` and all signal files.
   - Without `merged` status, `_refresh_workstream_terminal_states()`
     would mark the workstream MERGE_READY and try to create a new
     integration PR for already-merged work.

4. **Build resume runtimes** from `from_graph()` + patch:
   - Frozen tasks: set `signal_dir` to new run dir (where status files
     were copied), set `branch_name`, `attempt_num`, `pr_url` from
     the probe.
   - Non-frozen tasks: leave as default (PENDING).
   - MERGED workstreams: set `signal_dir` to new run dir.
   - Non-MERGED workstreams: leave as PENDING — idempotent prep reuses
     existing worktrees.

5. **Reset stale worktree branches**: Before dispatch, switch any
   worktree checked out on a non-frozen task branch back to its
   integration branch. This ensures `WorktreeTaskPreparer` takes the
   force-create path (clean branch) rather than the retry path (which
   preserves old WIP commits).

6. **Propagate `start_head`**: On resume, copy `start_head` from the
   prior run's `run_info.json` instead of using `git rev-parse HEAD`.
   This preserves the original reset point across run chains.

7. **Resume summary table** — print before orchestrator starts:
   ```
   Resuming graph 'my-graph' (run 1, prior: run 0)

     Task            Status     Action
     --------------- ---------- ------------------
     write_spec      completed  skip (frozen)
     write_impl      failed     restart
     review          pending    start
   ```

8. **Frozen override report** — print only when attribute differences
   exist between frozen `resolved.json` and current YAML/CLI.

9. **Config comparison** — compare prior `run_config.json` with current
   settings, emit warnings on mismatch. Current config wins.

10. **`build_task_pr_prober()` factory** in `orchestrator/builders.py` —
    follows the pattern of `build_integration_merge_checker()`. Keeps
    concrete `GhTaskPrProber` import in builders, not in `run_graph.py`.

**Files touched:**
- `src/agentrelay/run_graph.py`
- `src/agentrelay/orchestrator/builders.py` (`build_task_pr_prober()`)
- `src/agentrelay/output/console.py` (resume table + override report)
- `src/agentrelay/cli.py` (remove `_ConflictError` handling)
- `test/test_run_graph.py`
- `test/output/test_console.py`
- `test/test_cli.py`

**Tests:**
- `_resolve_run_context()`: fresh, resume, multiple prior runs
- `_copy_frozen_artifacts()`: frozen task with/without outputs, merged
  workstream, non-merged workstream
- `_build_resume_runtimes()`: mix of frozen/non-frozen tasks, verify
  signal_dir and status
- `_reset_stale_worktree_branches()`: stale branch switched, frozen
  branch untouched, missing worktree skipped
- `_compare_run_configs()`: matching, mismatched, missing file
- `start_head` propagation: fresh uses HEAD, resume uses prior
- Resume summary table formatting
- Frozen override report formatting
- Integration test: `run_graph()` fresh → existing behavior preserved
- Integration test: `run_graph()` resume → pre-built runtimes passed
  to orchestrator
- Integration test: resume with modified YAML → override report printed

### PR E2: Refactor run_graph.py — infrastructure decoupling + phase extraction

**Scope:** Cleanup follow-up to PR E. Reduces `run_graph.py` coupling
to concrete infrastructure and improves readability by extracting the
monolithic `run_graph()` function into named phases.

**Motivation (discovered during PR E):** PR E added ~40 lines of inline
resume logic to an already long function. `run_graph()` directly calls
`docker_ops` (network create/exists/remove) and `tmux.current_session()`
— the wiring layer knows concrete infrastructure mechanisms. If we add
Podman-specific setup, SSH tunnels, or a non-tmux agent environment,
those details would naturally land in `run_graph.py`, turning it from a
composition layer into an implementation layer.

**Changes:**

1. **Extract infrastructure lifecycle behind protocols:**
   - Docker/Podman network lifecycle → protocol behind a factory in
     `builders.py` (similar to `build_task_pr_prober()`).
   - tmux session detection/validation → protocol on
     `AgentEnvironment` or a new `SessionResolver` abstraction.
   - `run_graph.py` calls factories/protocols, never `docker_ops` or
     `tmux` directly.

2. **Extract `run_graph()` into named phases:**
   - `_resolve_config(ops, cli_args) -> OrchestratorConfig` — the
     verbose CLI > YAML > default resolution chain.
   - `_setup_resume(ctx, graph, config) -> (task_runtimes,
     workstream_runtimes)` — probe, validate, copy, build runtimes,
     print summary.
   - `_setup_infrastructure(graph) -> cleanup_callback` — network
     creation, session validation.
   - Top-level `run_graph()` becomes a short sequence of phase calls.

3. **Reduce `run_graph()` parameter count:** Group related parameters
   into a config dataclass (e.g., `RunOptions` combining model, sandbox,
   credentials, verbose, keep_panes, etc.). The 13-keyword signature
   becomes 3–4 parameters.

**Files touched:**
- `src/agentrelay/run_graph.py`
- `src/agentrelay/orchestrator/builders.py` (new factories)
- Tests for refactored functions

**Depends on:** PR E (merged).

### PR F: Shared reset utilities + primitive commands

**Scope:** Shared utility layer and three primitive undo commands.
Depends on PR A (path layout) and PR B (`resolved.json` for pre-merge
SHAs).

**Changes:**

1. **Shared reset utility module** — `src/agentrelay/reset_ops.py`:
   - `_reset_branch(repo_path, branch, target_sha)` — reset branch to
     SHA + force-push. Used by `reset-task` (integration branch),
     `reset-workstream` (target branch), and `reset-to` (both).
   - `_delete_task_state(run_dir, task_id, graph_name, repo_path)` —
     delete task signal directory + task branch (local + remote).
   - `_delete_workstream_state(run_dir, ws_id, graph_name, repo_path)`
     — remove worktree + delete integration branch + delete workstream
     signal directory + prune worktree refs.
   - `_find_workstream_tip(run_dir, graph, ws_id)` — find the most
     recently touched task in a workstream by scanning signal dirs.
   - `_workstream_merge_order(run_dir, graph)` — determine the order
     in which workstreams were merged to the target branch, from
     workstream `resolved.json` timestamps.

   These are stateless, composable building blocks. The primitive
   commands validate constraints and call them for a single target.
   `reset-to` calls them in batch.

2. **`reset-task` subcommand** in `cli.py`:
   - Argument: `graph_yaml` (positional), `--task` / `-t` or
     `--workstream` / `-w` (one required)
   - If `--workstream` provided: auto-detect the tip task via
     `_find_workstream_tip()`
   - If `--task` provided: validate that the target is the tip of its
     workstream's execution stack — error with guidance if not

3. **`reset_task()` function** — core logic:
   - Determine the workstream for the target task
   - Find all tasks in the workstream, ordered by execution sequence
   - Validate the target is the tip
   - If task status is FAILED / RUNNING / stale PR_CREATED (not merged):
     - Call `_delete_task_state()`
     - Switch worktree to integration branch if task branch was
       checked out
   - If task status is PR_MERGED / COMPLETED (merged):
     - Read `integration_branch_before_merge` from `resolved.json`
     - Call `_reset_branch()` on integration branch
     - Call `_delete_task_state()`
   - Print confirmation: "Reset task 'task-c'. Workstream tip is now
     'task-b'." (or "Workstream has no remaining tasks.")

4. **`teardown-workstream` subcommand** in `cli.py`:
   - Arguments: `graph_yaml` (positional), `--workstream` / `-w`
     (required)
   - Validate precondition: all tasks in the workstream have no signal
     directories

5. **`teardown_workstream()` function** — core logic:
   - Validate all tasks are peeled back (no signal dirs)
   - Call `_delete_workstream_state()`
   - Print confirmation: "Teardown workstream 'ws-1'. Infrastructure
     removed. Next run will create fresh worktree from current main."

6. **`reset-workstream` subcommand** in `cli.py`:
   - Arguments: `graph_yaml` (positional), `--workstream` / `-w`
     (required)
   - Validate preconditions: workstream is MERGED, and is the most
     recently merged workstream on its target branch

7. **`reset_workstream()` function** — core logic:
   - Read `target_branch_before_merge` from workstream `resolved.json`
   - Validate this is the tip via `_workstream_merge_order()`
   - Call `_reset_branch()` on target branch
   - Clean up all workstream state: close/delete integration PR,
     call `_delete_task_state()` for each task, call
     `_delete_workstream_state()`
   - Print confirmation: "Reset workstream 'ws-2'. Target branch
     'main' rolled back to <sha>. All workstream state removed."

8. **Diagram update**: add new functions/classes to diagram if needed.

**Files touched:**
- `src/agentrelay/cli.py` (new subcommands)
- `src/agentrelay/reset_ops.py` (new — shared utilities)
- `src/agentrelay/reset_task.py` (new — reset-task core logic)
- `src/agentrelay/reset_workstream.py` (new — teardown + reset
  workstream core logic)
- `docs/diagrams/uml/diagram-detailed.d2`
- `test/test_reset_ops.py` (new — shared utility tests)
- `test/test_reset_task.py` (new)
- `test/test_reset_workstream.py` (new)

**Tests:**
- `_reset_branch()`: resets and force-pushes
- `_delete_task_state()`: signal dir + branch deleted
- `_delete_workstream_state()`: worktree + branch + signal dir deleted
- `_find_workstream_tip()`: finds correct tip task
- `_workstream_merge_order()`: returns correct merge ordering
- `reset_task()`: non-merged tip task → signal dir + branch deleted
- `reset_task()`: merged tip task → integration branch reset, signal
  dir + branch deleted
- `reset_task()`: non-tip task → error with guidance
- `reset_task()`: auto-detect tip when `--workstream` provided
- `reset_task()`: successive resets peel back workstream correctly
- `teardown_workstream()`: all tasks peeled → infrastructure removed
- `teardown_workstream()`: tasks still have state → error with guidance
- `reset_workstream()`: tip merged workstream → target branch reset,
  all state removed
- `reset_workstream()`: non-tip merged workstream → error with guidance
- `reset_workstream()`: non-merged workstream → error with guidance
- Integration: reset all tasks + teardown-workstream → re-run creates
  fresh infrastructure from current main
- Integration: reset-workstream on tip → target branch rolled back,
  re-run starts workstream from scratch

### PR G: `reset-to` batch rollback

**Scope:** Direct-jump batch rollback command. Depends on PR F (shared
utilities).

**Changes:**

1. **`reset-to` subcommand** in `cli.py`:
   - Arguments: `graph_yaml` (positional), `--after` (required, task
     ID or workstream ID)

2. **`reset_to()` function** — core logic:

   a. **Probe current state** — read all task/workstream statuses and
      `resolved.json` files to understand the current execution graph.

   b. **Resolve the target** — determine what `--after X` means:
      - If X is a task ID: keep that task and everything before it in
        its workstream. Other workstreams are untouched unless they
        are downstream (merged after a workstream being removed).
      - If X is a workstream ID: keep that workstream and everything
        merged before it on the target branch.

   c. **Compute the removal set** — everything that needs to be undone
      to reach the target state:
      - Tasks to remove from integration branches (per workstream)
      - Workstream infrastructure to tear down
      - Workstreams to unmerge from the target branch
      - Validate: no completed task that would remain depends on a
        task being removed.

   d. **Compute the minimum operations:**
      - For each integration branch being rolled back: one
        `_reset_branch()` call using the first-removed task's
        `integration_branch_before_merge` SHA.
      - For the target branch (if workstreams are being unmerged): one
        `_reset_branch()` call using the first-removed workstream's
        `target_branch_before_merge` SHA.
      - Batch `_delete_task_state()` for all removed tasks.
      - Batch `_delete_workstream_state()` for all removed/torn-down
        workstreams.

   e. **Display the plan** — structured summary of all operations,
      showing branch resets, force-pushes, and cleanup counts.

   f. **Prompt for confirmation** — `Proceed? [y/N]`

   g. **Execute** — call shared utilities. Order:
      1. Reset target branch (if needed) — most destructive, do first
      2. Reset integration branches (if needed)
      3. Delete task state (signal dirs + branches)
      4. Delete workstream state (worktrees + integration branches +
         signal dirs)

3. **Diagram update**: add to diagram if needed.

**Files touched:**
- `src/agentrelay/cli.py` (new subcommand)
- `src/agentrelay/reset_to.py` (new — target resolution, removal set
  computation, plan display, execution)
- `test/test_reset_to.py` (new)

**Tests:**
- Target resolution: `--after task-b` in a 3-task workstream →
  correct removal set (task C)
- Target resolution: `--after ws-1` in a 4-workstream graph →
  correct removal set (ws-2 from main, ws-3/ws-4 teardown)
- Minimum operations: 3 tasks removed from one integration branch →
  1 branch reset (not 3)
- Minimum operations: 2 workstreams removed from main → 1 main reset
  (not 2)
- Validation: remaining completed task depends on removed task → error
- Plan display: correct operation counts and descriptions
- Integration: `reset-to --after task-a` with A,B,C all merged →
  integration branch reset once, B and C cleaned up
- Integration: `reset-to --after ws-1` with ws-1 merged, ws-2 merged,
  ws-3 in progress → main reset once, all state for ws-2/ws-3 removed
- Integration: reset-to then re-run → graph resumes correctly from
  the target state

## Merge order

```
PR A (per-run dirs) ──→ PR B (frozen records) ──┐
                   │                            ├──→ PR E (wiring + CLI)
                   ├──→ PR C (state probing) ───┘
                   │
                   ├──→ PR D (idempotent prep)
                   │
                   └──→ PR F (shared utils + primitive cmds) ──→ PR G (reset-to)
                        (depends on A + B)
```

PR A must land first (directory layout foundation). After PR A:
- PRs B, C, D can develop in parallel
- PR F can start once PR B lands (needs `resolved.json` format)
- PR E depends on B, C, and D
- PR G depends on PR F (uses shared utilities)
- PR E and PR G are independent of each other

## Risk assessment

**Low risk:**
- PR A is path plumbing — mechanical, well-scoped, concentrated in ~6
  places.
- PR B is a new write + dataclass + validation — clean addition, no
  existing behavior changes.
- PR D is a small defensive change with clear skip-if-exists semantics.
- The orchestrator's existing init path already handles pre-built
  runtimes — no changes needed inside the orchestrator.
- Signal-file-backed status means all state is inspectable and
  debuggable on disk.
- PR G reuses PR F's shared utilities — no new destructive primitives,
  just composition.

**Medium risk:**
- Stale PR_CREATED normalization calls `gh pr merge` as a side effect
  during probe. If the PR has merge conflicts, it fails gracefully
  (task marked FAILED, retried). But it's a side effect in what should
  be a read-mostly operation.
- Attempt number reconstruction from `attempts/<N>/` subdirectories
  must handle edge cases (no attempts dir = attempt 0, gaps in
  numbering).
- FORCE_FRESH run mode has the most complex flow — it combines cleanup,
  validation, and fresh-start in a single path. Careful testing needed.
- `reset-task` and `reset-workstream` perform force-pushes. Safe due
  to the stack constraint (nothing was merged after the tip), but
  force-push is inherently destructive. The stack constraint is
  validated before any destructive operation.
- `reset-workstream` and `reset-to` may force-push to the target
  branch (usually `main`). This is the most destructive operation in
  the system. The stack constraint and `target_branch_before_merge`
  SHA make it deterministic, but careful validation is essential.
- `reset-to` computes a multi-level removal set — the target
  resolution and validation logic must correctly handle cross-workstream
  dependencies and mixed workstream states (some merged, some
  in-progress, some pending).

**Mitigations:**
- All normalization writes status signals to disk, so the state is
  always consistent even if the probe is interrupted.
- `resolved.json` is write-once — no mutation, no corruption risk.
- Pre-merge SHAs (`integration_branch_before_merge`,
  `target_branch_before_merge`) make all undo operations deterministic —
  no commit archaeology.
- Stack constraints are validated before any destructive operation at
  every level.
- `reset-to` displays a full plan and requires explicit confirmation
  before executing.
- `reset-to` uses the same shared utilities as the primitive commands —
  no new destructive code paths, just composition.
- Extensive unit tests for each probe and reset path.
- E2e graph specifically tests the resume scenario end-to-end.

## Estimated effort

- PR A: 1 day (path plumbing + test updates)
- PR B: 1–1.5 days (two dataclasses, serialization, validation, tests)
- PR C: 1–1.5 days (probe logic + tests)
- PR D: 0.5 day (small change, focused tests)
- PR E: 1–1.5 days (wiring, CLI, summary table, override report)
- PR F: 1.5 days (shared utilities + three commands, stack validation)
- PR G: 1 day (target resolution, removal set, plan display, tests)
- Total: 5.5–6.5 days (B, C, D parallelizable after A; F after B;
  E after B+C+D; G after F. E and G are independent.)

## Decisions resolved

1. **Resume summary table:** Yes. Two sections — task status table
   (always) and frozen override report (only when differences exist).

2. **Fresh restart:** Yes, via `--force-fresh` / `-F`. Previous run
   directories are preserved. Stale git state (worktrees, branches) is
   cleaned up.

3. **Frozen task validation:** Execution graph wins. Attribute
   differences produce an informational override report, not an error.
   The only hard error is a completed task ID missing from the current
   graph (DAG needs the node). Pending/failed tasks are free to change.

4. **Per-run directories:** Yes. `.workflow/<graph>/runs/<N>/` mirrors
   the per-attempt pattern for tasks. History preserved, fresh restart
   is clean.

5. **Frozen records:** `resolved.json` written at two levels:
   - Task-level: once per completed task, with
     `integration_branch_before_merge` SHA.
   - Workstream-level: once per merged workstream, with
     `target_branch_before_merge` SHA.
   These are the source of truth for the execution graph and enable
   deterministic undo at every level.

6. **Worktree preservation:** Required for mid-workstream resume.
   Worktrees contain the integration branch with merged task code and
   potentially WIP commits from failed tasks.

7. **Stack-based undo model:** Uniform pattern at three levels:
   - `reset-task`: peel task from integration branch tip
   - `reset-workstream`: peel workstream from target branch tip
   - `agentrelay reset`: wipe everything
   Plus `teardown-workstream` for infrastructure cleanup (not an undo).
   `teardown-workstream` requires all tasks peeled first.
   `reset-workstream` requires the workstream to be the most recently
   merged on its target branch.

8. **Direct-jump batch rollback:** `reset-to --after <id>` computes
   the minimum operations to reach a target state and executes them
   in batch. Uses the same shared utilities as the primitive commands.
   The stack model validates which states are reachable; the direct
   jump avoids redundant sequential pops (one branch reset instead of
   N).

## Parallelization assessment

> **Assessed:** 2026-04-13. Update this section if PR specs or
> dependencies change.

### Dependency chain

The dependency graph is deep. PR A is the foundation — every other PR
depends on it (directly or transitively). The longest chain is
A → B → C → E (4 PRs deep).

```
PR A (per-run dirs) ──→ PR B (frozen records) ──→ PR C (state probing) ──→ PR E (wiring)
                   │                          │
                   ├──→ PR D (idempotent prep) ──→ PR E
                   │                          │
                   └──────────────────────────→ PR F (reset utils) ──→ PR G (reset-to)
```

### Hard dependencies

| From | To | Reason |
|---|---|---|
| A → B | B writes `resolved.json` to paths determined by A's layout |
| A → C | C reads signal files from A's run directories |
| A → D | D modifies `workstream_preparer.py`, which A also modifies |
| A → F | F reads from A's run directories |
| B → C | C imports `ResolvedTask` from B's `resolved.py` |
| B → E | E calls B's `validate_frozen_tasks()` |
| B → F | F reads B's `resolved.json` for pre-merge SHAs |
| C → E | E calls C's `probe_graph_state()` |
| D → E | E assumes D's idempotent prep behavior |
| F → G | G imports F's `reset_ops.py` utilities |

### Independent pairs

| Pair | Why independent |
|---|---|
| B ↔ D | Different files (`task_runner/core/runner.py` vs `workstream_preparer.py`), no imports |
| C ↔ F | Different files (`orchestrator/probe.py` + `builders.py` vs `reset_ops.py` + `reset_task.py`), no imports |
| C ↔ D | Different files, no imports |
| E ↔ G | No shared files, no imports |

### File overlap risk

E and F both modify `cli.py`, but in different regions — E adds a
`--force-fresh` flag to the existing `run` subcommand, F adds three
new subcommands (`reset-task`, `teardown-workstream`,
`reset-workstream`). Land F before E to minimize conflict (F's changes
are additive new subcommands).

### Recommended execution phases

```
Phase 1:  PR A              (alone — foundation)
Phase 2:  PR B ‖ PR D       (parallel — independent files)
Phase 3:  PR C ‖ PR F       (parallel — C needs B, F needs A+B)
Phase 4:  PR E ‖ PR G       (parallel — E needs B+C+D, G needs F)
```

Merge order within phases:
- **Phase 2:** Land B before D — B is on the critical path (C, E, F
  all need it), D is only needed by E.
- **Phase 3:** Land F before C — unblocks G earlier, and F's `cli.py`
  changes (new subcommands) merge cleanly before E's changes (flag on
  existing subcommand).
- **Phase 4:** E and G are independent — either order is fine.

### Summary

Parallelization is limited but real. Maximum 2 PRs at a time, in
three parallel pairs (B‖D, C‖F, E‖G). The critical path is 4 phases
regardless of parallelization. The main value is developing B+D
simultaneously (saves ~0.5 day) and C+F simultaneously (saves ~1 day).
