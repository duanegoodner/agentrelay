# Backlog

Near-term items for the current architecture track.

---

## Core Execution

- ~~**Decouple `run_graph.py` from infrastructure implementation details**~~:
  **Resolved** in PR #199. `SandboxInfrastructureManager`,
  `SessionResolver`, and `RunRepoManager` protocols eliminate all
  `ops.docker`, `ops.tmux`, and `ops.git` imports from `run_graph.py`.
- Expand orchestrator support for richer resume hooks and durable state checkpoints.
- **Graph resumption across orchestrator runs**: When a graph is re-launched
  and `.workflow/<graph>/` already exists from a previous run, the orchestrator
  should probe the actual state — branches, PRs (open/merged/closed), signal
  files — and reconcile with the DAG to determine what remains. Completed
  tasks (merged PR or `.done` + open PR) are skipped; failed tasks are retried;
  unstarted tasks proceed normally. This replaces the current "refuse and tell
  the user to reset" behavior with intelligent resumption. Distinct from
  intra-run retry (`max_task_attempts`) which archives attempt artifacts within
  a single orchestrator session. Touches orchestrator dispatch, signal
  detection, and branch/PR probing. Consider implementing before the Rust
  migration: the Python version will be the public-facing testing ground for
  early users during the conversion, and "reset and re-run the entire graph
  because task 8 failed" is a poor first experience. Weigh against the risk
  of scope creep delaying the Rust timeline.
- **Per-run worktrees / preserving interrupted agent work**: Currently
  worktrees live at `.worktrees/<graph>/<ws-id>/` and are shared across
  runs. An alternative model would make worktrees per-run
  (`.worktrees/<graph>/runs/<N>/<ws-id>/`), giving each run a completely
  clean worktree and preserving prior runs' worktrees as read-only
  artifacts. This would enable agents to inspect what a previous run's
  agent did in the worktree (WIP commits, partial changes) without the
  complexity of preserving the live worktree state across restarts.
  **Skepticism**: unclear whether this would ever be worthwhile. The
  current shared-worktree model works well — PR D makes preparation
  idempotent for reuse, and agent instructions can reference prior run
  artifacts (logs, concerns, signal files) without needing the worktree
  itself. Per-run worktrees would increase disk usage, change the
  worktree lifecycle model, and touch significant plumbing. The main
  motivation (agent visibility into prior work) can likely be addressed
  more cheaply by surfacing prior run artifacts in agent instructions.
  Don't rule it out, but the bar for justifying it is high.
  **Note on uncommitted work (discovered in PR E e2e testing,
  2026-04-16):** Preserving *uncommitted* work from an interrupted agent
  is trivially easy — just skip the `git clean -fd` that
  `_reset_stale_worktree_branches()` runs during resume. Untracked files
  survive branch switches naturally. However, this only works cleanly
  when the interrupted agent made *no commits*. If the agent committed
  some work and then had uncommitted changes on top, the resume path
  creates an incoherent state: the uncommitted files survive (untracked),
  but the committed files are lost (the branch is force-created from the
  integration branch, overwriting the old task branch). The new agent
  would see partial artifacts without the committed foundation they
  depend on. Per-run worktrees would solve this by preserving the entire
  worktree (committed + uncommitted) as a read-only artifact, but that's
  a much larger change. For now, `git clean -fd` (always discard) is the
  safe default.
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
- **Rewind completed task in place**: Redo a specific completed task
  (e.g., task B in A → B → C) without disturbing downstream tasks (C)
  that were built on its output. The agent re-runs on the integration
  branch and produces a "fixup" PR that layers on top of the existing
  history rather than replacing it. Unlike `reset-to --after task-a`
  (which peels B and C, then re-runs both), rewind preserves C's work.
  Useful for small corrections ("B forgot a docstring," "B's test has a
  typo") where re-running downstream tasks is wasted effort.
  **Value: medium.** Saves agent compute on large graphs when a small
  fix is needed to an early task. Most impactful when graphs are long
  (many tasks after the one being fixed) and the fix is genuinely
  non-breaking.
  **Difficulty: high.** Three hard problems: (1) the git mechanics —
  the agent needs to work on a branch that already has C's commits on
  top, producing a patch that fits between B and C conceptually but sits
  after C in git history; (2) safety validation — the system must either
  verify that B's changes don't conflict with C's work (hard to define
  precisely) or trust the user's judgment; (3) updated `resolved.json`
  — B's frozen record needs to be updated without invalidating C's
  record, which assumed the original B. Benefits from the Rust state
  machine architecture where these invariants can be encoded in types.
  Prerequisite: the stack-based undo model from the graph resumption
  sprint (2026-04-12) provides the foundational `resolved.json` records
  and execution graph concepts this feature would build on.
- **Human intervention on task failure**: When an agent declares a task failed,
  allow a human to fix the problem (e.g., correct an upstream file, adjust the
  worktree) and then trigger a retry of the failed task without restarting the
  entire graph. Currently the orchestrator treats agent-declared failure as
  terminal (unless `max_task_attempts` allows automatic retry). A manual retry
  mechanism — CLI command, signal file, or interactive prompt — would let
  humans unblock downstream tasks after fixing transient or environmental
  issues. Design this after gaining more experience with failure modes in
  e2e testing (PR C, PR D).
- **Tmux kickoff send_keys may not auto-submit in newer Claude Code versions**:
  Observed in e2e testing (2026-04-13, Claude Code 2.1.105) that
  `tmux send_keys ... Enter` types the kickoff prompt but does not submit
  it — the agent sits idle until a human presses Enter in the tmux pane.
  Likely caused by a Claude Code update changing the default prompt
  submission behavior. Investigate whether Claude Code now requires
  double-Enter, Ctrl+Enter, or a different key to submit. Fix in
  `TmuxTaskKickoff.kickoff()` or `ops/tmux.send_keys()`. May also need
  to update the OCI container's pre-seeded Claude Code configuration.

## Integration

- **Local-only execution mode (no remote repository)**: The protocol layer
  (`TaskMerger`, `WorkstreamIntegrator`, `IntegrationMergeChecker`,
  `IntegrationAutoMerger`) isolates the orchestrator from GitHub *specifically*,
  but still assumes *some* remote exists — PR creation, PR merge, push/fetch
  are baked into the protocol method signatures and the `PR_CREATED`/`PR_MERGED`
  status model.  A truly local-only mode (no remote, no PRs) would require:
  - Local-merge `TaskMerger` that merges task branches into the integration
    branch directly (git merge, no PR).
  - Local-merge `WorkstreamIntegrator` that merges integration branches into
    the target branch directly.
  - Agent SDK `complete()` path that commits and signals done without calling
    `gh pr create`.
  - Status flow change: tasks would skip `PR_CREATED` and go directly to
    `PR_MERGED` (or a new `MERGED` status).
  - `ops/git.py` operations that currently hardcode `origin` would need to
    become no-ops or conditional.
  This is a different axis than GitHub→GitLab portability (which the current
  protocol layer supports via new `Gh*`-style implementations).  Design
  deliberately rather than shoehorning into existing protocols.
  Additionally, `agent_sdk/task_helper.py` calls `gh` directly — it's the
  one place where platform coupling bypasses the protocol layer.  Decoupling
  it was already noted as a backlog item (see platform coupling note in
  MEMORY.md).
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

- ~~**OCI container not removed on task failure (retry name conflict)**~~:
  **Resolved** in PR D (sprint 2026-04-09). Attempt-indexed container and
  tmux window naming prevents collisions. Sandbox teardown wired into
  `WorktreeTaskTeardown` behind the `_should_teardown()` gate.
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
  preparation and could validate both `--fail-fast-internal` and
  `--no-fail-fast-internal` behavior. Belongs in `graphs/failure/`.
- Auto-suffix for concurrent same-graph runs: append a timestamp or counter to
  `.workflow/<graph>` and `.worktrees/<graph>` directory names so multiple runs
  of the same graph can coexist. Requires updating `reset_graph` to discover
  suffixed directories.
## Removed Modules (revisit when needed)

- `spec/` (`SpecRepresentation` protocol, `PythonStubSpec`) — removed in PR #106 (feat/dependency-cleanup). Was intended to abstract spec file formats for spec-writer agents.
- `workspace.py` (`LocalWorkspaceRef`, `WorkspaceRef`) — removed in the same PR. Was intended to model workspace/repo references.
- View protocols (`TaskStateView`, `TaskArtifactsView`, `TaskRuntimeView`, `WorkstreamStateView`, `WorkstreamArtifactsView`, `WorkstreamRuntimeView`) — removed in the same PR. Read-only projections of mutable runtime types via structural typing (Protocol). Reintroduce when a consumer needs enforced read-only access to runtime state.

## Output-Driven Task Composition

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
- **Remove `paths:` backward-compatibility sugar from `_parse_paths()`**: The
  `paths:` key in graph YAML (`src`/`test`/`spec` sub-keys) is preserved as
  sugar that converts to `TaggedPath` entries. Once all graph YAML files are
  migrated to the `tagged_paths:` list format, remove the sugar and simplify
  the parser. Requires updating all graphs in `graphs/` and any external
  repos (e.g., agentrelaydemos).
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

## Persistent Agents

Long-lived agents that span multiple tasks, carrying conversation context
across task boundaries. A third axis of context sharing alongside file-based
pull (graph YAML, signal dirs) and file-based push (`agentrelay-note`).
Full design discussion in `docs/discussions/PERSISTENT_AGENTS.md`.

- **Static agent assignment in graph YAML**: Minimal first implementation.
  Graph author declares named agent slots per workstream with model tiers and
  assigns tasks to slots. Agents scoped to a single workstream. No runtime
  routing, no forking. Validates the core hypothesis: does persistent context
  produce noticeably better task output? Requires changes to `TmuxAgent`
  (lifecycle), `StandardTaskRunner` (reuse existing pane), and graph YAML
  schema (agent slot declarations). Consider implementing pre-Rust as a
  learning prototype (1–2 sprints).
- **LLM-assisted agent routing**: Replace static assignment with an LLM
  router that evaluates available agents' task histories and the new task
  description to pick the best fit. Three-way routing decision: assign to
  idle agent with relevant context, fork a busy agent, or start fresh.
  Defer until static assignment has produced evidence that dynamic routing
  would improve outcomes. Have the LLM explain its routing reasoning —
  over time, those explanations may reveal encodable heuristics.
- **Agent forking (DAG-aware context cloning)**: When the task DAG branches,
  clone an agent's conversation state so both branches inherit the parent's
  context. Technically: serialize conversation history at fork point, start
  two sessions with the same prefix. Plays into Anthropic API prompt caching
  (shared prefix cached, each fork pays only for divergent suffix). Requires
  Claude Code support for session cloning. Defer to Rust unless Claude Code
  adds the necessary hooks sooner.
- **Cross-workstream agent release**: Allow an agent that completes all tasks
  in Workstream X to be released to downstream Workstream Y, carrying
  cross-workstream context. Constraint: target workstream must have a
  dependency-order relationship with the source. Agent switches worktrees at
  the workstream boundary. Defer to Rust.
- **Agent retirement policy and fork budget**: Lifecycle management to prevent
  unbounded agent/fork growth. Retire agents with no remaining useful tasks;
  cap total live agents. The LLM router is well-positioned to judge whether
  forking is worth it vs. starting fresh. Defer to Rust.
- **Agent identity and lineage metadata**: Record which agent handled which
  task, fork-of relationships, and routing decisions in signal directory
  artifacts. Needed for debugging and observability of persistent-agent runs.
- **Fork-point snapshots**: Serialize agent conversation state before each
  task begins, enabling forks from any prior task boundary (not mid-task
  state). Explore snapshot-all-prune-eagerly strategy with topology-aware
  pruning. Investigate BTRFS/ZFS/LVM copy-on-write snapshots for
  near-zero-cost checkpointing. See `docs/discussions/PERSISTENT_AGENTS.md`
  (Fork-point snapshots section).
- **Framework-agnostic fork protocol**: Design forking as a capability
  advertisement on `AgentFrameworkAdapter` — `supports_fork()`,
  `snapshot()`, `fork_from()`. Orchestrator routing degrades gracefully
  when the framework doesn't support forking (falls back to fresh agent +
  file-based context). Core orchestrator logic must not couple to
  Anthropic-specific mechanisms. See `docs/discussions/PERSISTENT_AGENTS.md`
  (Framework-agnostic design section).
- **Local LLM agent support**: Implement `AgentFrameworkAdapter` for a
  local inference engine (llama.cpp, vLLM, or Ollama). Primary motivation:
  cost optimization for simple tasks. Secondary motivation: local models
  provide direct access to KV cache state, enabling higher-fidelity
  forking and a transparent sandbox for prototyping fork mechanics.
  Validating fork strategies with local models (zero per-token cost)
  before applying them to hosted-API agents. See
  `docs/discussions/PERSISTENT_AGENTS.md` (Local LLM agents section).

## Signal Directory Structure

- **Signal directory restructure**: Split `signal_dir/` into two named
  subdirectories — one for orchestrator-internal status tracking (currently
  `signal_dir/status/`) and one for agent-facing files (instructions, manifest,
  policies, .done, .failed, etc., currently direct children of `signal_dir/`).
  Gives each scope a clear name and prevents bugs like agent signals not being
  cleared on retry (fixed in PR D). Deferred because it touches every
  signal_dir consumer (agent SDK CLI tools, completion checker, preparer, gate
  checker, teardown, reset_graph).

- ~~**Uniform per-attempt directories**~~: **Resolved** in PR G (sprint
  2026-04-09). All attempt artifacts now live under
  `signal_dir/attempts/<N>/` including the current attempt.

## Diagram Tooling

- **Interactive module overview on docs site**: Enhance the module
  overview diagram (`diagram-modules.svg`) on the mkdocs site so that
  clicking (or hovering over) a module box navigates to or displays
  the corresponding per-module detailed diagram. Could be implemented
  as an SVG image map, clickable SVG links, or a JavaScript overlay.
  Natural fit for the documentation sprint (Phase 5).

## Code Quality

- ~~**Audit and refactor `run_graph.run_graph()`**~~: **Resolved** in
  PR #199. Phase extraction (`_resolve_config`, `_setup_resume`),
  `RunOptions` dataclass, and protocol decoupling
  (`SandboxInfrastructureManager`, `SessionResolver`, `RunRepoManager`).
- **Audit codebase for direct external-package coupling**: Scan all
  modules (not just `run_graph.py`) for places where core tooling
  directly imports concrete external packages, specific implementations,
  or anything else that should be pluggable via a protocol or interface.
  `run_graph.py` was the most egregious case (resolved in PR #199), but
  other modules may have similar coupling — e.g., `task_helper.py`
  calling `gh` directly (already noted under Extensibility), or modules
  importing `ops/` functions where a protocol would better express the
  dependency.  Goal: the design diagram should accurately represent all
  dependency arrows, and core modules should depend on protocols rather
  than concrete implementations wherever the dependency crosses an
  architectural boundary.
- **Audit docstrings for consistent Google-style format**: Scan the
  entire `src/agentrelay/` tree for Sphinx-style docstring syntax
  (`:class:`, `:func:`, `:meth:`, `:param:`, `:type:`, `::` literal
  blocks) and convert to Google-style (backtick-quoted names, `Args:`,
  `Returns:`, `Raises:`, `Attributes:` sections).  Also ensure all
  dataclasses have `Attributes:` sections and all protocols have
  `Methods:` sections.  Broader than the existing "API Reference mkdocs
  rendering issues" item (which is scoped to `__init__.py` and
  module-level docstrings) — this covers every docstring in the codebase.
- **Replace raw tuple returns with named types**: Audit the codebase for
  functions that return raw tuples (especially heterogeneous ones) and
  replace them with `dataclass` or `NamedTuple` return types. Named
  fields are more readable than positional unpacking and prevent
  ordering bugs as return values grow. `_extract_operational_config()`
  in `run_graph.py` is the first example (converted in PR C of sprint
  2026-04-09); scan for others.

## Documentation

- **Design philosophy document**: Consolidate the project's design
  philosophy into a dedicated document (or a section in the top-level
  README). Key themes are scattered across sprint docs, discussion files,
  backlog entries, and sprint planning notes — including:
  observation-before-enforcement, guidance-not-restriction for agent
  autonomy, the OCI isolation spectrum (flexible by default in dev,
  precise knobs for production), signal-file-backed state as source of
  truth, diagrammability, and the SDK-over-roles principle. Comb through
  existing `.md` files to extract and unify these into a single coherent
  statement of the project's design values. Target audience: someone
  encountering the project for the first time who wants to understand not
  just *what* it does but *why* it's designed the way it is.

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

## Visualization

- **Graph diagram for documentation**: Create a sample graph visualization
  showing tasks as nodes inside container boundaries, grouped into
  workstreams, with dependency edges between them. Purpose: give readers
  and new users a clear mental model of what a graph looks like at runtime
  (tasks, containers, workstreams, dependencies). Include in README and
  design docs. Could be hand-drawn in D2 or generated from a representative
  graph YAML.

- **Graph visualization tool**: Build a tool/script that takes a graph YAML
  file as input and generates a graphical representation of the DAG.
  **Static version (MVP)**: Render tasks as nodes with dependency edges,
  grouped by workstream, output as SVG or HTML. Could use D2, Graphviz,
  or a JavaScript library.
  **Live version (stretch)**: Display the graph in a browser while it's
  running, with color changes and indicators showing task status progression
  (pending → running → PR created → merged / failed). Could read signal
  files or subscribe to orchestrator events. Natural fit for a web dashboard
  using something like D3.js, Cytoscape.js, or ELK.js. Consider whether
  the live version is Python-era (useful for demos and debugging) or
  Rust-era (benefits from structured event stream).

## Observability

- **Record effective run config**: After CLI > YAML > default resolution,
  write the effective `OrchestratorConfig` (and other resolved settings
  like model, sandbox type, credential name) to
  `.workflow/<graph>/run_config.json` at startup. Currently there's no
  record of what values were actually used — if a CLI flag overrides a
  YAML value, only the YAML is preserved (copied to `.workflow/`).
  Simple JSON dump of all resolved config. Useful for post-mortem
  debugging and future graph resumption.
- ~~**Carry-forward of `resolved.json` across runs**~~: **Resolved** in
  sprint 2026-04-12 (PR E). The MVP copies `resolved.json` directly
  rather than referencing backward into prior run directories. Each run
  directory is self-contained.
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
- **Logging over persistent panes as the debugging strategy**: With
  `agent.log`, `summary.md`, `concerns.log`, `ops_concerns.log`, and
  per-attempt artifact archiving, persistent tmux panes are no longer
  the primary debugging tool. Future investment should go to structured
  logging (per-attempt event logs, `run_config.json`, orchestrator log
  files) rather than keeping panes alive after failure. The default
  `TearDownMode` has been changed to `ALWAYS` (PR D, sprint 2026-04-09);
  `ON_SUCCESS` is now an opt-in debugging mode for live pane inspection.
- **CLI tool for inspecting existing run state (`agentrelay probe`)**:
  Add a subcommand that runs the existing `probe_graph_state()` machinery
  (landed in sprint 2026-04-12, PR C) against a graph's workflow directory
  and prints a tabular summary of each task and workstream: status,
  attempt number, branch name, PR URL, whether a frozen `resolved.json`
  exists, and worktree path.  Use cases:
  - Debugging stuck or aborted runs — "what state is this in right now?"
    without triggering a re-run.
  - Pre-resume inspection — see what `agentrelay run` would pick up
    before committing to a restart (complements the resume summary
    table that PR E will print).
  - Operator workflows — a quick tabular view of multi-workstream state
    instead of spelunking `.workflow/<graph>/runs/<N>/` by hand.
  - Scripting — a `--json` output mode lets external tools query run
    state programmatically.
  **Shape:** `agentrelay probe <graph> [--run N] [--json] [--dry-run]`.
  Defaults to the latest run directory; `--run N` selects a specific
  one.  `--json` emits the probe result as structured JSON instead of
  the tabular view.
  **Important design tension — the probe mutates disk.**
  `probe_graph_state()` writes status signal files during stale-state
  normalization and can even merge a stale PR via the `TaskPrProber`.
  A CLI named `probe` that users expect to be read-only would surprise
  them.  Resolution options:
  1. Add a `--dry-run` flag (the default) that skips normalization —
     probe reports what *is* on disk, not what the orchestrator would
     see on resume.  A `--normalize` (or `--write`) opt-in runs the
     mutating path.
  2. Or factor the probe into two layers: a pure read-only
     reconstruction function and a separate normalization function.
     The CLI calls only the read-only layer; `run_graph.py` (PR E)
     calls both.  This is the cleaner design but requires refactoring
     `probe.py`.
  The refactor is probably worth doing regardless — it makes the
  read-only probe usable from other contexts (tests, audit scripts,
  future UI) without the mutation side effect.
  **Depends on:** nothing — probe machinery already landed in PR C.
  Can be built any time after sprint 2026-04-12 merges.
