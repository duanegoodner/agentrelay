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

## Task Graph Awareness for Agents

Agents currently have no formal knowledge of their position in the task
graph. They see upstream task file changes via the shared worktree, and
`manifest.json` lists dependency IDs with descriptions, but nothing tells
the agent how to find upstream task artifacts (PR summaries, concerns,
signal files).

Ideas to explore:
- Wire up `context.md` with basic graph position info (dependency IDs,
  signal directory paths, PR URLs from completed upstream tasks).
- Give agents a tool or CLI command to query upstream task artifacts
  (e.g., `agentrelay-upstream <task_id>` returning summary, concerns,
  PR URL).
- The `context.md` infrastructure already exists in `WorktreeTaskPreparer`
  (field + write logic) and every role template says "If context.md
  exists, read it first" — just needs to be wired in `run_graph.py`
  or the orchestrator builder.

## Agent-Written Summaries for PR-less Tasks

Currently `summary.md` is only written for tasks that create a PR (the
orchestrator fetches the PR body). PR-less tasks (e.g., test_reviewer)
leave no summary of what they did. A CLI command like
`agentrelay-summary --message "..."` would let any agent write a summary
to its signal directory, independent of PR creation. This would make
PR-less task results visible to downstream agents, auditing, and the
integration PR body.

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
- **Trade-offs to balance**: The current approach — orchestrator-side objects
  produce deterministic instructions.md content, agents receive three auditable
  files (instructions.md, manifest.json, policies.json) — has clear strengths:
  - **Auditability**: What the agent saw is exactly what's on disk. No need to
    trace through override chains or resolve templates to understand what happened.
  - **Simplicity**: Adding new guidance (e.g., tool usage via `TOOL_REGISTRY`)
    is just programmatic input → rendered output. No new agent-side abstractions.
  - **Debuggability**: Three files to inspect per task. Nothing hidden.
  - The cost is **repetition** — every agent gets the full boilerplate even when
    most of it is identical across tasks in the same graph.
  - A more structured agent-side architecture would reduce repetition and enable
    agent-side interpretation of policies, but at the cost of auditability (need
    to trace what the agent actually did with the structured data) and complexity
    (agents need to understand a protocol, not just follow instructions).
  - **Recommendation**: Only pursue the structured approach when repetition
    becomes a measurable problem (token cost, context window pressure, or
    performance). The simpler rendered-output model is the right default.

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

~~Related: the TaskHelper completion step is fragile — agents struggle with
inline Python in zsh. A CLI wrapper would be more robust.~~ Resolved in
PR #120 (`agentrelay-complete`, `agentrelay-failed`, `agentrelay-concern`)
and PR #125 (`agentrelay-complete-no-pr`).

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

## Role-Specific Workflow Issues

### Spec writer: source-of-truth for specs

For specs that can be fully defined in docstrings/comments (e.g., Python
function/method signatures with docstrings), the source files should be the
single source of truth. Writing a separate `.md` spec file duplicates
information and risks drift. The spec_writer template should default to
source-only specs; the supplementary `.md` spec should be reserved for
complex specs that can't be captured in code comments alone (e.g., system
architecture, multi-component interactions).

### ~~Test reviewer: no-commit PR failure~~ — resolved in PR #125

### ~~Git push without upstream~~ — resolved in PR #125

### Task status semantics for PR-less completion

PR #125 introduced PR-less completion for review-only tasks, but reuses
`PR_MERGED` as the terminal success status even when no PR was created.
This works mechanically (downstream dependency checks and workstream
terminal state logic both key on `PR_MERGED`) but is semantically
misleading. A dedicated `COMPLETED` (or `COMPLETED_WITHOUT_PR`) status
would be more accurate. Changes needed:
- Add the new status to `TaskStatus` enum.
- Update `ALLOWED_TASK_TRANSITIONS`: `RUNNING` → `COMPLETED` (for
  PR-less) alongside the existing `RUNNING` → `PR_CREATED` path.
- Update all call sites that check `PR_MERGED` as "task succeeded" to
  also accept the new status (orchestrator dependency resolution,
  workstream terminal state, teardown mode, console output, integration
  PR body builder).
- Consider whether the new status needs its own signal file in the
  `status/` directory.

### Integration PR body quality

The integration PR body produced by `GhWorkstreamIntegrator` is
functional but not reader-friendly:
- **Long descriptions inlined verbatim**: Multi-paragraph task
  descriptions (e.g., from `spec_bounded_queue`) are dumped as-is,
  making the PR body wall-of-text. Should truncate or summarize.
- **Missing descriptions**: Tasks without an explicit `description` in
  the YAML show `(no description)`. Could fall back to the task ID or
  role name for context.
- **Formatting**: The body is a flat bullet list. Could use collapsible
  sections (`<details>`), tables, or better heading structure to match
  the quality of a typical agent-written PR description.
- **Concern presentation**: Concerns are listed per-task, which is good,
  but could benefit from a summary/highlight for cross-cutting concerns.

## Cross-Workstream Dependency Ordering

Two related questions about correctness when tasks span workstreams:

### Human merge and status signaling

Integration PRs are left for human merge (by design, since PR A2). When a
human merges a workstream's integration branch to main, does the orchestrator
need the human to write a status signal file (e.g., marking the workstream
as MERGED) so that downstream tasks/workstreams can be initiated? Or does the
orchestrator detect the merge via some other mechanism? If signal files are
needed, we should either automate this (GitHub webhook, polling) or document
the manual step clearly.

### Premature cross-workstream task dispatch

If Task A is in Workstream X and Task B is in Workstream Y, and B depends
on A: does the orchestrator wait until Workstream X's integration branch
has been merged to main before starting Task B? The concern is that the
orchestrator could see Task A as PR_MERGED (its task PR merged to the
integration branch) and dispatch Task B before Workstream X's integration
PR is merged to main — meaning Task B's worktree wouldn't have Task A's
changes. Need to verify whether the current orchestrator scheduling logic
prevents this, or if this is a gap.

## Implementer Test Coverage Threshold

The implementer role should optionally enforce a minimum test coverage level.
When configured, the implementer must verify that test coverage meets or exceeds
the threshold before completing its task — writing additional tests if needed.

- **Graph YAML configuration**: A `coverage` field on the task (or role-level
  default) specifying the minimum coverage percentage and optionally how to
  measure it (e.g., `pixi run coverage --branch`, a specific `pytest-cov`
  invocation, or a custom command).
- **Implementer template guidance**: When a coverage threshold is set, the
  instructions should tell the agent to run the coverage tool after
  implementation, check the result against the threshold, and iterate
  (write more tests, re-run) until coverage is satisfied.
- **Failure mode**: If the agent cannot reach the threshold after a reasonable
  effort, it should record a concern explaining the gap rather than silently
  shipping under-covered code.
- **Scope**: Coverage enforcement applies only to the files under the task's
  `paths.src` and `paths.test` — not the entire repo.

## Observability

- Standardize runtime artifacts (state snapshots, audit log, failure context).
- Define the minimal durable signals needed for reliable resume behavior.
