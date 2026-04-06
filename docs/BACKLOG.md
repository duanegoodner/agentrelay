# Backlog

Near-term items for the current architecture track.

---

## Core Execution

- Expand orchestrator support for richer resume hooks and durable state checkpoints.
- **Human-triggered partial graph re-run**: Allow a human monitoring a graph
  execution to intervene and re-run a subset of tasks — for example, after
  reviewing a missed note that indicates a completed task's output is
  incomplete, or after manually fixing an upstream artifact. The mechanism
  could be a CLI command that accepts a list of task IDs to re-run, resets
  their status and worktrees, and resumes the orchestrator from that point.
  Differs from the existing `max_task_attempts` auto-retry in that it is
  human-initiated, post-completion, and may affect tasks that succeeded but
  produced insufficient output. Design after the basic context-sharing
  infrastructure (graph YAML delivery, `agentrelay-note`, missed notes
  detection) is in place and we have e2e experience with missed-note scenarios.
  See `docs/discussions/CONTEXT_SHARING.md`.
- **Orchestrator-driven partial re-run via LLM judgment**: Extend the above
  with an orchestrator capability to autonomously decide whether a missed note
  (or other runtime signal) justifies re-running part of the graph, without
  requiring human intervention. This would require the orchestrator to consult
  an LLM agent — either as an on-demand subprocess or as a persistent
  "planning agent" attribute on the orchestrator — to evaluate the missed note
  content and the affected task's output and produce a re-run recommendation.
  Prerequisite: human-triggered partial re-run (above) must exist first, as the
  orchestrator would use the same machinery. High complexity; defer until the
  simpler human-intervention mechanism is validated in practice.
  See `docs/discussions/CONTEXT_SHARING.md`.
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

- **Prototype feature audit**: Audit `src/agentrelay/prototypes/v01/`
  functionality, compare against the primary architecture, and determine if
  any features from the prototype are missing and ought to be added. The
  prototype was clumsy but had useful capabilities that shouldn't be
  accidentally dropped.

## Credential Management

- **Project-specific credentials files**: Currently `--credentials` takes a
  single path (default `~/.config/agentrelay/credentials.yaml`). Different
  projects may need different GitHub PATs (different orgs, different permission
  scopes). Credentials should stay completely outside the project directory —
  not rely on `.gitignore` to avoid accidental commits. Possible approaches:
  - **Named files under `~/.config/agentrelay/`**: e.g.,
    `credentials-agentrelaydemos.yaml`, `credentials-production.yaml`. Pass
    the right one via `--credentials`. Works today, no code changes.
  - **Graph-level `credentials` field**: graph YAML declares a profile name
    (e.g., `credentials: agentrelaydemos`) that resolves to a file under
    `~/.config/agentrelay/`. Makes graphs self-documenting; `--credentials`
    CLI flag overrides.
  - **Per-project config directory**: `~/.config/agentrelay/projects/<name>/`
    with its own `credentials.yaml`. More structured if per-project config
    grows beyond just credentials.
  - **Convention-based resolution**: auto-resolve based on target repo path
    or name, falling back to the global default.
- **Merge authority for isolated agents**: Currently, isolated (containerized)
  agents cannot merge PRs into main — the `elevated` token tier has no actual
  permission differentiation from `standard`. We need the ability to
  selectively grant isolated agents merge-to-main capability while still
  enforcing the same safeguards as non-isolated merge agents (no merge when
  design concerns are raised, concern-gated auto-merge).
  Possible approaches:
  - **GitHub App**: A GitHub App acts as a separate identity that can be
    added to a branch ruleset's bypass list, giving merge authority that
    personal PATs lack (fine-grained PATs all share the human user's
    identity). Authenticates via private key (`.pem`) → JWT → short-lived
    installation access token (~1 hour). Would require a
    `GitHubAppCredentialProvider` or refresh logic in
    `FileCredentialProvider`.
  - **Ruleset-scoped PAT**: If GitHub adds per-PAT bypass support in branch
    rulesets, a dedicated elevated PAT could be granted merge access
    directly. Simpler than a GitHub App but depends on GitHub feature
    availability.
  - **Orchestrator-mediated merge**: Instead of giving the agent direct
    merge credentials, the agent signals "ready to merge" and the
    orchestrator (running on the host with full credentials) performs the
    merge after validating concern status. This keeps merge authority
    entirely outside the container but requires a new signal/protocol.
- **4-layer credential inheritance**: Anthropic credential selection
  (API key vs OAuth) could follow the same graph → workstream → task →
  agent inheritance pattern used by `IsolationConfig`. Different tasks
  might use different credential tiers or auth methods (e.g., a
  cheap-model task using API key, a complex task using Max plan OAuth).
  Deferred until the consolidated credential YAML format is stable and
  real use cases justify per-task credential selection.
## Container Infrastructure

- **Agent framework pre-seed versioning**: The Docker image pre-seeds
  config files (`.claude.json`, `statsig.json`) and startup scripts
  (`claude-setup-credentials`, `claude-trust-workdir`) to suppress
  interactive prompts in ephemeral containers. These pre-seed schemes
  are tightly coupled to the agent framework version — a new Claude Code
  release could change onboarding flows, settings schema, or credential
  handling, breaking the existing scheme. On each new agent framework
  release, verify that the current pre-seed works. Consider maintaining
  a mapping of framework version → pre-seed scheme so older framework
  versions remain usable (useful if a new release introduces regressions
  and we need to pin to an older version). This also applies to any
  future agent frameworks beyond Claude Code.

## Extensibility

- `EnvCredentialProvider` — credential provider that reads from environment
  variables (e.g. `AGENTRELAY_PAT_READ_ONLY`, `AGENTRELAY_PAT_STANDARD`) for
  CI/CD environments where secrets come from the runner, not a local YAML file.
- Add additional `AgentFramework` implementations beyond `CLAUDE_CODE`.
- Expand `AgentEnvironment` beyond tmux when real use-cases are validated.
- **SDK tooling calibrated to agent capability**: The current SDK design
  assumes agents with strong tool use (file reads, path derivation, directory
  navigation) — e.g., Claude Code with Sonnet/Opus. Less capable agents
  (smaller local models, weaker tool use, smaller context windows) may need
  richer SDK commands to compensate. For example, an agent that struggles with
  path derivation would benefit from `agentrelay-read --task <id> summary`
  more than a capable agent that can just `cat` the file. As the system moves
  toward mixed-framework/mixed-model agent teams, evaluate whether the SDK
  surface area needs a "high-assistance" mode — more structured commands,
  pre-resolved paths, explicit guidance — alongside the current "minimal
  instructions + filesystem access" approach.
- **Decouple `task_helper.py` from GitHub CLI**: `TaskHelper.complete()`
  makes a direct `subprocess.run(["gh", "pr", "create", ...])` call,
  bypassing the protocol/ops abstraction used everywhere else in the
  orchestrator. This is the one spot where agent-side code is
  GitHub-specific without an abstraction layer. Evaluate whether to route
  through an ops function or make the PR creation mechanism configurable
  (e.g., via an env var or manifest field that tells the agent which
  platform CLI to use). Low urgency — only matters if/when supporting
  non-GitHub platforms.

## Task Graph Model

- **Multi-graph orchestration**: The current model runs a single `TaskGraph`
  per invocation — eagerly parsed, frozen, immutable. For larger or more
  dynamic workflows, a `MultiGraphOrchestrator` could coordinate multiple
  `TaskGraph` instances with dependency edges between them. Key aspects:

  - **Graph as the unit of lazy instantiation**: Rather than making individual
    tasks lazy (which would break the frozen model, validation-at-construction,
    and index precomputation), keep each graph eager/frozen/validated and move
    dynamism up one level. Graphs are instantiated on demand, run to completion,
    and released — preserving all the reliability properties of the current model.

  - **YAML as the inter-graph contract**: Each graph remains a YAML file. A
    planning agent (or human) produces YAML files that define downstream graphs.
    The multi-graph orchestrator validates and instantiates them. This gives
    auditability for free — every graph that ran is a YAML file on disk.

  - **Use cases**:
    - *Scale*: A project with hundreds of tasks split across multiple YAML files.
      The orchestrator instantiates graphs in dependency order, allowing completed
      graphs to go out of scope and free resources.
    - *Dynamic planning*: As a running graph produces artifacts (PR summaries,
      concerns, ops concerns), a planning agent monitors those outputs and
      constructs YAML files for follow-up graphs (refactors, test coverage,
      fixes for discovered problems). The planning agent's output is just YAML —
      clean separation between execution agents (do work) and planning agents
      (decide what work to do next).
    - *Concurrent graphs*: Multiple `TaskGraph` instances running simultaneously.
      The current infrastructure nearly supports this — worktrees and signal dirs
      are already namespaced by graph name (`.workflow/<graph>/`). The main
      challenge is merge ordering across graphs, which would need cross-graph
      gating similar to the existing cross-workstream gating.

  - **Resource handoff**: When a graph completes, it may need to hand off
    resources (worktrees, branch refs, merge state) to a downstream graph.
    Precise ownership transfer is critical — see Rust migration notes below.

  - **Comparison to LangGraph**: LangGraph uses a static-topology,
    dynamic-routing model — the compiled graph is immutable, and runtime
    dynamism comes from conditional edges, `Send` fan-out, and tool-calling
    loops within fixed node sets. A LangGraph maintainer noted that building
    a fresh subgraph inside a node at runtime is technically possible but
    "not the pattern LangGraph is optimized for." The multi-graph approach
    described here is flat composition (peer graphs with dependency edges),
    not nesting (subgraph owned by a parent node). This is closer to
    Airflow's DAG dependencies or Temporal's child workflows.

  - **Prerequisites**: The existing frozen/eager single-graph model is the
    right fit for current scale. Multi-graph orchestration is worth pursuing
    when the number of tasks per project exceeds what a single graph handles
    comfortably, or when dynamic planning (agents deciding what work comes
    next) becomes a real use case. A Rust migration (see below) would make
    the concurrency, ownership, and lifecycle management aspects
    significantly more tractable.

## Graph Execution

- **E2e graph for internal error fail-fast**: The `fail_fast_on_internal_error`
  CLI flag is implemented but has no e2e coverage. Internal errors require
  infrastructure-level failures (Docker, git, GitHub API), which are hard to
  trigger from a graph YAML alone. A graph referencing an invalid OCI image
  (e.g., nonexistent Docker image) would reliably raise during task
  preparation and could validate both `--fail-fast-on-internal-error` and
  `--no-fail-fast-on-internal-error` behavior. Belongs in `graphs/failure/`.
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

## Output-Driven Task Composition

- **Output manifests and `agentrelay-declare`**: Agents declare what files they
  created or modified, with semantic categories (stubs, tests, implementation,
  spec, etc.) via a new SDK command. Writes `outputs.json` to the signal
  directory. Foundation for `inputs_from` and `expected_outputs` below. Depends
  on e2e observation from sprint 2026-04-03 (agent graph awareness) to validate
  that agents use graph-wide context effectively.
- **`inputs_from` graph YAML extension**: Downstream tasks reference upstream
  outputs by task ID and optional category instead of hardcoded file paths.
  Orchestrator resolves inputs at prepare time by reading upstream
  `outputs.json`. Coexists with the existing `paths` field — both can be used
  on the same task.
- **`expected_outputs` graph YAML extension**: Structural expectations on task
  outputs (category + count bounds) validated pre-gate by the orchestrator.
  Agents raise concerns when their output structure deviates significantly.
- **Role template simplification**: As structured I/O contracts make more of
  the role-specific guidance derivable from data, simplify or generalize role
  templates. Preserve role-specific concern guidance.
- **Typed output categories**: `OutputEntry.category` is currently a free-form
  `str`. After sufficient e2e usage, review which categories agents actually
  use in practice and consider introducing an `OutputCategory` enum (with a
  fallback for custom values). Only worth doing once real usage patterns emerge.

Full design: `docs/discussions/OUTPUT_DRIVEN_COMPOSITION.md`.

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

## Framework-Specific Agent Configuration

When running agents with a specific framework (e.g., Claude Code), the
orchestrator could leverage framework-specific persistence and configuration
mechanisms to improve agent behavior:

- **CLAUDE.md**: Inject project-specific instructions into the worktree's
  CLAUDE.md (build commands, coding conventions, repo layout). More durable
  and framework-native than instructions.md for Claude Code agents.
- **Skills**: Pre-configure slash commands (e.g., `/commit`, `/test`) in the
  worktree so agents have standardized workflows without relying on
  instruction prose.
- **MEMORY.md**: Seed agent memory with project context, architecture notes,
  or lessons from prior runs. Could be populated from orchestrator state
  (upstream task summaries, concern history).
- **settings.json**: Per-task Claude Code settings (allowed tools, MCP
  servers, permission profiles).

The `AgentFrameworkAdapter` protocol is the natural integration point —
`ClaudeCodeAdapter.build_command()` already knows the worktree path and
could prepare framework-specific files before launch. Design question:
should this be adapter responsibility (framework-aware file setup) or a
separate step in the task preparer pipeline?

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

## Role-Specific Workflow Issues

### Spec writer: source-of-truth for specs

For specs that can be fully defined in docstrings/comments (e.g., Python
function/method signatures with docstrings), the source files should be the
single source of truth. Writing a separate `.md` spec file duplicates
information and risks drift. The spec_writer template should default to
source-only specs; the supplementary `.md` spec should be reserved for
complex specs that can't be captured in code comments alone (e.g., system
architecture, multi-component interactions).

### Skip integration PR when all tasks are PR-less

When every task in a workstream completes without a PR (e.g., a
workstream containing only `test_reviewer` tasks), the integration branch
has no commits different from `main`. `GhWorkstreamIntegrator` still
attempts `gh pr create`, which fails because GitHub rejects empty PRs.
The workstream should detect that no task produced a PR and skip
integration entirely — transition directly to MERGED (or a new terminal
state) instead of attempting a no-op integration PR.

### Refine integration PR body

Once all task types write `summary.md` files (PR-backed tasks via
orchestrator PR body fetch, PR-less tasks via `agentrelay-summary`),
decide how to incorporate agent-written summaries into the integration
PR body. Currently `_build_pr_body` in `GhWorkstreamIntegrator` uses
`TaskSummary` objects populated from task metadata (description, PR URL,
concerns) — it does not read `summary.md`. Options: add a `summary_text`
field to `TaskSummary` and populate it from `summary.md`, or include
summaries as collapsible sections. Consider whether PR-backed tasks
should prefer the agent-written summary over the fetched PR body, and
how to handle tasks that wrote both.

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

~~`auto` merge strategy~~ — resolved in PR #135 (`auto_merge` on `WorkstreamSpec`,
concern-gated). Remaining strategy:

- **`agent`** — If merge conflicts, launch a Claude Code agent in a tmux pane
  to resolve them. Require the test suite to pass before completing the merge.
  If the agent cannot resolve, fall back to human review.

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

**Multi-graph orchestration strengthens the case for Rust.** The single-graph
orchestrator is simple enough that Python asyncio works well, but coordinating
multiple concurrent graphs amplifies several concerns:

- **Ownership and lifecycle**: When a completed graph hands off resources
  (worktrees, signal dirs, branch refs, merge state) to a downstream graph,
  Python relies on convention to prevent stale references. Rust's ownership
  model makes invalid states unrepresentable — moving a `CompletedGraphResult`
  into a downstream graph's input is a compile-time guarantee.
- **Concurrent graph execution**: Multiple graphs with their own async
  scheduling, competing for shared resources (git repo, Docker networks, tmux
  sessions). Rust's `Send`/`Sync` bounds and `Arc<Mutex<T>>` enforce safe
  shared access at compile time, replacing Python's "hope the locks are right."
- **Resource cleanup**: A graph that crashes mid-execution must clean up
  containers, worktrees, branches, networks. Rust's `Drop` trait guarantees
  cleanup when ownership ends — even on panic. With multiple concurrent graphs,
  missed cleanup has multiplicative blast radius.
- **Cross-graph state machines**: The dispatch pipeline (DAG deps → workstream
  state → cross-workstream gates → blocked reasons) is already the most complex
  code. Lifting it to cross-graph scope means more state transitions and
  invariants. Rust's exhaustive `match` on enums catches unhandled cases at
  compile time; Python's `if/elif` chains silently skip them.
- **Scale**: Hundreds of tasks across multiple concurrent graphs means more
  polling loops, signal file checks, and subprocess calls. Python's GIL and
  asyncio overhead may matter. Rust's zero-cost abstractions and true
  parallelism via tokio handle this naturally.

**Thread allocation model (tokio):** The orchestrator is I/O-bound —
launching subprocesses, polling signal files, making GitHub API calls, and
waiting. Async is the natural fit. Use a tokio multi-thread runtime with a
small thread pool (~= CPU core count). Each orchestrator is a top-level
async task; within each, individual tasks are async futures that yield while
waiting on I/O. For multi-graph, all orchestrators share one tokio runtime
(the scheduler multiplexes them across the thread pool). If hard isolation
between orchestrators is needed (one panicking shouldn't affect another),
each can run on its own single-threaded tokio runtime in a dedicated OS
thread — but start with a shared runtime and isolate only if needed.
Thread-per-task is wasteful (30 threads mostly sleeping); thread-per-
orchestrator is reasonable but loses the benefit of tokio's work-stealing
across orchestrators.

Suggested phased approach:
1. **Engine proxy**: Rust CLI that handles LLM API calls (learn Rust I/O,
   JSON, env vars). Use `rig-core` crate.
2. **Graph runner**: Move DAG scheduling to Rust using `petgraph` (learn
   ownership, trait-based abstraction). Design with multi-graph composition
   in mind from the start — even if the initial port handles a single graph,
   the trait boundaries and ownership model should accommodate a future
   `MultiGraphOrchestrator` without major rework.
3. **Full harness**: Move tmux/process management to Rust with `tokio`
   (learn async, PTY handling).

Stay in Python while the design is still evolving rapidly; migrate when
state complexity or scale becomes a pain point.

**Transition timing**: The natural start point is after the agent isolation
sprint (2026-03-26) completes — at that point all core protocol boundaries
(`AgentSandbox`, `FrameworkConfigAdapter`, `CredentialProvider`, task runner
step protocols, workstream lifecycle) will be stable and validated e2e with
container execution. Phase 1 (engine proxy) could begin in parallel with
isolation PRs E/F since it's a standalone Rust learning project that doesn't
touch the orchestrator.

**Pre-migration gate: full e2e test pass.** Before starting any Rust work,
run e2e tests against every graph category (`smoke/`, `concerns/`, `roles/`,
`failure/`, `workstreams/`, `gates/`, `adr/`). Earlier sprint e2e runs
surfaced issues that may not all be captured in the backlog — a full pass
will rediscover them and ensure the Python implementation is a reliable
reference for the Rust port.

See `docs/discussions/OPENROUTER_BIFROST_RUST.md` for full discussion.

## Agent Context Sharing

A detailed design for targeted inter-agent messaging (`agentrelay-note`,
`agentrelay-read`, inbox/late-insights infrastructure, missed notes detection)
is documented in `docs/discussions/CONTEXT_SHARING.md`. The design was
produced during sprint planning for the context-sharing sprint (2026-04-03),
but the messaging infrastructure was deferred in favor of shipping graph YAML
delivery first and observing how agents use graph-wide awareness before
building the note system. Items below are ordered by expected implementation
sequence; all depend on e2e observation after graph YAML delivery ships.

- **`agentrelay-note` CLI + inbox + late insights**: Targeted cross-task
  messaging. Agent sends a note to a specific task's inbox; SDK routes to
  `late_insights/` if the target already completed. Structured checkpoints
  in instructions define when agents re-check their inbox. Full design in
  `docs/discussions/CONTEXT_SHARING.md` (PR B section).
- **Missed notes detection**: Orchestrator-side scan at task completion
  comparing inbox note mtimes against `.done` write time. Writes
  `missed_notes.log`, emits console event, includes warning in integration
  PR body. Does not block auto-merge by default. Full design in
  `docs/discussions/CONTEXT_SHARING.md` (PR C section).
- **`agentrelay-read` convenience command**: CLI for querying any task's
  artifacts (summary, concerns, done URL, inbox). Abstracts signal dir
  path derivation and validates task IDs against graph YAML. Full design
  in `docs/discussions/CONTEXT_SHARING.md` (PR D section).
- **OCI mount tightening**: Replace the broad `.workflow/<graph>/` read-write
  mount with granular read-only signals + specific write paths. Implement
  only if e2e testing shows agents writing to inappropriate signal files.
  Full design in `docs/discussions/CONTEXT_SHARING.md` (PR E section).
- **Per-task signal dir visibility restrictions**: For very large graphs, it may
  be useful to restrict what sections of the graph's signal store each agent can
  see — via filesystem ACLs or, in OCI isolation mode, container bind mount
  scoping. Implement after the basic pull-based context-sharing infrastructure
  is stable and validated in e2e.
- **`strict_notes` policy for missed-note blocking**: Opt-in flag (with
  per-workstream/task/agent scoping) that causes missed notes to block
  auto-merge. Default remains permissive. Depends on missed notes detection.
- **Concurrent note delivery via orchestrator injection**: If e2e observation
  shows that the structured-checkpoint inbox model misses too many notes sent by
  concurrent tasks, a future option is having the orchestrator watch inbox
  directories and inject a brief notification into the target tmux pane via
  `tmux send-keys`. Very unlikely to be needed.
- **Vector DB for semantic context retrieval**: The filesystem approach (graph
  YAML + signal dirs + plain text artifacts) is the right foundation — auditable,
  debuggable, zero-dependency, and natural for Claude Code agents. But it scales
  poorly for semantic queries ("which tasks dealt with caching?") and assumes
  agents are good at reading files. A vector DB layer would index the same
  artifacts that already exist on disk — the filesystem stays the source of truth
  and audit trail; the vector DB is an optional query accelerator. Strongest
  motivator: mixed-framework agent teams where some agents are local models with
  smaller context windows and weaker tool use. When all agents are Claude Code,
  "read this file" is solved; when some agents run via different harnesses, a
  framework-agnostic semantic query API becomes much more valuable. Don't design
  for it now, but ensure filesystem conventions established in graph YAML delivery
  don't accidentally preclude it.

## Agent Worktree Awareness

- ~~**Agent navigates out of worktree**~~: Addressed in PR #152 (worktree CWD
  guidance in agent instructions). OCI isolation hard-prevents at Level 2.

## Agent SDK Retry Support

- ~~**`agentrelay-complete` fails on retry when PR already exists**~~: Fixed in
  PR #149 (`create_pr()` probes for existing open PR and reuses it on retry).

## Retry Agent Context

- ~~**Retry agent awareness of previous attempt artifacts**~~: Addressed in
  sprint 2026-04-04 (PR B). Instructions now include a "Previous Attempts"
  section when `attempt_num > 0`, listing archived artifact directories and
  guidance to review prior failures before starting. Used instruction-level
  approach (consistent with other conditional sections); the broader question
  of instruction-level vs. structured manifest approach is tracked under
  "Agent Instruction Architecture" above.

## Signal Directory Structure

- **Signal directory restructure**: Split `signal_dir/` into two named
  subdirectories — one for orchestrator-internal status tracking (currently
  `signal_dir/status/`) and one for agent-facing files (instructions, manifest,
  policies, .done, .failed, etc., currently direct children of `signal_dir/`).
  Gives each scope a clear name and prevents bugs like agent signals not being
  cleared on retry (fixed in PR D). Deferred because it touches every
  signal_dir consumer (agent SDK CLI tools, completion checker, preparer, gate
  checker, teardown, reset_graph).

## Documentation

- **Target repo branch protection assumption**: agentrelay assumes target repos
  are configured with branch protection requiring at least one human approval
  before merging to main. This is load-bearing for the isolation model — it
  ensures PRs created by containerized agents (even those with elevated PATs)
  cannot be auto-merged without human review, since no PAT shares the human
  user's bypass identity in GitHub branch rulesets. Document this assumption
  explicitly in `ARCHITECTURE.md` and `SCHEMA.md`, and consider adding a
  preflight warning to `pixi run e2e-check` if the target repo lacks a
  qualifying protection rule.

- **API Reference mkdocs rendering issues**: Some API reference pages render
  poorly — `ops` page shows raw reStructuredText instead of formatted output
  (Sphinx-style `::` code blocks not recognized by mkdocstrings). Parts of
  the `run_graph` and `tools` pages also appear off. Likely cause: some
  module/package docstrings use Sphinx reStructuredText conventions instead
  of the Google-style docstrings expected by mkdocstrings. Fix: audit all
  `__init__.py` and module-level docstrings for Sphinx-isms (`::` literal
  blocks, `:param:` fields, `:type:` annotations) and convert to Google
  style.

## Observability

- Standardize runtime artifacts (state snapshots, audit log, failure context).
- Define the minimal durable signals needed for reliable resume behavior.
- **Orchestrator log files**: The orchestrator currently writes all output to
  the terminal (via `ConsoleListener`) with no persistent log file. For long
  runs or post-mortem debugging, a durable log is valuable. Design questions:
  one log per graph run (`.workflow/<graph>/orchestrator.log`), or a separate
  file per event type? Structured (JSON) or human-readable? Should subsume or
  complement the existing per-task `agent.log` (tmux scrollback). Consider
  alongside the "standardize runtime artifacts" item above — they are likely
  the same effort.
- **Orchestrator writes graph artifacts to the repo**: Give the orchestrator the
  ability to commit files to the target repo (or write to GitHub as issues,
  gists, PR comments, or wiki pages) as a first-class operation — separate from
  the per-task PR workflow. Use cases include: committing `late_insights.log`,
  graph run summaries, concern aggregates, and other non-code artifacts that
  should be durable and version-controlled but don't belong in a task PR.
  Design questions: should this be a new `ops/git.py` function
  (`commit_files_to_main`), a separate "graph artifact" workstream, or a
  GitHub-specific mechanism (issues, wiki)? The simplest starting point is
  probably a post-run commit to main by the orchestrator for a set of
  well-known artifact files (`.workflow/<graph>/late_insights.log`,
  `orchestrator.log`, etc.).
- **Isolation environment visibility in terminal output**: When agents
  run in OCI containers, the orchestrator's terminal output should
  surface container lifecycle events — container launch (image, name,
  network), container shutdown/removal, and any sandbox setup/teardown
  errors. Currently the `ConsoleListener` reports task-level events
  (started, succeeded, failed) but nothing about the isolation layer.
  Could be added via the existing `on_event` callback in
  `StandardTaskRunner` or as new event types in the listener protocol.
- **agent.log not captured on task failure**: `agent.log` (tmux pane
  scrollback) is only written during teardown, which runs conditionally
  based on `TearDownMode`. When a task fails and teardown is skipped
  (e.g., `ON_SUCCESS` mode), no `agent.log` is produced — so archived
  attempt directories from `reset_for_retry()` never contain the agent's
  scrollback. Fix: ensure scrollback capture always runs regardless of
  teardown mode, or make it a separate step from resource cleanup.
- **Per-attempt orchestrator event log**: Each task attempt should have a
  log file capturing the orchestrator-side events for that attempt — the
  same timestamped lines shown in the launch terminal (prepared, launched,
  waiting, gate running, gate failed, etc.) but scoped to that single
  attempt. Currently these events go to the terminal via `ConsoleListener`
  and are not persisted per-task. A per-attempt event log in
  `signal_dir/attempts/<N>/events.log` (or similar) would make post-run
  debugging much easier — you'd see both the agent's perspective
  (agent.log) and the orchestrator's perspective (events.log) for each
  attempt side by side.
