# Backlog

Near-term items for the current architecture track.

---

## Core Execution

- Expand orchestrator support for richer resume hooks and durable state checkpoints.
- **Human intervention on task failure**: When an agent declares a task failed,
  allow a human to fix the problem (e.g., correct an upstream file, adjust the
  worktree) and then trigger a retry of the failed task without restarting the
  entire graph. Currently the orchestrator treats agent-declared failure as
  terminal (unless `max_task_attempts` allows automatic retry). A manual retry
  mechanism — CLI command, signal file, or interactive prompt — would let
  humans unblock downstream tasks after fixing transient or environmental
  issues. Design this after gaining more experience with failure modes in
  e2e testing (PR C, PR D).

## Integration

- Map v01 graph/task-launch behavior onto current architecture interfaces.
- Define a migration path so prototype-only concepts land behind stable abstractions.

## Agent Isolation

- **Separate Linux user + scoped GitHub PAT for agent sessions**: Currently
  agents run as the human user, sharing SSH keys, `gh` credentials, and full
  filesystem access. A dedicated `claude-agent` OS user with a fine-grained
  GitHub PAT (scoped to the target repo, no admin privileges) would enforce
  identity separation, filesystem isolation via permissions, and prevent agents
  from merging PRs intended for human review. Bubblewrap (`bwrap`) or similar
  sandboxing can further restrict worktree visibility. See
  `docs/discussions/AGENT_ISOLATION.md` for full discussion of options
  (bwrap, Docker, git hooks, CODEOWNERS, deploy keys vs PATs).

## Extensibility

- Add additional `AgentFramework` implementations beyond `CLAUDE_CODE`.
- Expand `AgentEnvironment` beyond tmux when real use-cases are validated.

## Graph Execution

- **CLI flags for fail-fast config**: `OrchestratorConfig.fail_fast_on_internal_error`
  and `fail_fast_on_workstream_error` have no CLI flags. Add `--fail-fast-on-internal-error`
  and `--fail-fast-on-workstream-error` (boolean flags) to `run_graph.py` and wire
  through `_build_config_from_args`. Currently the only way to change these defaults
  is programmatically. Surfaced during PR C e2e testing: the `blocked_downstream`
  graph requires `--max-concurrency 2` as a workaround because the default
  `fail_fast_on_workstream_error=True` blocks new workstream preparation after a
  failure.
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

## Agent-Assisted Integration Branch Merging

Configurable merge strategies for integration PRs. Currently the orchestrator
creates integration PRs and leaves them for human review (`human` mode, since
PR A2). Additional strategies:

- **`auto`** — If no merge conflicts, merge automatically. If conflicts exist,
  fall back to human review.
- **`agent`** — If merge conflicts, launch a Claude Code agent in a tmux pane
  to resolve them. Require the test suite to pass before completing the merge.
  If the agent cannot resolve, fall back to human review.

Implementation sketch:
- Add a `merge_strategy` field to `WorkstreamSpec` or `OrchestratorConfig`.
- For `auto`: attempt `gh pr merge`, fall back to `human` on failure.
- For `agent`: create a tmux pane, instruct Claude Code to resolve conflicts
  and run tests. Agent uses TaskHelper-like API to signal success or failure.

Originally planned as PR F in sprint 2026-03-19, deferred because the retry
and gate work surfaced more foundational issues (signal cleanup, prepare-on-retry,
agent SDK retry support) that should be addressed first. Best tackled in a
sprint focused on integration reliability alongside the cross-workstream
dependency ordering and agent SDK retry items below.

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

### Observed agent workaround (PR C e2e testing, 2026-03-23)

Running `diamond_4_workstreams.yaml`, the `double_calc` agent discovered
that `base_calc.py` was missing from its worktree. It inspected available
branches with `git show`, found the code on the `base_calc` task branch,
and ran `git merge agentrelay/diamond-4-workstreams/base_calc --no-edit`
to pull the dependency's code into its own branch. This worked — but the
agent did not report an ops concern despite the workaround being a
significant deviation from the expected workflow. Implications:
- The workaround succeeded because worktrees share the git object store,
  so other workstreams' branches are locally available.
- Merging another task's branch directly could cause conflicts when
  integration PRs are merged to main (duplicate commits).
- The agent silently working around infrastructure gaps without raising
  ops concerns makes these gaps harder to detect systematically.

## Concern Guidance Level Experimentation

PR #129 shipped "prompted" guidance (cross-check steps in role templates) which
works reliably with Sonnet. Further investigation deferred:

- **Model matrix**: Test concern discovery across Haiku, Sonnet, Opus to see if
  the prompted guidance level generalizes or if weaker models need stronger
  prompting (checklist-style).
- **Guidance levels**: Compare minimal (no cross-check step), prompted (current),
  and checklist (explicit verification questions) to find the minimum effective
  guidance.
- **Results documentation**: Fill in the results matrix in `graphs/roles/README.md`
  with model × guidance level data.
- Experiment infrastructure is already in place: single-task graphs in
  `graphs/roles/experiments/`, BoundedQueue fixtures, `setup_fixtures.sh`.

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

## Multi-Model Support via Bifrost + OpenRouter

Use Bifrost (high-performance Rust gateway) as a local routing layer in front
of OpenRouter and direct provider APIs. This decouples the orchestrator from
any single LLM provider and enables per-task model/provider selection:
- Route high-reasoning tasks to Anthropic direct (Max plan), simple tasks
  to cheaper models via OpenRouter, and trivial tasks to local models.
- Automatic fallback: if one provider is down or rate-limited, Bifrost
  retries on another.
- Bifrost's "Code Mode" compresses tool definitions, reducing token usage.
- The orchestrator only talks to `localhost:8080`; routing/billing logic
  lives in Bifrost config.

Prerequisite: the current `AgentConfig.model` field already supports per-task
model selection. Extending to per-task provider/harness selection requires
adding a `provider` (and possibly `harness`) field to the graph YAML schema
and wiring environment variables at agent launch time.

See `docs/discussions/OPENROUTER_BIFROST_RUST.md` for full discussion.

## Rust Migration

Migrate the orchestrator from Python to Rust for type safety, fearless
concurrency, and resource efficiency. The orchestrator is not currently a
bottleneck (agents and network I/O dominate), but Rust's ownership model
enforces correct state management at compile time — valuable as the task
graph grows in complexity and the orchestrator gains more responsibilities
(retry logic, gate execution, agent-assisted merging).

Suggested phased approach:
1. **Engine proxy**: Rust CLI that handles LLM API calls (learn Rust I/O,
   JSON, env vars). Use `rig-core` crate.
2. **Graph runner**: Move DAG scheduling to Rust using `petgraph` (learn
   ownership, trait-based abstraction).
3. **Full harness**: Move tmux/process management to Rust with `tokio`
   (learn async, PTY handling).

Stay in Python while the design is still evolving rapidly; migrate when
state complexity or scale becomes a pain point.

See `docs/discussions/OPENROUTER_BIFROST_RUST.md` for full discussion.

## Agent Worktree Awareness

- **Agent navigates out of worktree**: During E2E testing (PR D, retry graph
  with Haiku), the generic-role agent was launched in the workstream worktree
  but used absolute paths to write files in the main repo and `cd`'d to the
  main repo for git operations. It committed to `main` instead of the task
  branch. The agent saw `/data/git/.../main` as the project root and ignored
  its actual CWD. Possible fixes: add explicit worktree guidance to agent
  instructions ("work in your current directory, do not navigate to other
  paths"), or include the worktree path in the manifest so agents can
  self-check. Observed with Haiku; may not affect stronger models.

## Agent SDK Retry Support

- **`agentrelay-complete` fails on retry when PR already exists**: On retry
  after gate failure, the PR from attempt 1 already exists. `agentrelay-complete`
  calls `gh pr create` which rejects the duplicate (`a pull request for branch
  ... already exists`). The agent must manually discover the existing PR URL
  and call `mark_done` directly. Fix: `agentrelay-complete` (or `create_pr`
  in `TaskHelper`) should detect the existing PR and reuse its URL instead of
  failing. Observed during PR D E2E testing with Sonnet — the agent worked
  around it by reading the SDK source, but this is fragile.

## Signal Directory Structure

- **Signal directory restructure**: Split `signal_dir/` into two named
  subdirectories — one for orchestrator-internal status tracking (currently
  `signal_dir/status/`) and one for agent-facing files (instructions, manifest,
  policies, .done, .failed, etc., currently direct children of `signal_dir/`).
  Gives each scope a clear name and prevents bugs like agent signals not being
  cleared on retry (fixed in PR D). Deferred because it touches every
  signal_dir consumer (agent SDK CLI tools, completion checker, preparer, gate
  checker, teardown, reset_graph).

## Diagram Rendering

- **`diagram-no-impl.d2` exceeds TALA layout size limit**: As the D2 diagram
  grows, the `diagram-no-impl` view (all types with collapsed implementations)
  fails to render with TALA: `Reached a bad state: Dimensions w:20515, h:30905
  reached after stage NodePlacement`. The other three views (detailed,
  no-private, standard) render fine. Options: split the diagram into
  sub-diagrams, reduce the no-impl view further, or switch to a different
  layout engine for that view. Observed during PR D.

## Observability

- Standardize runtime artifacts (state snapshots, audit log, failure context).
- Define the minimal durable signals needed for reliable resume behavior.
