# YAML Schema Reference

This page documents the YAML schemas used by agentrelay: the **task graph**
schema (accepted by `TaskGraphBuilder`) and the **credentials** schema
(accepted by `FileCredentialProvider`).

---

## Task Graph YAML

Schema accepted by `agentrelay.task_graph.TaskGraphBuilder.from_yaml(...)`.

## Top-level object

Required keys:

- `name`: non-empty string.
- `tasks`: non-empty list of task objects.

Optional keys:

- `workstreams`: non-empty list of workstream objects.
- `max_workstream_depth`: integer > 0. Default: `1`.

Unknown top-level keys are rejected by `TaskGraphBuilder`.

### Operational keys

The following top-level keys are **not** part of the graph schema but are
recognized by `run_graph.py`, which extracts them before passing the dict to
`TaskGraphBuilder.from_dict()`:

- `tmux_session`: string. Override tmux session name for all agents.
- `keep_panes`: boolean. Leave agent tmux windows open after completion.
- `model`: string. Override model for all agents.
- `tools`: list of strings. Declared tool names (e.g., `["pixi"]`).
- `anthropic_credential`: string. Default Anthropic credential name from
  the credentials YAML. Overridden by `--anthropic-credential` CLI flag.

These can also be set via CLI flags (`--tmux-session`, `--model`,
`--anthropic-credential`). CLI flags take precedence over YAML values.

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

---

## Credentials YAML

Schema accepted by `agentrelay.sandbox.FileCredentialProvider`.  Passed to
`run_graph.py` via `--credentials <path>`.

### Top-level object

Optional keys (all are optional; an empty mapping `{}` is valid):

- `token_tiers`: mapping of tier name → env var mapping.
- `anthropic`: mapping of credential name → credential entry.
- `defaults`: mapping of env var name → value. **Deprecated** — a
  `defaults` section containing `ANTHROPIC_API_KEY` raises a migration
  error. Move Anthropic credentials to the `anthropic` section.

### token_tiers

Maps `TokenTier` values (`read_only`, `standard`, `elevated`) to
dictionaries of environment variables injected into sandboxed agents.
Typically used for GitHub PATs.

```yaml
token_tiers:
  read_only:
    GH_TOKEN: ghp_xxxx
  standard:
    GH_TOKEN: ghp_yyyy
  elevated:
    GH_TOKEN: ghp_zzzz
```

### anthropic

Named Anthropic credential entries.  Each entry has a `type` field
(`api_key` or `oauth`) and type-specific fields.

**`api_key` entry** — pay-per-token API key:

- `type`: `api_key` (required)
- `key`: string (required). The Anthropic API key.

**`oauth` entry** — Max plan OAuth credentials file:

- `type`: `oauth` (required)
- `path`: string (required). Path to `~/.claude/.credentials.json`.
  Tilde (`~`) is expanded.

```yaml
anthropic:
  dev_api_key:
    type: api_key
    key: sk-ant-xxxx
  max_plan:
    type: oauth
    path: ~/.claude/.credentials.json
```

### Selection rules

- If `anthropic` has exactly **one** entry, it is auto-selected.
- If **multiple** entries exist, use `--anthropic-credential <name>` on
  the CLI or `anthropic_credential: <name>` in the graph YAML.
- If no `anthropic` section exists, no Anthropic authentication is
  configured for containerized agents.

### Canonical examples

- API key only: [docs/examples/credentials-api-key.yaml](examples/credentials-api-key.yaml)
- OAuth only: [docs/examples/credentials-oauth.yaml](examples/credentials-oauth.yaml)
- Both (requires explicit selection): [docs/examples/credentials-both.yaml](examples/credentials-both.yaml)
