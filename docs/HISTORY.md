# Changelog

Chronological log of features and fixes merged into `main`. For full detail see
each PR on GitHub.

---

## 2026-03-01

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
