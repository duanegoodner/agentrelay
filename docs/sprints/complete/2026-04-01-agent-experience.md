# Sprint Notes — 2026-04-01: Agent Experience

> **Status: Complete.** All 5 PRs (A–E) merged. PRs C, D, E were developed
> in parallel across git worktrees and merged sequentially with no conflicts.
> The original PR C (context.md wiring) was superseded by a broader
> context-sharing design; see `docs/discussions/CONTEXT_SHARING.md`.
> Phase 1 of that design ships in sprint 2026-04-03.

## Goal

Fix known agent reliability issues surfaced during e2e testing: the
`agentrelay-complete` retry bug, semantic correctness of PR-less task status,
a missing `agentrelay-summary` CLI for PR-less tasks, and explicit worktree
CWD guidance to prevent the Haiku-class commit-to-main bug at Level 0.

## Context

Sprints 2026-03-26 and 2026-03-30 completed the agent isolation infrastructure
(OCI containers, scoped PATs, credential injection, OAuth support). With the
infrastructure layer solid, the focus shifts to agent-facing quality: the
reliability of the SDK agents use during execution, the semantic correctness of
task state as recorded by the orchestrator, and the information agents receive
about their working environment.

Four friction points accumulated across e2e testing and code review:

1. **`agentrelay-complete` retry failure** — when a task retries after a gate
   failure, the PR from attempt 1 already exists. `gh pr create` rejects the
   duplicate, and the agent must manually discover the existing PR URL and call
   `mark_done` directly (observed with Sonnet; fragile).
2. **`PR_MERGED` misused for PR-less completion** — the terminal success
   status for a task that never created a PR reads `PR_MERGED`. Works
   mechanically but is misleading for auditing and tooling.
3. **PR-less tasks leave no summary** — `test_reviewer` and similar PR-less
   roles produce no `summary.md`. Their output is invisible to the integration
   PR body and to any future context-sharing mechanism.
4. **Agent worktree navigation** — at Level 0 (no OCI isolation), weaker
   models (observed with Haiku) navigate out of the worktree to the main repo
   and commit to `main`. OCI isolation hard-prevents this at Level 2 via
   filesystem boundaries. Level 0 needs explicit instruction-level guidance.

## Architecture notes

**`agentrelay-complete` retry fix:** `TaskHelper.create_pr()` calls
`gh pr create`, which fails on retry when the PR from attempt 1 already exists.
Fix: check for an existing open PR first with `gh pr list --head <branch>
--base <integration_branch> --state open` and reuse it if found. No protocol
changes needed, no stderr parsing — uses stable `gh` JSON output.

**`COMPLETED` status:** Adding `TaskStatus.COMPLETED` requires updating
`ALLOWED_TASK_TRANSITIONS`, all consumers that treat `PR_MERGED` as "task
succeeded" (dependency resolution, workstream terminal state, teardown mode,
console output, integration PR body builder), and the `TaskRunner` completion
path for PR-less tasks. The specific line is `task_runner/core/runner.py:302`
where PR-less completion currently transitions to `PR_MERGED`.

**`agentrelay-summary` CLI:** Writes agent-supplied text to
`signal_dir/summary.md`. The orchestrator already reads `summary.md` during
integration PR body assembly — no consumer changes needed. The new command
is a peer of `agentrelay-complete-without-pr`.

**Worktree CWD guidance:** The worktree path is known at instruction assembly
time. A "Working directory" note in the instructions (in `templates.py`) gives
Level 0 agents explicit guidance; at Level 2 it is defense-in-depth.

**Context sharing:** The original PR C in this sprint was a simple "push
assembled context.md at launch" approach. This has been superseded by a broader
pull-based graph-awareness design documented in
`docs/discussions/CONTEXT_SHARING.md`.
None of the PRs below depend on that design.

---

## PR plan

### PR A: Fix `agentrelay-complete` retry failure — Merged (#149)

- Branch: `feat/agent-sdk-retry-fix`

When a task retries after gate failure, the PR from attempt 1 already exists.
`agentrelay-complete` calls `gh pr create`, which fails with "a pull request
for branch … already exists." The agent must manually work around it — fragile.

**Changes:**
- `src/agentrelay/agent_sdk/task_helper.py` — `create_pr()`: before calling
  `gh pr create`, check for an existing open PR with
  `gh pr list --head <branch> --base <integration_branch> --state open --json url -q '.[0].url'`.
  If a URL is returned, reuse it (PR already exists from a previous attempt).
  If empty, proceed with `gh pr create` as before. This avoids parsing stderr
  error messages, which are fragile (locale-dependent, subject to change across
  `gh` CLI versions). The `--base` filter ensures we only reuse a PR targeting
  the correct integration branch, not a leftover from a different graph run.
  Both `branch_name` and `integration_branch` are already available on
  `TaskHelper`.
- On reuse, body is updated via `gh api` REST endpoint (not `gh pr edit`)
  to avoid the GraphQL "Projects (classic)" deprecation error.
- Unit tests: normal PR creation (no existing PR), existing PR detected and
  reused, body update with concerns on reuse. 1190 tests (3 new).

**Acceptance criteria:**
- [x] `agentrelay-complete` succeeds on retry when a PR already exists
- [x] Existing PR URL is returned (no new PR created)
- [x] Other `gh pr create` failure modes still propagate as errors
- [x] `pixi run check` passes

**Observations:**
- `gh pr edit` fails with exit code 1 due to GitHub "Projects (classic)"
  deprecation in the GraphQL API (`projectCards` field). The edit itself
  succeeds but `check=True` sees the non-zero exit. Workaround: use
  `gh api repos/{owner}/{repo}/pulls/{number} -X PATCH -f body=...`
  (REST API, no GraphQL). This also affects our own repo — discovered
  while updating PR #149's body.
- E2E validated with `graphs/failure/retry_on_gate_failure.yaml`
  (`--max-task-attempts 2`). Second agent's `agentrelay-complete`
  succeeds silently — probe finds existing PR, updates body via REST,
  writes `.done` signal. Task still fails as expected (gate targets
  nonexistent test file).

---

### PR B: `COMPLETED` task status for PR-less tasks — Merged (#150)

- Branch: `feat/completed-status`

`PR_MERGED` is reused as the terminal success status for tasks that complete
without a PR (e.g. `test_reviewer`). Mechanically fine but semantically wrong.

**Changes:**
- `src/agentrelay/task_runtime/runtime.py` — add `COMPLETED = "completed"`
  to `TaskStatus`.
- `ALLOWED_TASK_TRANSITIONS` — add `RUNNING → COMPLETED`.
- `src/agentrelay/task_runner/core/runner.py` — use `TaskStatus.COMPLETED`
  (not `PR_MERGED`) when completing without a PR.
- All consumers that check `PR_MERGED` as "task succeeded" must also accept
  `COMPLETED`:
  - `orchestrator/` — dependency readiness (`orchestrator.py:209`, `:585`,
    `:715`), dispatch pipeline, terminal state checks
  - `workstream/` — terminal state and teardown mode
  - `task_runner/` — teardown mode enum (`ON_SUCCESS` docstring references
    `PR_MERGED`)
  - `output/` — console display (`status_labels` dict)
  - Integration PR body builder
- Update tests for the new transition and all consumers.

**Acceptance criteria:**
- [x] PR-less task completion records `COMPLETED` status (not `PR_MERGED`)
- [x] PR-backed task completion still records `PR_MERGED` (unchanged)
- [x] Downstream dependency resolution treats both statuses as "task succeeded"
- [x] Workstream terminal state logic treats both as success
- [x] `pixi run check` passes

---

### PR C: `agentrelay-summary` CLI — Merged (#151)

- Branch: `feat/agent-summary-command`

PR-less tasks produce no `summary.md`, so their results are absent from
integration PR bodies and invisible to any future context-sharing mechanism
(see `docs/discussions/CONTEXT_SHARING.md`).
A new CLI command lets any agent write a summary regardless of whether it
created a PR.

**Changes:**
- `src/agentrelay/agent_sdk/` — add `agentrelay-summary --message "..."`
  CLI entry point.
- Writes `message` to `signal_dir/summary.md` (same path the orchestrator
  uses for PR-backed summaries — no consumer changes needed).
- Unit tests for the new CLI command.

**Acceptance criteria:**
- [x] `agentrelay-summary --message "..."` writes `summary.md` to the signal
      directory
- [x] Summary appears in integration PR body for tasks that used
      `agentrelay-summary` (validates against existing orchestrator consumer)
- [x] `pixi run check` passes

---

### PR D: Worktree CWD guidance in agent instructions — Merged (#152)

- Branch: `feat/worktree-cwd-guidance`

Weaker models (observed with Haiku in e2e) may ignore their CWD and navigate
to the main repo, then commit to `main`. OCI isolation hard-prevents this at
Level 2 via filesystem boundaries. Level 0 runs need explicit instruction-level
guidance.

**Changes:**
- Add a "Working directory" note to agent instructions in
  `src/agentrelay/agent_comm_protocol/templates.py` (in the shared preamble
  or the "What to Do" section): "Your working directory is `<worktree_path>`.
  All file edits and git operations must occur within this directory. Do not
  navigate to or operate on paths outside it."
- Note: the worktree path is not currently in `TaskManifest` or the
  `resolve_instructions()` signature. Add a `worktree_path: Path | None`
  parameter to `resolve_instructions()` rather than adding runtime state to
  the manifest schema. Pass `None` for tests that don't need it.
- Unit tests: verify worktree path appears in generated instructions for all
  roles.

**Acceptance criteria:**
- [x] Worktree path CWD guidance appears in `instructions.md` for all roles
- [x] `pixi run check` passes

---

### PR E: Archive attempt artifacts before retry cleanup — Merged (#153)

- Branch: `feat/retry-artifact-archive`

When a task retries after gate failure, `reset_for_retry()` clears signal files
and the next attempt's teardown overwrites `agent.log`. The artifacts from
attempt N are lost — there's no record of what the agent did or what the gate
produced. This makes post-run debugging harder, especially for intermittent
failures.

**Changes:**
- `src/agentrelay/task_runtime/runtime.py` — in `reset_for_retry()`, before
  clearing signals, copy selected files to `signal_dir/attempts/<attempt_num>/`.
  Files to archive: `agent.log`, `gate_last_output.txt`, `summary.md`,
  `concerns.log`. Only copy files that exist (best-effort, no errors on missing
  files). The `attempts/` directory is write-only — nothing reads it during
  execution, it's purely for post-run inspection.
- Unit tests: verify files are archived to the correct subdirectory before
  cleanup, verify missing files are silently skipped, verify signal files
  (`.done`, `.failed`) are not archived.

**Acceptance criteria:**
- [x] `reset_for_retry()` copies attempt artifacts to `signal_dir/attempts/<N>/`
- [x] Missing files are silently skipped (no errors)
- [x] Signal files (`.done`, `.failed`) are not archived
- [x] Archived files survive the retry cleanup
- [x] `pixi run check` passes
