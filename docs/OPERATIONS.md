# Operations Guide

Day-to-day procedures for running and managing agentrelaysmall graphs.

---

## Running a graph

```bash
# From the orchestrator repo's main worktree
python -m agentrelaysmall.run_graph graphs/<name>.yaml

# Override tmux session (if your tmux session has a different name)
python -m agentrelaysmall.run_graph graphs/<name>.yaml --tmux-session <session>

# Keep agent tmux windows open after tasks complete (useful for debugging)
python -m agentrelaysmall.run_graph graphs/<name>.yaml --keep-panes
```

The graph YAML itself can also set `tmux_session:` and `keep_panes:` as defaults —
see [CLAUDE.md](../CLAUDE.md) for the YAML key reference.

### What to expect in the terminal

```
[graph] starting: demo  target: /data/git/agentrelaydemos/main
[graph] ready: write_greet_fn
[graph] dispatching write_greet_fn
[graph] write_greet_fn done — PR: https://github.com/org/repo/pull/5
[graph] merging PR for write_greet_fn: https://github.com/org/repo/pull/5
[graph] write_greet_fn merged
[graph] main fast-forwarded after write_greet_fn
[graph] ready: use_greet_fn
...
[graph] === final status ===
  write_greet_fn: done  summary → /data/git/.../signals/write_greet_fn/summary.md
  use_greet_fn: done  summary → /data/git/.../signals/use_greet_fn/summary.md
```

The `summary →` line only appears if the agent wrote a non-empty PR body.

---

## Reading results

After a run, each task's artefacts live under:

```
<target_repo>/.workflow/<graph>/signals/<task-id>/
```

| File | Contents |
|---|---|
| `.done` | Timestamp (line 1) + PR URL (line 2) |
| `.merged` | Timestamp of when the PR was merged |
| `agent.log` | Full tmux pane scrollback — everything the agent did |
| `summary.md` | The agent's PR body (Summary + Files changed sections) |

To read a task summary:

```bash
cat .workflow/demo/signals/write_greet_fn/summary.md
```

To tail an agent's live output while it runs:

```bash
tmux attach -t agentrelaysmall
# navigate to the task's window to watch it work
```

---

## Resetting after a run

The reset script returns the target repo to exactly the state it was in before
the graph ran. It reads `.workflow/<graph>/run_info.json` (written at graph start)
for the `start_head` SHA.

```bash
# From the orchestrator repo's main worktree
python -m agentrelaysmall.reset_graph graphs/<name>.yaml

# Skip the confirmation prompt
python -m agentrelaysmall.reset_graph graphs/<name>.yaml --yes
```

The reset:

1. Closes any open PRs on `task/<graph>/*` branches
2. `git reset --hard <start_head>` + `git push --force-with-lease origin main`
3. Deletes remote task branches
4. Removes local worktrees under `worktrees/<graph>/`
5. Deletes `.workflow/<graph>/` from the target repo

**Requirement:** `run_info.json` must exist (written when the graph starts).
If it is missing (e.g. the graph crashed before any tasks ran, or was run before
this feature existed), reset manually by identifying the pre-run HEAD from
`git log` and performing the steps above by hand.

---

## Pre-PR verification

Before creating a PR on agentrelaysmall itself:

```bash
pixi run check
```

This runs black + isort + pyright + pytest in one step.

---

## Common failure modes

**Agent window opens in the wrong tmux session**
Set `tmux_session:` in the graph YAML or use `--tmux-session` on the CLI.

**Agent pane closes before you can inspect it**
Re-run with `--keep-panes` or set `keep_panes: true` in the YAML.

**Task stuck in `running` state**
Check `agent.log` for errors. The agent may have failed to write `.done` or
`.failed`. You can manually write `.failed` to unblock the orchestrator:
```bash
echo "$(date -u +%FT%TZ)\nmanual abort" > .workflow/<graph>/signals/<task-id>/.failed
```

**PR merge failed (not mergeable)**
Usually a pixi.lock conflict if a parallel agent also modified `pixi.toml`.
The orchestrator handles this automatically via `neutralize_pixi_lock_in_pr`.
If it still fails, check the PR diff and resolve manually.

**`reset_graph` push rejected (`--force-with-lease` failed)**
Unrelated commits appeared on `origin/main` since the graph started. Do not
force-push over them. Resolve by rebasing or fast-forwarding manually before
retrying.
