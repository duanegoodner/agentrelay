# Changelog

Chronological log of features and fixes merged into `main`. For full detail see
each PR on GitHub.

---

## 2026-02-26

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
