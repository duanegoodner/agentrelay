# Task Graph YAML Schema

This page documents the YAML schema accepted by
`agentrelay.task_graph.TaskGraphBuilder.from_yaml(...)`.

## Top-level object

Required keys:

- `name`: non-empty string.
- `tasks`: non-empty list of task objects.

Optional keys:

- `workstreams`: non-empty list of workstream objects.
- `max_workstream_depth`: integer > 0. Default: `1`.

Unknown top-level keys are rejected.

## Task object

Required keys:

- `id`: non-empty string, unique within `tasks`.

Optional keys:

- `role`: string. Defaults to `generic`. Accepts enum value (`implementer`) or enum name (`IMPLEMENTER`).
- `description`: string or `null`.
- `dependencies`: list of task IDs. Default: `[]`.
- `paths`: object with optional `src`, `test`, `spec`.
- `completion_gate`: string or `null`.
- `max_gate_attempts`: integer > 0 or `null`.
- `primary_agent`: object with optional `framework`, `model`, `adr_verbosity`, `environment`.
- `review`: object with required `agent` and optional `review_on_attempt` (default `1`).
- `workstream_id`: string or `null`. Defaults to `default`.

Validation rules:

- Dependency IDs must exist in `tasks`.
- Dependency graph must be acyclic.
- Duplicate dependency IDs in one task are rejected.
- Unknown task keys are rejected.

## Workstream object

Required keys:

- `id`: non-empty string, unique within `workstreams`.

Optional keys:

- `parent_workstream_id`: string or `null`.
- `base_branch`: non-empty string. Default: `main`.
- `merge_target_branch`: non-empty string. Default: `main`.

Validation rules:

- `parent_workstream_id` must reference an existing workstream ID.
- Workstream parent hierarchy must be acyclic.
- Workstream parent depth must be `<= max_workstream_depth`.

## Important defaulting behavior

1. If `workstreams` is omitted, a synthetic `default` workstream is used.
2. `task.workstream_id` defaults to `default`.
3. If `workstreams` is provided and tasks omit `workstream_id`, those tasks still resolve to `default`.
4. That means if you provide explicit `workstreams`, include `id: default` when you want omitted `workstream_id` tasks to remain valid.

## Agent/review defaults (current implementation)

- `primary_agent.framework`: `claude_code`
- `primary_agent.adr_verbosity`: `none`
- `primary_agent.environment`: tmux session `agentrelay`
- `review.review_on_attempt`: `1`

## Canonical examples

- Minimal graph: [docs/examples/minimal.yaml](examples/minimal.yaml)
- Parent/child workstreams: [docs/examples/workstreams.yaml](examples/workstreams.yaml)
- Mixed default + explicit workstreams: [docs/examples/mixed-default-and-explicit-workstreams.yaml](examples/mixed-default-and-explicit-workstreams.yaml)
