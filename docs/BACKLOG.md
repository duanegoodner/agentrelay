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

> **Priority**: Highly recommended as the next focus after sprint 2026-03-19
> completes. The ad-hoc template fixes in B1–BN will accumulate friction
> without a structured foundation; this item addresses the root cause.

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

## Agent Ops Concerns

Agents encounter operational issues during task execution — wrong build
commands, missing dependencies, permission errors, flaky tests, unexpected
repo layout — that are distinct from design concerns about the spec or code.
Even when the agent eventually works around the problem, the friction is
worth capturing so it can be fixed systematically.

- **New concern type**: `helper.record_ops_concern("description")` (or a
  `category` parameter on `record_concern`). Ops concerns are written to a
  separate file (e.g., `ops_concerns.log`) or tagged in the existing
  `concerns.log` so the orchestrator can distinguish them from design concerns.
- **Visibility**: Ops concerns surface in the integration PR body, console
  output, and post-run summary — separately from design concerns so they
  don't get lost in the noise.
- **Resolution paths**:
  - **Agent self-fix**: Agent records the concern and also applies a local
    workaround (e.g., switches to `pixi run`). The concern still gets logged
    so the root cause can be addressed.
  - **Orchestrator-driven fix**: Orchestrator aggregates ops concerns across
    runs and applies automated fixes (e.g., updating instructions templates,
    injecting env context).
  - **Human review**: Periodic triage of ops concerns to identify patterns
    and make durable fixes (CLAUDE.md updates, template changes, new backlog
    items).
- **Examples of ops concerns**: wrong Python/package manager invocation,
  shell escaping issues with TaskHelper, missing directories, import path
  confusion in worktrees, test collection failures from environment mismatch.

## Observability

- Standardize runtime artifacts (state snapshots, audit log, failure context).
- Define the minimal durable signals needed for reliable resume behavior.
