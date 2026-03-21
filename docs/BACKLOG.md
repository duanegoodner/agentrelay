# Backlog

Near-term items for the current architecture track.

---

## Core Execution

- Expand orchestrator support for richer resume hooks and durable state checkpoints.

## Integration

- Map v01 graph/task-launch behavior onto current architecture interfaces.
- Define a migration path so prototype-only concepts land behind stable abstractions.

## Extensibility

- Add additional `AgentFramework` implementations beyond `CLAUDE_CODE`.
- Expand `AgentEnvironment` beyond tmux when real use-cases are validated.

## Graph Execution

- Auto-suffix for concurrent same-graph runs: append a timestamp or counter to
  `.workflow/<graph>` and `.worktrees/<graph>` directory names so multiple runs
  of the same graph can coexist. Requires updating `reset_graph` to discover
  suffixed directories.

## Removed Modules (revisit when needed)

- `spec/` (`SpecRepresentation` protocol, `PythonStubSpec`) — removed in PR #106 (feat/dependency-cleanup). Was intended to abstract spec file formats for spec-writer agents.
- `workspace.py` (`LocalWorkspaceRef`, `WorkspaceRef`) — removed in the same PR. Was intended to model workspace/repo references.
- View protocols (`TaskStateView`, `TaskArtifactsView`, `TaskRuntimeView`, `WorkstreamStateView`, `WorkstreamArtifactsView`, `WorkstreamRuntimeView`) — removed in the same PR. Read-only projections of mutable runtime types via structural typing (Protocol). Reintroduce when a consumer needs enforced read-only access to runtime state.

## Agent Instruction Architecture

- **Structured concern definitions**: Move concern qualification guidance from
  prose in role templates to a formal data field (e.g., a `concern_policy` in
  policies.json). This lets per-graph or per-task overrides control what agents
  treat as concern-worthy without editing templates.
- **Partially structured instructions.md**: Use heading levels and lists with a
  direct mapping from JSON/YAML, so parts of instructions.md are machine-readable
  and overridable rather than pure prose.
- **Default-with-overrides pattern**: Define default role instructions as templates
  that interpret structured data from manifest.json and policies.json. Provide a
  mechanism for per-task description overrides that layer on top of defaults.
- **Trade-off**: More abstraction improves flexibility but reduces auditability —
  tracing exactly what instructions an agent received requires resolving the
  template + overrides chain. Consider keeping a rendered snapshot of the final
  instructions in the signal directory (already done: instructions.md is written
  to disk after resolution).

## Agent Build Environment Awareness

Agents don't always know how to invoke commands in the target repo's build
system (e.g., using bare `python -m pytest` instead of `pixi run pytest`).
This causes import errors and wasted agent cycles. Three approaches, in
increasing sophistication:

- **Manual CLAUDE.md**: Target repo maintainer adds build system guidance
  (e.g., "use `pixi run` for all Python commands") to CLAUDE.md. Simple
  but ad-hoc — each repo needs manual setup and agents may still miss it.
- **Orchestrator-injected environment context**: Orchestrator detects the
  build system (e.g., `pixi.toml` present) and injects a "Build environment"
  section into instructions.md. Scales automatically to any target repo.
- **Automated detection and correction**: Introduce an "ops concern" type
  (distinct from design concerns) for environment/tooling issues. Agents
  raise ops concerns when they hit env problems. Options for resolution:
  - Agent self-corrects (retries with adjusted commands).
  - A dedicated agent periodically reviews ops concerns and applies fixes
    (e.g., updating CLAUDE.md, adjusting orchestrator templates).
  - Human reviews ops concerns and decides on fixes.

Related: the TaskHelper completion step is fragile — agents struggle with
inline Python in zsh (`pixi run python -c "..."` has shell-escaping issues).
A CLI wrapper (e.g., `agentrelay-complete --title "..." --body "..."`) would
be more robust than asking agents to write inline Python.

## Observability

- Standardize runtime artifacts (state snapshots, audit log, failure context).
- Define the minimal durable signals needed for reliable resume behavior.
