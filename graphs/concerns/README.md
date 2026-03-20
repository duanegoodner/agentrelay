# Concerns Tests

Tests for the agent concerns mechanism — agents write observations to
`concerns.log` in their signal directory, and the orchestrator captures them.

## Graphs

| Graph | What it tests |
|---|---|
| `log_concerns.yaml` | Agent writes concerns to concerns.log; verify they are captured in orchestrator result and shown in console output |

## Running

```bash
pixi run e2e graphs/concerns/log_concerns.yaml /path/to/target-repo -v
pixi run e2e-reset graphs/concerns/log_concerns.yaml /path/to/target-repo
```

## What to verify

- Agent writes one or more lines to `.workflow/<graph>/signals/<task-id>/concerns.log`
- Concerns appear in verbose console output
- Concerns appear in the post-run summary under "Concerns:"
- `result.task_runtimes[task_id].artifacts.concerns` is non-empty
