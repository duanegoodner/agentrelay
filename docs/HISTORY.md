# Changelog

Chronological log of features and fixes merged into `main`. For full detail see
each PR on GitHub.

---

## 2026-03-03

### Demo YAML: `split_tdd_single.yaml` updated to three-node structured-roles graph — PR #42

Replaces the two-node split-TDD demo in `agentrelaydemos` with a three-node pipeline
that exercises the full set of structured-role features added in PRs #36–#41.

- **`graphs/split_tdd_single.yaml`** (in `agentrelaydemos`): three tasks —
  `write_roman_spec` (`role: spec_writer`), `write_roman_tests` (`role: test_writer`),
  `impl_roman` (`role: implementer`).
- **Features exercised:** `role:` key on plain tasks, `src_paths`/`test_paths` as
  structured lists, spec-in-source (docstrings as authoritative spec, no separate `.md`),
  `description:` omitted on `test_writer` and `implementer` tasks, dispatch-time path
  validation, MERGER agent reviews implementer PR for spec integrity, `design_concerns`
  mechanism available to implementer, `completion_gate` with `coverage_threshold: 95`,
  graph-level `verbosity: standard`.
- **`tdd_group` removed:** the new pipeline uses plain tasks with explicit roles instead
  of the `tdd_groups:` expansion macro.

`pixi run check` clean (no agentrelaysmall source changes in this PR).

**Key file:** `/data/git/agentrelaydemos/main/graphs/split_tdd_single.yaml`.

---

### Verbosity / ADR mechanism — PR #41

When a task's effective verbosity is above `"standard"`, the agent now writes an
ADR (Architecture Decision Record) to `docs/decisions/{task_id}.md` as part of its
normal commit. The final graph PR body lists all ADRs produced, and
`docs/decisions/index.md` is updated on the graph branch before the final PR is
created.

- **`_adr_step(task, graph) -> str`** (new, in `run_graph.py`): returns an empty
  string when effective verbosity is `"standard"`; otherwise returns a numbered
  step instructing the agent to write an ADR at `docs/decisions/{task.id}.md`
  with YAML front matter (`task_id`, `graph`, `role`, `date`, `verbosity`) and
  three standard sections (`## Context`, `## Decision`, `## Consequences`). At
  `"educational"` verbosity two additional sections are added (`## Key Concepts`,
  `## Alternatives Considered`). Always ends with `git add docs/decisions/{task.id}.md`.
- **`_effective_verbosity(task, graph) -> str`**: already present (PR 37 scaffold);
  now actively used by `_adr_step`.
- **All role prompt builders updated** (`_build_spec_writer_prompt`,
  `_build_test_writer_prompt`, `_build_test_reviewer_prompt`,
  `_build_implementer_prompt`, `_build_generic_instructions`): each accepts a new
  optional `graph: AgentTaskGraph | None = None` parameter and injects `_adr_step`
  between the "do the work" step and the "stage, commit, push" step. Step numbers
  shift accordingly when the ADR step is active.
- **`_build_task_instructions()`** updated: accepts `graph: AgentTaskGraph | None = None`
  and passes it to each role builder.
- **`_run_task()`** updated: passes `graph` to `_build_task_instructions()`.
- **`_run_graph_loop()`** updated: calls `write_adr_index_to_graph_branch()` before
  `create_final_pr()` when all tasks are done.
- **`scan_adr_section(graph_name, target_repo_root) -> str`** (new, in
  `task_launcher.py`): uses `git ls-tree` to list `docs/decisions/*.md` on the
  graph branch and `git show` to read their YAML front matter; returns a formatted
  `## ADRs produced in this run` section for the final PR body (empty string if no
  ADRs found).
- **`write_adr_index_to_graph_branch(graph_name, target_repo_root, worktrees_root)`**
  (new, in `task_launcher.py`): creates a temporary detached worktree on the graph
  branch, writes/updates `docs/decisions/index.md` (a markdown table of all ADR
  files with task_id, role, date columns), commits, and pushes. Silent no-op when
  no ADR files are present. Stale worktrees at the index path are cleaned up before
  and after the operation.
- **`_extract_front_matter_field(content, field) -> str | None`** (new private
  helper, in `task_launcher.py`): parses a YAML front-matter value from a markdown
  file string; used by `scan_adr_section` and `write_adr_index_to_graph_branch`.
- **`create_final_pr()`** updated: calls `scan_adr_section()` and appends the ADR
  listing to the PR body alongside the existing design-concerns section.

6 new tests (375 total, up from 369). `pixi run check` clean.

**Key files:** `run_graph.py`, `task_launcher.py`, `test/test_run_graph.py`.

---

## 2026-03-02

### MERGER role and `merge_history` — PR #40

Before the orchestrator calls `gh pr merge`, it now launches a MERGER agent to review
the PR in a tmux pane with CWD = `target_repo_root`. The agent checks spec integrity
for IMPLEMENTER PRs, logs findings to a graph-level `merge_history.md`, and returns
a verdict. The orchestrator merges only on approval.

- **`_build_merger_prompt(reviewed_task, pr_url, history_path) -> str`** (new, in
  `run_graph.py`): builds instructions for the MERGER agent. For IMPLEMENTER tasks
  with `src_paths`, includes a docstring integrity check (verifies docstrings were not
  materially altered — additive changes OK, changed signatures/Args/Returns/Raises NOT
  OK). Always instructs the agent to append a `## Review: {task_id} — {timestamp}`
  entry to `merge_history.md` and call `mark_done("approved")` or
  `mark_done("rejected: {reason}")` (never `mark_failed`).
- **`_launch_merger(reviewed_task, pr_url, graph, tmux_session) -> str`** (new, in
  `run_graph.py`): creates the merger signal dir at
  `.workflow/{graph}/merge_reviews/{task_id}/`, writes `task_context.json` and
  `instructions.md`, launches claude in a new tmux pane with CWD = `target_repo_root`,
  returns the pane_id.
- **`_run_task()`** updated: after `save_pr_summary` and before `merge_pr`, launches the
  MERGER, polls for its completion sentinel, reads the verdict, and closes the pane.
  If the verdict does not start with `"approved"`, sets status to `FAILED` and returns
  without merging.
- **`merge_history_path(graph_name, target_repo_root) -> Path`** (new, in
  `task_launcher.py`): returns `.workflow/{graph_name}/merge_history.md`.
- **`poll_for_completion_at(signal_dir, poll_interval) -> str`** (new async, in
  `task_launcher.py`): polls an arbitrary `signal_dir` for `.done` or `.failed`;
  variant of `poll_for_completion` that accepts a `Path` directly.
- **`launch_agent_in_dir(cwd, task_id, tmux_session, signal_dir, model) -> str`** (new,
  in `task_launcher.py`): launches a claude agent with a given CWD without requiring a
  worktree (used by MERGER which runs in `target_repo_root`).
- **`read_done_note_at(signal_dir) -> str`** (new, in `task_launcher.py`): reads line 2
  of `.done` from an arbitrary `signal_dir`; complement to `read_done_note`.
- **`close_pane_by_id(pane_id) -> str`** (new, in `task_launcher.py`): kills a tmux
  window by pane_id; used to close the MERGER pane after polling completes.
- **`write_merger_task_context(...)`** (new, in `task_launcher.py`): writes a minimal
  `task_context.json` for the MERGER agent (role=merger, task_id, signal_dir,
  graph_name, graph_branch, src_paths).

7 new tests (367 total, up from 360). `pixi run check` clean.

**Key files:** `run_graph.py`, `task_launcher.py`, `test/test_run_graph.py`.

### Gate failure recording in `merge_history.md`

When the orchestrator's completion gate fails, the failure is now appended to the
graph-level `.workflow/{graph}/merge_history.md` alongside MERGER review entries,
making the full PR lifecycle auditable from a single file.

- **`record_gate_failure(task_id, pr_url, gate_cmd, graph_name, target_repo_root)`**
  (new, in `task_launcher.py`): appends a `## Gate failure: {task_id} — {ts}` section
  with the PR URL, verdict, and gate command.
- **`_run_task()`** updated: calls `record_gate_failure()` in the gate-failure branch,
  between `save_pr_summary` and `task.state.status = TaskStatus.FAILED`.

2 new tests (369 total, up from 367). `pixi run check` clean.

**Key files:** `task_launcher.py`, `run_graph.py`, `test/test_task_launcher.py`.

---

### `design_concerns` mechanism — PR #39

Agents (primarily IMPLEMENTER) can now record concerns about the spec, tests, or
architecture during implementation. Concerns accumulate in a per-task
`design_concerns.md` file and are surfaced in the final graph PR body.

- **`WorktreeTaskRunner.record_concern(concern: str) -> None`** (new): appends a
  timestamped `## Concern recorded at {ISO timestamp}` entry to
  `$AGENTRELAY_SIGNAL_DIR/design_concerns.md`. Creates the signal dir and file if
  absent. Each call appends — multiple concerns are accumulated in one file.
- **`read_design_concerns(signal_dir: Path) -> str | None`** (new, in
  `task_launcher.py`): returns the stripped file contents if `design_concerns.md`
  exists and is non-empty, else `None`.
- **`create_final_pr()`** updated: scans `.workflow/{graph}/signals/*/design_concerns.md`
  before creating the final PR. If any tasks recorded concerns, a
  `## Design concerns raised during implementation` section is appended to the PR
  body with a `### {task_id}` subheading per task.
- **`_build_implementer_prompt()`** updated: step 4 now instructs the agent to call
  `record_concern()` for any concerns encountered during implementation (before the
  commit/push step). Steps 4→5 and 5→6 renumbered accordingly.
- **`_run_task()`** updated: reads `design_concerns.md` after gate passes; if
  concerns exist, calls `append_concerns_to_pr()` to add them to the task PR body
  before saving `summary.md` and merging. On gate failure, `summary.md` is saved
  immediately for debugging before the early return.
- **`append_concerns_to_pr(pr_url, concerns)`** (new, in `task_launcher.py`):
  fetches the current task PR body, appends a
  `## Design concerns raised during implementation` section, and updates the PR via
  the GitHub REST API. This ensures concerns appear in the task PR (merged into the
  graph integration branch) as well as in the final graph PR.
- **`save_pr_summary()`** call reordered: now called after concerns are appended
  (when gate passes) so `summary.md` always reflects the final PR body state.

9 new tests (360 total, up from 351). `pixi run check` clean.

**Key files:** `worktree_task_runner.py`, `task_launcher.py`, `run_graph.py`,
`test/test_worktree_task_runner.py`, `test/test_task_launcher.py`.

---

### Dispatch-time path validation — PR #38

Adds `validate_task_paths(task, worktree_path)` to `run_graph.py`. After a worktree is
created and before the agent is launched, the orchestrator checks that required files and
directories are present. This surfaces missing prerequisites (e.g. SPEC_WRITER stubs not
yet merged) with a clear error message rather than letting an agent fail mid-task.

- **`validate_task_paths(task, worktree_path) -> None`** (new): role-aware validation:
  - `SPEC_WRITER`: parent directory of each `src_paths` entry must exist; if `spec_path`
    is set, its parent directory must also exist.
  - `TEST_WRITER`: each `src_paths` file must exist (stubs from SPEC_WRITER must be
    merged in); parent directories of `test_paths` entries must exist.
  - `IMPLEMENTER`: each `src_paths` file must exist; each `test_paths` file must exist.
  - `MERGER`, `GENERIC`: no validation (pass unconditionally).
  - Raises `ValueError` with a message containing the task id and missing path.
- **`_run_task()`** updated: calls `validate_task_paths` after `create_worktree()` and
  before `write_task_context()`. On `ValueError`, prints the error, sets status to
  `FAILED`, and returns (worktree cleanup still runs via the `finally` block).
- **`test/test_path_validation.py`** (new): 14 unit tests covering all roles and both
  the happy path and error cases.

### SPEC_WRITER prompt, `_spec_reading_step`, and updated role prompts — PR #37

Implements the prompt-building layer for the structured-roles design. All new prompt
functions and helpers land in `run_graph.py`; no behaviour changes to the orchestrator
loop or data model.

- **`_effective_verbosity(task, graph) -> str`**: returns `task.verbosity or
  graph.verbosity or "standard"`. Scaffolded here for use by PR 6's ADR mechanism.
- **`_spec_reading_step(task) -> str`**: returns a "Before starting, read…" preamble
  when `task.src_paths` or `task.spec_path` is set; returns `""` otherwise. Injected
  into all non-SPEC_WRITER role prompts so agents always read the authoritative spec
  before acting.
- **`_build_spec_writer_prompt(task, graph_branch) -> str`** (new): dispatched for
  `AgentRole.SPEC_WRITER`. Instructs the agent to create stub files with full
  Google-style docstrings and `raise NotImplementedError` bodies, optionally write a
  supplementary `spec_path` .md index, verify importability, commit, push, and create
  a PR. Ends with "Do NOT implement any function or method bodies."
- **`_build_task_instructions()`**: SPEC_WRITER dispatch added at the top (before
  TEST_WRITER).
- **`_build_test_writer_prompt()`** updated: stub-creation step removed (SPEC_WRITER
  already produced stubs); spec-reading preamble injected; references `task.src_paths`
  ("already exist — do NOT create or overwrite them") and `task.test_paths` when set.
- **`_build_test_reviewer_prompt()`** updated: spec-reading preamble injected.
- **`_build_implementer_prompt()`** updated: spec-reading preamble injected; references
  `task.src_paths` and `task.test_paths` when set; adds explicit docstring-preservation
  instruction ("MUST preserve all existing docstrings … do NOT alter Args/Returns/Raises
  … docstrings are the specification contract").
- **`_build_generic_instructions()`** updated: spec-reading preamble injected immediately
  before "1. Do the work described in your task."

14 new tests (337 total, up from 323). 2 obsolete TEST_WRITER tests removed
(old stub-creation assertions no longer apply). `pixi run check` clean.

**Key file:** `run_graph.py`.

---

## 2026-03-01

### Structured roles, `src_paths`/`test_paths`/`spec_path`/`verbosity`, `SPEC_WRITER`/`MERGER` roles — PR #36

Core data model and YAML parser additions for the structured-roles design. No behavior
changes to existing agents; purely a foundation for subsequent PRs.

- **`AgentRole.SPEC_WRITER` and `AgentRole.MERGER`**: two new enum members support
  the spec-in-source and PR-review workflows described in the design plan.
- **`AgentTask.description` optional (default `""`)**: non-SPEC_WRITER roles can omit
  the description entirely; role + structured path fields carry the instruction content.
- **`src_paths: tuple[str, ...]`**: list of source files the task operates on. For
  SPEC_WRITER: files to create as stubs+docstrings. For IMPLEMENTER: files to fill in.
- **`test_paths: tuple[str, ...]`**: list of test files. TEST_WRITER creates them;
  IMPLEMENTER reads them as the test contract.
- **`spec_path: str | None`**: optional secondary spec `.md` for cases where the spec
  can't fit in source comments.
- **`verbosity: str | None`**: task-level verbosity override (`"standard"` /
  `"detailed"` / `"educational"`); `None` means inherit from graph.
- **`AgentTaskGraph.verbosity: str = "standard"`**: graph-level default verbosity
  parsed from YAML `verbosity:` key.
- **YAML `role:` key on plain tasks**: parser now maps `role: spec_writer` →
  `AgentRole.SPEC_WRITER` etc.; invalid values raise `KeyError` immediately.
- **`task_context.json`**: `write_task_context()` serialises all new fields.
- **`WorktreeTaskRunner`**: `from_config()` reads `src_paths`, `test_paths`,
  `spec_path`, and `verbosity` from `task_context.json`.
- **tdd_groups unchanged**: all new capabilities apply to plain tasks only.

46 new tests (323 total, up from 277). `pixi run check` clean.

**Key files:** `agent_task.py`, `agent_task_graph.py`, `task_launcher.py`,
`worktree_task_runner.py`, `test/test_agent_task.py`, `test/test_agent_task_graph.py`,
`test/test_task_launcher.py`, `test/test_worktree_task_runner.py`.

---

### Rename retries→attempts, `task_params`, `review_on_attempt` — PR #35

Three design improvements building on PR #34's gate machinery:

- **Rename "retries" → "attempts" throughout**: `max_gate_retries` →
  `max_gate_attempts`, `DEFAULT_GATE_RETRIES` → `DEFAULT_GATE_ATTEMPTS`,
  `gate_retries.log` → `gate_attempts.log`, `merge_pr(retries=6)` →
  `merge_pr(attempts=6)`. "Attempt 1" is unambiguous; "retry #1" is not
  (does it mean the first overall try or the second?).
- **`task_params: dict[str, Any]`** replaces the typed `coverage_threshold` field.
  A generic `{key}` → `str(val)` substitution dict avoids schema churn for future
  gate-command parameters. A new `_resolve_gate(task)` helper in `run_graph.py`
  performs the substitution before execution. `coverage_threshold` moves into
  `task_params` in both the YAML and `task_context.json`. YAML: `task_params:
  {coverage_threshold: 90}` (int preserved; coerced to str at substitution time).
- **`review_on_attempt: int = 1`** delays the self-review subagent until a specific
  gate attempt. Default `1` keeps the existing behavior (review before first attempt).
  Setting `review_on_attempt: 2` causes the review instruction to appear inside the
  gate loop instead of before it, worded as "Attempt 2+: before running the gate on
  attempt 2 or later, spawn a self-review subagent."

277 tests (up from 270). Demo graphs in `agentrelaydemos` updated to use
`max_gate_attempts` and `task_params:` blocks.

**Key files:** `agent_task.py`, `agent_task_graph.py`, `run_graph.py`,
`task_launcher.py`, `worktree_task_runner.py`.

---

### coverage_threshold, review_model, max_gate_retries, gate instruction hardening — PR #34

Three new optional `AgentTask` fields extend the `completion_gate` machinery:

- **`coverage_threshold: int | None`**: substituted into `{coverage_threshold}` in the
  gate command string; `run_completion_gate()` performs the substitution before exec.
- **`review_model: str | None`**: model ID for a self-review subagent that the agent
  spawns after completing its main work; included in `instructions.md` when set.
- **`max_gate_retries: int | None`**: per-task override for gate retry count; falls back
  to the graph-wide `max_gate_retries` YAML key (default `DEFAULT_GATE_RETRIES = 5`).

Gate instruction improvements to prevent agents from ignoring non-zero gate exits:
- "Exit code is the only accepted truth" paragraph explicitly overrides prior observations.
- `tee` + `PIPESTATUS[0]` pattern captures gate output to `gate_last_output.txt` while
  preserving the gate command's exit code through the pipe.
- Steps use "gate_exit is 0" / "gate_exit is non-zero" language to remove ambiguity.
- `mark_failed()` instruction references `gate_last_output.txt` for post-mortem.

`merge_pr()` now retries up to 6× (5 s delay) on transient GitHub "not mergeable"
responses that occur after `neutralize_pixi_lock_in_pr` pushes a new commit.

`WorktreeTaskRunner.record_gate_attempt(n, passed)` appends a timestamped JSONL
entry to `gate_retries.log` in the signal directory so retry history is auditable.

270 tests (up from 258). Demo graphs in `agentrelaydemos`:
`covg_and_retry_single.yaml`, `covg_and_retry_chained.yaml`.

**Key files:** `agent_task.py`, `agent_task_graph.py`, `run_graph.py`,
`task_launcher.py`, `worktree_task_runner.py`.

---

### AgentTask structure — completion_gate, agent_index, instructions.md channel — PR #33

Three coordinated improvements giving `AgentTask` more structure and reducing
reliance on large ephemeral f-string prompts:

- **`completion_gate`**: optional shell command on `AgentTask` (YAML `completion_gate:`
  key). The orchestrator runs it in the worktree after `.done` is seen but before
  merging the PR. Non-zero exit marks the task `FAILED` without merging. The agent
  also self-validates via a step included in `instructions.md` (defense-in-depth).
- **`agent_index`**: monotonically increasing integer assigned at dispatch time.
  Stored in `TaskState`, written to `task_context.json`, shown in log messages as
  `[a{N}]`. `AgentTaskGraph` gains `_agent_counter` + `next_agent_index()`.
- **`instructions.md` as the sole instruction channel**: all role-specific steps move
  to a file written in the signal directory before the agent launches. The tmux prompt
  becomes a minimal bootstrap string. `task_context.json` is now a rich structured
  record (`role`, `description`, `graph_branch`, `model`, `completion_gate`,
  `agent_index`). `WorktreeTaskRunner` gains the new fields and `get_instructions()`.
- **`BACKLOG.md`**: added 5 entries from a review of the original `agentrelay` project.

Scope: `AgentTask` and `GENERIC` role only. `TDDTaskGroup` intentionally untouched.

**Key files:** `agent_task.py`, `agent_task_graph.py`, `run_graph.py`,
`task_launcher.py`, `worktree_task_runner.py`.

---

## 2026-02-27

### Move `task_context.json` and `context.md` to `.workflow/` — PR #32

Both orchestration context files are now written under
`.workflow/<graph>/signals/<task-id>/` instead of the worktree root.

- **`task_context.json`**: was written to the worktree root (gitignored in target
  repos); now lives alongside the other signal files (`.done`, `.merged`, `agent.log`,
  etc.) and persists after worktree cleanup for easier debugging.
- **`context.md`**: was written to the worktree root with no gitignore entry, causing
  it to be picked up by `git add -A` and committed into PRs/`main`. Now also under
  `.workflow/`, so it is automatically gitignored and persists after teardown.
- **`AGENTRELAY_SIGNAL_DIR` env var**: exported by `launch_agent()` to the tmux pane;
  `WorktreeTaskRunner.from_config()` reads it to locate `task_context.json` without
  needing the worktree path. The `worktree_path` parameter of `from_config()` is removed.
- **`WorktreeTaskRunner.get_context()`**: now reads from `self.signal_dir / "context.md"`
  instead of `Path.cwd() / "context.md"`.

**Key files:** `task_launcher.py`, `worktree_task_runner.py`, `run_graph.py`.

---

### `reset_graph`: skip git reset on out-of-order runs — PR #29

`reset_graph.py` now automatically skips the `git reset --hard` + force-push step
when the recorded `start_head` is not an ancestor of the current `HEAD` (i.e. the
reset would move `main` forward and re-introduce already-reset commits). All other
cleanup still runs: open PRs are closed, remote task branches are deleted, leftover
worktrees are removed, and the `.workflow/` signal directory is cleared. The warning
message is updated to communicate that step 2 will be skipped rather than implying
the user must decide.

**Correct reset order:** most-recently-run graph first (reverse run order).
**Key file:** `reset_graph.py`.

---

### Typed `AgentTask.dependencies` and `TaskGroup` ABC — PR #28

Replaced string-based dependency references with typed object references throughout
the task model and graph builder.

- **`TaskGroup` ABC** added to `agent_task.py`: abstract frozen dataclass with `id`,
  `description`, and abstract `dependency_ids` property. Provides a common type for
  groups that expand to multiple tasks.
- **`AgentTask.dependencies`** changed from `tuple[str, ...]` to `tuple[AgentTask, ...]`;
  a `dependency_ids` computed property reconstructs the string tuple when needed. No
  call sites that already held `AgentTask` objects are broken.
- **`TDDTaskGroup`** (in `agent_task_graph.py`) extends `TaskGroup` with two typed dep
  fields: `dependencies_single_task: tuple[AgentTask, ...]` and
  `dependencies_task_group: tuple[TaskGroup, ...]`. Its `dependency_ids` property
  concatenates both.
- **Topological sort** (`_topo_sort`, Kahn's algorithm) added to `agent_task_graph.py`
  so the builder can construct frozen dataclasses in dependency-first order.
- **`_build_context_content()`** in `run_graph.py` simplified: no longer needs the
  graph as a parameter; iterates `task.dependencies` directly.
- **Tests** updated across `test_agent_task.py`, `test_agent_task_graph.py`, and
  `test_run_graph.py` — 176 tests total.

**Key files:** `agent_task.py`, `agent_task_graph.py`, `run_graph.py`.

---

### TDD workflow: `AgentRole`, `TDDTaskGroup`, role-specific prompts — PR #26

Added first-class TDD workflow support via a `tdd_groups:` YAML key that
auto-expands a single group entry into three sequential `AgentTask` objects —
test-writer, reviewer, and implementer — each dispatched as its own
worktree-PR-merge cycle.

- **`AgentRole`** enum (`GENERIC`, `TEST_WRITER`, `TEST_REVIEWER`, `IMPLEMENTER`)
  added to `agent_task.py`. `AgentTask` gains two new optional fields: `role`
  (default `GENERIC`) and `tdd_group_id` (default `None`) — fully
  backward-compatible with existing plain `tasks:` graphs.
- **`TDDTaskGroup`** dataclass added to `agent_task_graph.py`. It is a
  transient build-time concept: `from_yaml()` expands each group into
  `{id}_tests`, `{id}_review`, and `{id}_impl` `AgentTask` objects, then
  discards the group. `AgentTaskGraph` stays a flat `dict[str, AgentTask]`.
  The `tasks:` YAML key is now optional (a YAML with only `tdd_groups:` is valid).
- **Cross-group dependencies**: a dep string that matches another group's `id`
  resolves to `{dep}_impl` at build time; plain task IDs pass through unchanged.
- **Role-specific prompts**: `_build_task_prompt()` in `run_graph.py` dispatches
  to `_build_test_writer_prompt`, `_build_test_reviewer_prompt`,
  `_build_implementer_prompt`, or `_build_generic_prompt` based on `task.role`.
  Reviewer writes `{task.id}.md` (e.g. `stats_module_review.md`); implementer
  derives the review filename from `task.id`.
- **New test coverage**: new `test/test_run_graph.py`; additions to
  `test_agent_task.py` and `test_agent_task_graph.py` — 171 tests total.

**Key files:** `agent_task.py`, `agent_task_graph.py`, `run_graph.py`.

---

## 2026-02-26

### `BACKLOG.md` for quick idea capture — PR #25

Added `docs/BACKLOG.md` — a lightweight place to park ideas immediately without
interrupting a current task. Three sections: Features, Improvements, Ideas/Maybe.
Items graduate to `HISTORY.md` when done. Added a pointer in `CLAUDE.md` so new
sessions see it.

---

### Black + isort formatting pass — PR #24

Ran `pixi run check` (introduced in PR #23) across the whole codebase to apply
`black` line wrapping, blank-line normalization, and `isort` import ordering. No
functional changes — pure formatting.

---

### `CLAUDE.md`, `OPERATIONS.md`, `HISTORY.md`, `pixi run check` — PR #23

Three usability improvements landed together:

- **`CLAUDE.md`** at repo root: concise project reference auto-loaded by Claude Code
  at session start — commands, module map, signal files, YAML keys, and links to
  detailed docs.
- **`pixi run check`**: one command for format + typecheck + test — the canonical
  pre-PR verification step.
- **`docs/OPERATIONS.md`**: day-to-day running guide (running a graph, reading
  results, resetting after a run, common failure modes).
- **`docs/HISTORY.md`**: per-PR development log covering all 23 PRs to that point.

---

### Agent PR body capture + `summary.md` — PR #22

Agents are now prompted to write a real `## Summary` / `## Files changed` PR body
instead of the placeholder `"Automated task."`. Before merging, the orchestrator
fetches the body via `gh pr view --json body` and writes it to
`.workflow/<graph>/signals/<task-id>/summary.md`. The final status report shows
the summary path for each completed task.

**Key functions:** `save_pr_summary()` in `task_launcher.py`.

---

### Configurable tmux session + keep_panes + graph reset — PR #21

Three related usability improvements:

- **`tmux_session`** graph YAML field + `--tmux-session` CLI flag: controls which
  tmux session agent windows open in (default: `"agentrelaysmall"`).
- **`keep_panes`** graph YAML field + `--keep-panes` CLI flag: suppresses auto-close
  of agent tmux windows after task completion (useful for debugging).
- **`reset_graph.py`** module + `record_run_start()`: `python -m agentrelaysmall.reset_graph`
  reads `run_info.json` (written at graph start) and fully resets the target repo —
  closes open PRs, `git reset --hard` + force-push, deletes remote branches,
  removes worktrees and signal dirs.

---

## 2026-02-25

### pixi.lock neutralize-and-regenerate — PR #20

Eliminates pixi.lock merge conflicts when parallel agents both modify `pixi.toml`.
Before merging any PR, the orchestrator restores main's current `pixi.lock` into
the agent branch (neutralizing the agent's version), then after merging runs
`pixi install` and commits the freshly resolved lock file to main.

**Key functions:** `neutralize_pixi_lock_in_pr()`, `commit_pixi_lock_to_main()`.

---

### pixi.toml change detection — PR #19

After merging a PR, the orchestrator checks whether `pixi.toml` changed (via
`gh pr view --json files`). If so, it runs `pixi install` on the target repo to
keep the environment in sync.

**Key functions:** `pixi_toml_changed_in_pr()`, `run_pixi_install()`.

---

### Agent log capture + sibling repo support + `target_repo_root` rename — PR #18

- **Agent log capture:** after each task, the orchestrator captures the full tmux
  pane scrollback and writes it to `.workflow/<graph>/signals/<task-id>/agent.log`.
- **Sibling repo support:** `AgentTaskGraphBuilder.from_yaml()` accepts a
  `target_repo_root` override, enabling the orchestrator to drive tasks in a
  separate sibling repository (e.g. `agentrelaydemos`).
- **Rename:** `repo_root` → `target_repo_root` throughout for clarity.

---

### Bypass `--dangerously-skip-permissions` dialog — PR #17

Fixed the `send_prompt()` timing sequence to correctly navigate the Claude Code
confirmation dialog (Down + Enter) before sending the task prompt.

---

## 2026-02-24

### Multi-task async graph dispatch loop — PR #14

Core orchestrator loop (`run_graph.py`): loads a YAML graph, resolves task
dependencies, dispatches ready tasks concurrently via asyncio, polls for
completion signals, and merges PRs in order. Supports resuming interrupted runs
(signals persist across restarts).

---

### `pull_main` after merge — PR #11

After merging a task PR, the orchestrator fast-forwards the local main branch
(`git pull --ff-only`) so subsequent tasks branch from the correct HEAD.

---

### `.workflow/` gitignored; graph YAML convention — PR #12

All runtime state (`.workflow/`) is gitignored. Graph definitions (`graphs/`)
are version-controlled. This keeps the working tree clean and makes graph
definitions reviewable and reusable.

---

### PR workflow + timing fixes — PR #5

Agents create their own PRs and write the URL into the `.done` signal file.
Fixed timing delays in `send_prompt()` to ensure Claude finishes initializing
before the task prompt is sent.

---

### PATH propagation in `launch_agent` — PR #7

Exports the orchestrator's `PATH` into each agent's tmux environment so tools
like `gh`, `pixi`, and `claude` are available in agent bash subshells.

---

## 2026-02-23 — 2026-02-24 (initial build)

### Foundation — PRs #1–#3

- Project scaffolding: `pyproject.toml`, `pixi.toml`, source layout
- Documentation: `PROJECT_DESCRIPTION.md`, `WORKFLOW_DESCRIPTION.md`,
  `DESIGN_DECISIONS.md`, `REPO_SETUP.md`
- Core infrastructure: `AgentTask`, `AgentTaskGraph`, `AgentTaskGraphBuilder`,
  `WorktreeTaskRunner`, `task_launcher` functions, demo script, initial tests
