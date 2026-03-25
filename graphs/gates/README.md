# Completion Gate Tests

Validate that completion gates run after task completion and before PR merge.
Gates are shell commands (exit 0 = pass) that verify the agent's work.

## Graphs

| Graph | Scenario | What it tests |
|---|---|---|
| `pixi_run_test.yaml` | Gate passes on agent's code | Gate runs in worktree, passes, PR merges normally |

## Running

```bash
# Preflight check
pixi run e2e-check /path/to/target-repo

# Run
pixi run e2e graphs/gates/pixi_run_test.yaml /path/to/target-repo

# Reset
pixi run e2e-reset graphs/gates/pixi_run_test.yaml /path/to/target-repo
```

## What to verify after a run

### pixi_run_test

- `gate_last_output.txt` exists in the task's signal directory
- Gate output contains pytest results (pass/fail)
- Task reaches `PR_MERGED` status (gate passed, PR merged)
- Verbose console output shows `task_gate_running` and `task_gate_passed` events
- Integration PR exists for the workstream
