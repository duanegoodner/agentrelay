# Workstream Tests

Validate workstream execution constraints: dependency fan-in (diamond topology)
and same-workstream serialization without explicit dependency edges.

## Graphs

| Graph | Topology | What it tests |
|---|---|---|
| `diamond_1_workstream.yaml` | A → B, A → C, B → D, C → D (1 workstream) | Fan-in scheduling: D waits for both B and C. All tasks share a worktree. |
| `diamond_4_workstreams.yaml` | A → B, A → C, B → D, C → D (4 workstreams) | Cross-workstream dependencies and code visibility. B and C run in parallel. |
| `serial_workstream.yaml` | A, B, C (no deps, same workstream) | Workstream serialization: tasks execute one at a time in topological order |

## Running

```bash
# Preflight check
pixi run e2e-check /path/to/target-repo

# Run
pixi run e2e graphs/workstreams/diamond_1_workstream.yaml /path/to/target-repo
pixi run e2e graphs/workstreams/diamond_4_workstreams.yaml /path/to/target-repo --max-concurrency 2
pixi run e2e graphs/workstreams/serial_workstream.yaml /path/to/target-repo

# Reset
pixi run e2e-reset graphs/workstreams/diamond_1_workstream.yaml /path/to/target-repo
pixi run e2e-reset graphs/workstreams/diamond_4_workstreams.yaml /path/to/target-repo
pixi run e2e-reset graphs/workstreams/serial_workstream.yaml /path/to/target-repo
```

## What to verify after a run

### diamond_1_workstream

- `base_calc` runs first (no dependencies)
- `double_calc` and `square_calc` each run after `base_calc` (serialized — same workstream)
- `combined_calc` runs last (waits for both `double_calc` and `square_calc`)
- `combined_calc` imports from both `double_calc` and `square_calc` successfully
- All tasks have `.done` and `.merged` signals
- Target repo main branch contains all four modules and their tests

### diamond_4_workstreams

- `base_calc` runs first (no dependencies)
- `double_calc` and `square_calc` run in parallel (separate workstreams)
- `combined_calc` runs last (waits for both)
- **Code visibility**: Each worktree branches off main independently. Downstream
  tasks may not see upstream tasks' code in their worktree. This graph tests
  whether that gap causes failures. See BACKLOG.md "Cross-Workstream Dependency
  Ordering" for discussion.

### serial_workstream

- Tasks execute in alphabetical ID order: `create_stack` → `extend_stack` → `use_stack`
- No two tasks run concurrently (same workstream enforces serialization)
- `extend_stack` modifies the file created by `create_stack`
- `use_stack` imports `Stack` with `push_many` and `pop_all` (added by `extend_stack`)
- All tasks have `.done` and `.merged` signals
- Target repo main branch has `stack.py` with all methods and `stack_utils.py`
