# Smoke Tests

Quick validation that the core execution paths work end-to-end.

## Graphs

| Graph | Topology | What it tests |
|---|---|---|
| `quick_chained.yaml` | A -> B (serial) | Dependency ordering, change propagation via shared workstream |
| `quick_parallel.yaml` | A \|\| B (parallel) | Separate workstreams, concurrent execution, independent merges |
| `inputs_from_chain.yaml` | A -> B (inputs_from) | Output-driven composition via `inputs_from` graph YAML extension |
| `pixi_run_test.yaml` | Single task + gate | Completion gate runs tests before PR merge; implementer role |

## Running

```bash
# Preflight check
pixi run e2e-check /path/to/target-repo

# Run
pixi run e2e graphs/smoke/quick_chained.yaml /path/to/target-repo
pixi run e2e graphs/smoke/quick_parallel.yaml /path/to/target-repo --max-concurrency 2

# Reset
pixi run e2e-reset graphs/smoke/quick_chained.yaml /path/to/target-repo
pixi run e2e-reset graphs/smoke/quick_parallel.yaml /path/to/target-repo
```

## What to verify after a run

- Each task's signal directory has `.done` (line 2 = PR URL)
- PRs target the correct integration branch
- Orchestrator wrote `.merged` after merging each task's PR
- Workstream integration branches merged to main
- `agent.log` captured for each task
- Target repo main branch contains all expected files
