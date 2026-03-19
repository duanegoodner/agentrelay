# Migration Guide

This guide explains how to move from older task-only YAML files to the current
TaskGraph schema with workstreams and orchestrator-aware behavior.

## Scope

This migration guide targets `TaskGraphBuilder` YAML consumed by the current
architecture layer (`src/agentrelay/`).

It does not describe all prototype v01 runner fields. Operational top-level
fields (`tmux_session`, `keep_panes`, `model`) are not part of the graph
schema — they are extracted by `run_graph.py` before `TaskGraphBuilder`
parses the YAML. See [SCHEMA.md](SCHEMA.md) for details.

## Migration checklist

1. Keep top-level `name` and `tasks`.
2. Optionally add top-level `workstreams`.
3. Add `workstream_id` per task when tasks should run in non-default workstreams.
4. Add `max_workstream_depth` if you need hierarchy depth > 1.
5. Remove unknown keys not in the current schema.

## Before/after: task-only graph

Before (already valid in current schema):

```yaml
name: simple

tasks:
  - id: write_spec

  - id: implement
    dependencies: [write_spec]
```

After: unchanged required for migration. This is still supported and maps to a
synthetic `default` workstream.

## Before/after: introducing workstreams

Before:

```yaml
name: feature-a

tasks:
  - id: write_spec
  - id: implement
    dependencies: [write_spec]
```

After:

```yaml
name: feature-a
max_workstream_depth: 2

workstreams:
  - id: feature_a
    base_branch: main
    merge_target_branch: main
  - id: feature_a_impl
    parent_workstream_id: feature_a
    base_branch: feature_a
    merge_target_branch: feature_a

tasks:
  - id: write_spec
    workstream_id: feature_a
  - id: implement
    dependencies: [write_spec]
    workstream_id: feature_a_impl
```

## Orchestrator behavior to account for

When migrating YAML, keep these execution rules in mind:

1. Dependency scheduling is still task-DAG based.
2. Workstream gate: only one active task per workstream at a time.
3. Parent/child gate: child workstream tasks wait until parent workstream is `MERGED`.
4. `TaskRunner.run(...)` returns `FAILED`: expected task-level failure. Retry policy may apply (`max_task_attempts`).
5. `TaskRunner.run(...)` raises: internal/system failure. Orchestrator records traceback and fail-fast behavior applies.

## Tear down policy

`OrchestratorConfig.task_teardown_mode` forwards directly to `TaskRunner.run(...)`:

- `always`
- `on_success`
- `never`

Use `never` for debugging sessions where agent resources (for example tmux panes)
should remain available after a run.

## Validation tip

Use these commands after migration:

```bash
pixi run pytest test/test_task_graph_builder.py
pixi run pytest test/test_orchestrator.py
pixi run docs-build
```
