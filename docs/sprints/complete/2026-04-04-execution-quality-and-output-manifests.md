# Sprint Notes — 2026-04-04: Execution Quality & Output Manifests

> **Status: Complete.** All 5 PRs (A–E) merged. PRs developed in parallel
> across git worktrees; merged sequentially A→B→C→D→E. PR E required a
> rebase to resolve one test file conflict (PR B added
> `TestPreviousAttemptsSection`, PR E added `test_mentions_outputs_json` —
> both in `test_templates.py`, different regions). 1273 tests after all
> PRs landed.

## Goal

Fix orchestrator correctness and observability gaps surfaced during recent
e2e testing, and lay the foundation for output-driven task composition by
shipping the `agentrelay-declare` SDK command and `outputs.json` signal file.

## Context

Sprint 2026-04-03 shipped agent graph awareness — agents can now discover
upstream artifacts via graph YAML and signal directory navigation. E2e
validation showed that capable agents (Sonnet) successfully discover file
locations from upstream summaries alone, without `paths` fields or role
templates.

Several quality gaps accumulated during the isolation and agent-experience
sprints:

1. **agent.log lost on task failure** — Scrollback capture happens in
   `TmuxAddress.teardown()`, which is gated by `TearDownMode`. When mode
   is `ON_SUCCESS` and the task fails, teardown is skipped and no
   `agent.log` is written. This means archived attempt directories from
   `reset_for_retry()` never contain the agent's scrollback.

2. **Retry agents are blind to previous attempts** — PR #153 archives
   attempt artifacts to `signal_dir/attempts/<N>/`, and `attempt_num` is
   already in `manifest.json`, but retry agents receive no instruction
   guidance pointing them at archived scrollback or gate output.

3. **fail-fast config is hard-coded** — `fail_fast_on_workstream_error`
   defaults to `True` with no CLI flag. Independent workstreams cannot
   continue when a sibling fails. `fail_fast_on_internal_error` stays
   always-on (internal errors = orchestrator bugs, not agent failures).

4. **Empty integration PR for PR-less workstreams** — When every task in
   a workstream completes without a PR, the integration branch has no
   commits different from the base. `gh pr create` fails because GitHub
   rejects empty PRs.

5. **No structured output declarations** — Agents produce files but don't
   formally declare what they created. The output-driven composition design
   (`docs/discussions/OUTPUT_DRIVEN_COMPOSITION.md`) depends on an
   `outputs.json` manifest as its foundation.

## Architecture notes

**agent.log capture (PR A):** `TmuxAddress.teardown()` does two things:
(1) capture scrollback to `agent.log`, (2) optionally kill the tmux pane.
These should be separated. Scrollback capture should always happen when a
task reaches a terminal status, regardless of `TearDownMode`. The teardown
mode should only gate resource cleanup (pane destruction, branch deletion).
Implementation: extract scrollback capture into a separate step in the task
runner lifecycle that runs unconditionally before the teardown decision.

**Retry agent awareness (PR B):** `attempt_num` is already in
`manifest.json` (written by `build_manifest()` in `manifest.py:77`). The
`attempts/` directory structure is already in place from PR #153. The change
is instruction-level: add a "Previous Attempts" section to
`resolve_instructions()` when `attempt_num > 0`, telling the agent where to
find prior scrollback (`agent.log`), gate output (`gate_last_output.txt`),
and summary (`summary.md`). Use absolute paths derived from `signal_dir`.

**fail-fast CLI (PR C):** Add `--no-fail-fast-on-workstream-error` boolean
flag to `run_graph.py` and wire through `_build_config_from_args`. Also add
an optional `fail_fast_on_workstream_error` field to graph YAML (parsed in
`TaskGraphBuilder`) so the graph author can express this as a property of
the graph's topology. CLI flag overrides graph YAML. No flag for
`fail_fast_on_internal_error` — it stays always-on.

**Skip empty integration PR (PR D):** In
`StandardWorkstreamRunner.integrate()` (or `GhWorkstreamIntegrator`),
before calling `gh.pr_create()`, check whether the integration branch has
any commits ahead of the base branch. If not, skip PR creation and
transition the workstream directly to MERGED (all work was PR-less, nothing
to integrate). Use `git rev-list --count base..integration` or similar.

**Output manifests (PR E):** New `agentrelay-declare` CLI command in
`agent_sdk/`. Each invocation appends a file entry (path, action, category)
to `signal_dir/outputs.json`. Follows the existing append pattern used by
`agentrelay-concern`. Data model: `OutputManifest` with `schema_version`
and `files` list of `OutputEntry` (path, action, category). Add instruction
guidance in templates telling agents to declare their outputs before
completing. No graph YAML changes yet — `inputs_from` and
`expected_outputs` are future PRs.

---

## PR plan

### PR A: Capture agent.log on task failure — Merged (#157)

- Branch: `feat/agent-log-on-failure`

`agent.log` (tmux scrollback) is only captured during teardown. When
`TearDownMode` is `ON_SUCCESS` and the task fails, no scrollback is written.

**Changes:**
- Extracted scrollback capture from `TmuxAddress.teardown()` into a new
  `capture_log(signal_dir)` method on `AgentAddress` / `TmuxAddress`.
- Added `TaskLogCapture` protocol in `task_runner/core/io.py` and
  `WorktreeTaskLogCapture` implementation in
  `task_runner/implementations/task_log_capture.py`.
- `StandardTaskRunner.run()` calls `_log_capture(runtime).capture_log(runtime)`
  unconditionally in the `finally` block before the `_should_teardown()` check.
- `TmuxAddress.teardown()` skips scrollback capture if `agent.log` already
  exists (idempotent).
- `_log_capture` added to `StepDispatch` tables alongside existing steps.

**Acceptance criteria:**
- [x] `agent.log` is captured regardless of teardown mode
- [x] Teardown mode still gates resource cleanup (pane destruction)
- [x] No double-capture when teardown also runs
- [x] `pixi run check` passes

---

### PR B: Retry agent awareness of previous attempts — Merged (#158)

- Branch: `feat/retry-agent-awareness`

When `attempt_num > 0`, the agent should know about prior attempts and where
to find their artifacts.

**Changes:**
- `src/agentrelay/agent_comm_protocol/templates.py` — added "Previous
  Attempts" section to `resolve_instructions()`, conditional on
  `manifest.attempt_num > 0`. Lists attempt directories with absolute paths,
  artifact filenames, and guidance to review prior scrollback and gate output.
- Added `_PREVIOUS_ATTEMPT_ARTIFACTS` tuple and `_previous_attempts_section()`
  helper function.
- Updated `docs/BACKLOG.md` to mark the retry agent awareness item as
  addressed.

**Acceptance criteria:**
- [x] Instructions include "Previous Attempts" section when `attempt_num > 0`
- [x] Section lists the correct `attempts/<N>/` paths and artifact names
- [x] No "Previous Attempts" section on first attempt
- [x] `pixi run check` passes

---

### PR C: CLI flag for fail-fast-on-workstream-error — Merged (#159)

- Branch: `feat/fail-fast-cli`

The `fail_fast_on_workstream_error` config field has no CLI or graph YAML
control.

**Changes:**
- `src/agentrelay/run_graph.py` — added `--no-fail-fast-on-workstream-error`
  boolean flag wired through `_build_config_from_args`. Graph YAML
  `fail_fast_on_workstream_error` field parsed via `TaskGraph.config` dict.
  Precedence: CLI > graph YAML > default (`True`).
- `src/agentrelay/orchestrator/orchestrator.py` — `OrchestratorConfig` now
  accepts `fail_fast_on_workstream_error` from the graph config.
- Updated `blocked_downstream.yaml` e2e graph to use the new field.
- Updated `docs/BACKLOG.md` and `CLAUDE.md` to reflect the new option.

**Acceptance criteria:**
- [x] `--no-fail-fast-on-workstream-error` disables the flag
- [x] Graph YAML `fail_fast_on_workstream_error: false` disables the flag
- [x] CLI flag overrides graph YAML setting
- [x] Default remains `True` when neither CLI nor YAML specifies
- [x] `pixi run check` passes

---

### PR D: Skip integration PR when all tasks are PR-less — Merged (#160)

- Branch: `feat/skip-empty-integration`

When every task in a workstream completes without a PR, the integration
branch has no commits ahead of the base branch. `gh pr create` fails.

**Changes:**
- `src/agentrelay/ops/git.py` — added `rev_list_count(repo_path, base, head)`
  function.
- `src/agentrelay/workstream/implementations/workstream_integrator.py` —
  `GhWorkstreamIntegrator.create_integration_pr()` checks `rev_list_count()`
  before calling `gh.pr_create()`. If zero commits ahead, calls
  `mark_merged()` directly and returns early.
- `src/agentrelay/orchestrator/orchestrator.py` — updated
  `_process_merge_ready_workstreams()` to handle workstreams that transition
  directly to MERGED (no PR_CREATED intermediate).
- `src/agentrelay/output/console.py` — added "skipped_integration" event
  display.

**Acceptance criteria:**
- [x] No `gh pr create` when integration branch equals base branch
- [x] Workstream reaches terminal success state without an integration PR
- [x] Workstreams with at least one PR-backed task still create integration PRs
- [x] `pixi run check` passes

---

### PR E: Output manifests and `agentrelay-declare` — Merged (#161)

- Branch: `feat/output-manifests`

Foundation for output-driven task composition. Agents declare what files
they created or modified via a structured manifest.

**Changes:**
- `src/agentrelay/agent_sdk/output_manifest.py` — `OutputEntry` and
  `OutputManifest` data models, `append_output()` function for atomic
  append to `outputs.json`.
- `src/agentrelay/agent_sdk/cli.py` — `agentrelay-declare` CLI entry point
  with `--path`, `--action`, `--category` flags.
- `src/agentrelay/agent_sdk/task_helper.py` — `TaskHelper.declare_output()`
  method wrapping `append_output()`.
- `src/agentrelay/agent_comm_protocol/templates.py` — added `outputs.json`
  to the Graph Awareness artifact listing; added `agentrelay-declare`
  guidance in the "Submitting Your Work" section.
- `docs/diagrams/uml/diagram-detailed.d2` — added `OutputEntry` and
  `OutputManifest` to the agent_sdk module diagram.
- Full design reference: `docs/discussions/OUTPUT_DRIVEN_COMPOSITION.md`.

**Acceptance criteria:**
- [x] `agentrelay-declare --path ... --action ... --category ...` appends
      to `outputs.json`
- [x] Multiple declarations accumulate correctly
- [x] `outputs.json` schema matches the design doc format
- [x] Instructions include guidance to declare outputs before completion
- [x] `pixi run check` passes

---

## Dependency ordering

PRs A through E were independent — no code dependencies between them.
Developed in parallel across five git worktrees. Merged sequentially
A→B→C→D→E. PR E required rebase after PRs A–D landed (one conflict in
`test_templates.py` — both PR B and PR E added tests to the same test
class, resolved by keeping both additions).
