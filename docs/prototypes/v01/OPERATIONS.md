# Operations Guide

Day-to-day procedures for running and managing v01 agentrelay graphs.

---

## Running a graph

```bash
# From this repository root
pixi run python -m agentrelay.prototypes.v01.run_graph graphs/<name>.yaml

# Override tmux session
pixi run python -m agentrelay.prototypes.v01.run_graph graphs/<name>.yaml --tmux-session <session>

# Keep agent tmux windows open after tasks complete
pixi run python -m agentrelay.prototypes.v01.run_graph graphs/<name>.yaml --keep-panes
```

The graph YAML itself can also set `tmux_session:` and `keep_panes:` defaults.

### Graph YAML quick reference

```yaml
name: my-graph
target_repo: /path/to/target/repo
tmux_session: agentrelay   # optional; default "agentrelay"
keep_panes: false          # optional

tasks:
  - id: setup
    description: "Initial project scaffolding"
    dependencies: []
  - id: stats_module_tests
    description: >-
      Create src/pkg/stats.py with mean() and median() functions.
      Both raise ValueError on empty input.
      Tests go in tests/test_stats.py.
    role: test_writer
    dependencies: ["setup"]
  - id: stats_module_review
    description: "Review tests for stats module"
    role: test_reviewer
    dependencies: ["stats_module_tests"]
  - id: stats_module_impl
    description: "Implement stats module"
    role: implementer
    dependencies: ["stats_module_review"]
```

Each task gets its own worktree and PR.

---

## Reading results

After a run, task artifacts are written under:

```
<target_repo>/.workflow/<graph>/signals/<task-id>/
```

| File | Contents |
|---|---|
| `.done` | Timestamp (line 1) + PR URL (line 2) |
| `.merged` | Timestamp of successful merge |
| `agent.log` | Full tmux pane scrollback |
| `summary.md` | Agent PR body (if available) |

To view a summary:

```bash
cat .workflow/<graph>/signals/<task-id>/summary.md
```

To watch live output:

```bash
tmux attach -t agentrelay
```

---

## Resetting after a run

The reset script returns the target repo to the `start_head` recorded in
`.workflow/<graph>/run_info.json`.

```bash
pixi run python -m agentrelay.prototypes.v01.reset_graph graphs/<name>.yaml
pixi run python -m agentrelay.prototypes.v01.reset_graph graphs/<name>.yaml --yes
```

Reset performs:

1. Close open PRs on `task/<graph>/*` and `graph/<graph>` branches
2. Reset `main` back to `start_head` and push with `--force-with-lease` (unless out-of-order reset is detected)
3. Delete remote task/graph branches
4. Remove local worktrees under `worktrees/<graph>/`
5. Remove `.workflow/<graph>/`

---

## Common failure modes

**Agent window opens in wrong tmux session**
Use `--tmux-session` or set `tmux_session:` in YAML.

**Pane closes before inspection**
Use `--keep-panes`.

**Task appears stuck**
Inspect `agent.log`; if needed, write `.failed` manually in that task's signal directory.

**PR merge not mergeable**
Commonly a lockfile/content conflict. Review PR diff and rerun/reset as needed.

**Reset rejected (`--force-with-lease`)**
New commits landed on `origin/main` since run start; resolve manually before retrying reset.
