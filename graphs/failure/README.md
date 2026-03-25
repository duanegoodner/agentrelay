# Failure Tests

Validate orchestrator behavior when tasks fail: signal handling, dependency
blocking, and continued execution of unaffected workstreams.

## Graphs

| Graph | Scenario | What it tests |
|---|---|---|
| `agent_fails.yaml` | Single task deliberately fails | `.failed` signal handling, error in console output, `COMPLETED_WITH_FAILURES` outcome |
| `blocked_downstream.yaml` | A fails, B blocked, C succeeds | Dependency blocking (`task_blocked` event), workstream isolation, continued execution |
| `retry_on_gate_failure.yaml` | Gate always fails, orchestrator retries | Deterministic gate failure (nonexistent test file) → retry → exhaustion → `COMPLETED_WITH_FAILURES` |

## Running

```bash
# Preflight check
pixi run e2e-check /path/to/target-repo

# Run
pixi run e2e graphs/failure/agent_fails.yaml /path/to/target-repo
pixi run e2e graphs/failure/blocked_downstream.yaml /path/to/target-repo --max-concurrency 2  # required

# Reset
pixi run e2e-reset graphs/failure/agent_fails.yaml /path/to/target-repo
pixi run e2e-reset graphs/failure/blocked_downstream.yaml /path/to/target-repo

# Gate retry (requires --max-task-attempts 2)
pixi run e2e graphs/failure/retry_on_gate_failure.yaml /path/to/target-repo --max-task-attempts 2
pixi run e2e-reset graphs/failure/retry_on_gate_failure.yaml /path/to/target-repo
```

## What to verify after a run

### agent_fails

- `.failed` signal file exists in `deliberate_fail` signal directory (line 2 = reason)
- Console output shows the failure reason
- Orchestrator outcome is `COMPLETED_WITH_FAILURES`
- No `.done` or `.merged` signal files

### blocked_downstream

- `fails_first` has `.failed` signal with reason
- `blocked_by_first` is marked FAILED with `task_blocked` event (message: "dependency 'fails_first' failed")
- `independent_success` has `.done` signal with PR URL and `.merged` signal
- Orchestrator outcome is `COMPLETED_WITH_FAILURES` (not fatal — independent task succeeded)
- Integration PR exists for `ws_independent` workstream

### retry_on_gate_failure

- Run with `--max-task-attempts 2`
- Agent creates a simple greeting function, signals `.done`
- Gate runs `pixi run pytest test/test_nonexistent.py -q` — always fails (file doesn't exist)
- Orchestrator retries (attempt 2), gate fails again
- `gate_last_output.txt` in signal directory contains gate error output
- Console shows `task_gate_running` and `task_gate_failed` events
- Final outcome is `COMPLETED_WITH_FAILURES`
