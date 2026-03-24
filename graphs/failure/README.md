# Failure Tests

Validate orchestrator behavior when tasks fail: signal handling, dependency
blocking, and continued execution of unaffected workstreams.

## Graphs

| Graph | Scenario | What it tests |
|---|---|---|
| `agent_fails.yaml` | Single task deliberately fails | `.failed` signal handling, error in console output, `COMPLETED_WITH_FAILURES` outcome |
| `blocked_downstream.yaml` | A fails, B blocked, C succeeds | Dependency blocking (`task_blocked` event), workstream isolation, continued execution |

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
