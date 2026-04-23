# Pre-Rust Roadmap

> **Created**: 2026-04-06
> **Purpose**: Capture the remaining work before freezing Python feature
> development and beginning the Rust migration.

---

## Strategic decisions

### Rust migration approach: clean rewrite (Approach B)

The Rust migration will be a clean rewrite, not an incremental replacement.
The Python orchestrator will be frozen for new features once this roadmap
is complete. It remains the working reference implementation and the
behavioral spec the Rust port reimplements against.

**Why clean rewrite over incremental:**
- Idiomatic Rust from day one — design for ownership, `enum` state
  machines, `tokio` async, `petgraph` DAGs. No PyO3 compromises.
- Clean architecture opportunity — apply lessons learned from Python.
  Items like signal directory restructure and structured instructions are
  easier to get right in a greenfield design than to retrofit.
- Sharp finish line — when the Rust version passes the same e2e tests,
  it's done.
- The Python version is the spec — every behavior is implemented and
  tested. Rust doesn't guess; it reimplements known-correct behavior.

**What this means for Python feature work:** Only items that improve the
e2e testing experience (since e2e tests become the Rust rewrite's
acceptance criteria) or that unify the data model (so the Rust port builds
on a clean foundation) are worth doing. Speculative features, heavy
infrastructure, and design-heavy items are Rust-era work.

See `docs/BACKLOG.md` (Rust Migration section) and
`docs/discussions/OPENROUTER_BIFROST_RUST.md` for full rationale.

### OCI as the default execution mode

OCI container isolation should be the recommended default for running
agentrelay. There is no capability lost by running in a container — the
isolation levels provide a spectrum from relaxed to strict, and "relaxed"
is a property you configure on a container, not a reason to skip
containers.

**`SandboxType.NONE` remains supported** as an explicit opt-out for:
- Development/debugging of agentrelay itself (fastest feedback loop)
- First-time setup / onboarding (Docker/Podman is a barrier)
- CI environments that already provide isolation

**What this means concretely:**
- Graph YAML examples and docs default to `sandbox: oci`
- `SandboxType.NONE` documented as "development/debugging mode"
- E2e test graphs primarily run in OCI mode
- New features designed OCI-first (work in containers, degrade gracefully
  without)

This is a docs/convention/priority shift, not a code change.

### Agent autonomy: guidance, not restriction

`inputs_from` and other orchestrator-provided context are **convenience
and contract mechanisms**, not access control. Agents retain full graph
awareness and can explore beyond declared inputs.

**Current posture:** Flexible by default in dev mode. Observe what agents
do with broad context before designing restrictions. Premature isolation
blocks learning.

**Path to restrictions:** OCI isolation provides the substrate for precise
access control via container bind mount scoping. Per-task filesystem
restrictions and signal dir visibility controls are in the backlog,
deferred not because they're hard, but because observation data is needed
to know which restrictions matter.

See the "Design philosophy" section of
`docs/sprints/complete/2026-04-05-output-composition-and-polish.md` for
the full rationale.

---

## Completed work

### Phase 1: CLI & data model cleanup ✓

> Sprint 2026-04-06 (PRs #169–#171). 1348 tests.

- **`agentrelay` top-level CLI** (PR #169): `cli.py` with subcommands
  `run`, `reset`, `check`, `dry-run`, `list`. `--target-repo` defaults
  to current directory.
- **`TaggedPath` replaces `TaskPaths`** (PR #170): `TaskPaths` removed,
  category-based input resolution is the unified model. `paths:` sugar
  preserved for backward compatibility.
- **TALA diagram fix** (PR #171): `--tala-seeds` workaround for TALA
  dimension limit.

### Phase 2: E2E validation with OCI isolation ✓

> Sprint 2026-04-07 (PRs #174–#178). 1448 tests.

- **CLI short options + `--sandbox` override** (PR #174)
- **Graph index + name-based selection** (PR #175): `agentrelay list -g`
- **Tmux session auto-detect** (PR #176): TTY verification + window naming
- **Graph consolidation** (PR #177): 29 → 21 graphs across 8 categories
- **E2E OCI validation** (PR #178): all 20 scenarios pass with OCI
  isolation, both API key and OAuth credential paths validated

### Phase 3: CLI cleanup, diagram tooling, and execution quality ✓

> Sprint 2026-04-09 (PRs #180–#186). 1467 tests.

- **CLI cleanup** (PR #180): Fix `--max-concurrency` help text, add
  short options (`-a`, `-d`, `-T`, `-A`, `-C`, `-S`, `-W`, `-I`),
  shorten flag names.
- **ELK layout engine** (PR #181): Switch from TALA to ELK (bundled
  with D2, no external dependency). Dagre tried first but crashes on
  large diagrams. Drop monolith SVG render; per-module diagrams provide
  better navigation.
- **Graph YAML config fields** (PR #182): `max_concurrency`,
  `max_task_attempts`, `teardown_mode` as graph-level YAML fields with
  CLI-wins precedence. `--keep-panes` CLI flag. `OperationalConfig`
  dataclass.
- **OCI container retry fix** (PR #183): Attempt-indexed container and
  tmux window names prevent name collisions on retry. Sandbox teardown
  wired into `WorktreeTaskTeardown` behind `_should_teardown()` gate.
- **Default teardown mode → ALWAYS** (PR #184): Persistent artifacts
  (`agent.log`, `summary.md`, per-attempt archives) replace live tmux
  panes as the debugging interface. `ON_SUCCESS` and `NEVER` remain
  opt-in.
- **Record effective run config** (PR #185):
  `.workflow/<graph>/run_config.json` captures the fully resolved
  configuration after CLI > YAML > default precedence.
- **Uniform per-attempt signal directories** (PR #186): Agent artifacts
  live under `signal_dir/attempts/<N>/` for every attempt including the
  current one. Eliminates archive-vs-live layout split. Simplifies
  `reset_for_retry()`.

### Phase 4: Graph resumption (MVP) ✓

> Sprint 2026-04-12 (PRs #191, #192, #193, #194, #196, #197, #199, #201,
> #203, #206, #208). 1722 tests. Completed 2026-04-23.

- **Per-run directory layout** (PR #191): `.workflow/<graph>/runs/<N>/`
  contains signal dirs, workstream dirs, run_info.json, run_config.json,
  graph.yaml. Worktrees remain at `.worktrees/<graph>/<ws-id>/`.
- **Frozen records** (PR #192): `resolved.json` written at terminal
  success for tasks and workstreams — captures definition +
  pre-merge SHAs for rollback.
- **Tmux kickoff fix** (PR #193): Ensures prompt submission to agent
  panes is reliable at startup.
- **State probing + runtime reconstruction** (PR #194): `probe_graph_state()`
  reads per-run signals, normalizes stale RUNNING/PR_CREATED, loads
  frozen resolved.json records. Post-probe invariant: no task in
  RUNNING or PR_CREATED.
- **Idempotent workstream preparation** (PR #196): Worktree/branch
  creation skips re-creation when structures already exist.
- **Wire resumption into CLI** (PR #197): `run_graph.py` auto-detects
  resume; conflict check replaced by probe-driven dispatch.
- **run_graph decoupling via protocols** (PR #199): `SandboxInfrastructureManager`,
  `SessionResolver`, `RunRepoManager` protocols isolate `run_graph.py`
  from `ops/` layer.
- **Shared reset utilities + primitive undo commands** (PR #201):
  `reset_ops.py`, `reset_task.py`, `reset_workstream.py`;
  stack-based undo (`reset-task`, `teardown-workstream`,
  `reset-workstream`).
- **Reset observability** (PR #203): `rollback_log.json` per
  workstream, integration PR body updates via `PrBodyUpdater` protocol
  (later renamed to `IntegrationPrOps` in PR #208).
- **`reset-to` batch rollback command** (PR #206): `agentrelay reset-to
  --after <id>` computes the minimum set of operations to roll a graph
  back to the state immediately after a given task or workstream,
  plan-then-execute pattern.
- **Decouple reset commands from ops layer** (PR #208): `RepoResetOps`
  protocol (new `reset_repo.py`) and `IntegrationPrOps` protocol
  (renamed from `PrBodyUpdater`, adds `close_pr`). `reset_ops.py`
  converted from free-function module to `ResetOps` class. All four
  reset commands now depend only on protocols.

**Deferred to Rust** (not blockers for freeze):
- Cross-session retry of failed tasks
- Corruption detection / worktree validation
- Partial re-run of specific task subsets
- Human-triggered re-run of completed tasks
- Decoupling `reset_graph.py` from `ops/` (whole-run wipe — backlog)
- Decoupling `task_helper.py`'s direct `gh` call (backlog)

---

## Remaining work

### Phase 4.5: Persistent agents (minimal prototype)

**Goal:** Validate that agents carrying conversation context across
tasks produces noticeably better output — and generate evidence that
informs the Rust design for agent lifecycle, routing, and forking.

**Why now:** The agentic orchestration field is advancing rapidly. A
working prototype with observed results is more valuable to the broader
conversation than a polished Rust implementation shipped later. The
Python version will be the public-facing testing ground; persistent
agents are a genuinely novel capability worth demonstrating early.
Additionally, the Rust state machine should encode agent identity,
lineage, and lifecycle as first-class types — empirical data from a
Python prototype shapes that design from day one.

**Depends on Phase 4:** Graph resumption provides building blocks
(probe, runtime reconstruction, per-run directories) and ensures
persistent agents survive graph interruption/restart.

**MVP scope:**
1. Static agent assignment in graph YAML — named agent slots per
   workstream with model tiers, tasks assigned to slots
2. Agents scoped to a single workstream (no cross-workstream release)
3. Agent lifecycle: spawn once at first assigned task, stay alive
   through subsequent tasks, tear down at workstream completion
4. No forking, no runtime routing logic
5. Tests + e2e validation with at least one multi-task workstream graph

**What the MVP skips** (deferred to Rust):
- LLM-assisted agent routing
- Agent forking (`--fork-session` CLI support exists, but forking is
  a scope decision for Phase 4.5, not a technical blocker)
- Cross-workstream agent release
- Fork budgets and retirement policies
- Context window management beyond built-in compaction

**What it delivers:** A graph author can declare "these three tasks
share an agent" and the agent carries its full conversation history
from task to task within a workstream. Comparison against the current
model (independent agents per task) reveals whether persistent context
improves output quality and what failure modes emerge.

Full design discussion: `docs/discussions/PERSISTENT_AGENTS.md`.
Backlog items: `docs/BACKLOG.md` (Persistent Agents section).

Estimated effort: 1–2 sprints.

### Phase 5: Documentation sprint

**Goal:** Make the project legible to outsiders. The Python codebase is
feature-complete (1467 tests, 21 e2e graphs, full OCI support) — the
gap is not capability but discoverability.

#### README overhaul

The current README still says *"End-to-end execution currently lives in
`prototypes/v01`"* — actively misleading. Rewrite to reflect reality:
- What agentrelay does (one paragraph)
- A graph YAML example
- An `agentrelay run` invocation and what happens (tmux panes, PRs,
  signal files)
- Getting started steps (pixi, Claude Code, credentials, target repo)

#### Design philosophy document

Consolidate distinctive ideas scattered across sprint docs, discussions,
and backlog into a single coherent document:
- Observation-before-enforcement
- Guidance-not-restriction for agent autonomy
- Signal-file-backed state as source of truth
- SDK-over-roles
- OCI isolation spectrum (flexible default, precise knobs for production)
- Diagrammability as a design constraint
- YAML-as-contract (graph YAML is the unit of work definition)

This is what gets the project into the community conversation — people
engage with ideas, not just code.

#### Getting started guide refresh

Update `docs/GUIDE.md` with a walkthrough: install → configure
credentials → write a simple graph → run it → inspect results. OCI
as the documented default.

#### Graph visualization for mental model

Create a sample graph diagram showing tasks as nodes inside container
boundaries, grouped into workstreams, with dependency edges. Include in
README and design docs so readers can quickly grasp the runtime model
(tasks, containers, workstreams, dependencies) without reading code.

#### Docs site cleanup

- Fix API reference rendering issues (Sphinx-isms in docstrings)
- Remove stale prototype references
- Ensure the mkdocs site at duanegoodner.github.io/agentrelay works well
- **Interactive module overview**: Make the module overview diagram
  clickable — each module box links to its per-module detailed diagram.
  Low effort, high discoverability value.

### Phase 6: Freeze Python, begin Rust

**Gate:** Phases 4–5 complete (4.5 optional but recommended). Graph
resumption works, persistent agents validated (if 4.5 done),
documentation reflects the current system.

**Actions:**
- Mark the Python codebase as frozen for new features
- Critical bugfixes can still land if discovered
- Begin Rust rewrite as a separate project/repo (or a `rust/` subdirectory)
- The Python test suite and e2e graphs become the Rust port's acceptance
  criteria

---

## What is NOT pre-Rust work

These backlog items are explicitly deferred to the Rust migration:

| Item | Why defer |
|---|---|
| `expected_outputs` graph YAML extension | Better with compile-time validation |
| Role template simplification | Observe `inputs_from` dynamics first |
| Typed output categories | Needs real e2e usage data |
| Human-triggered partial re-run | Significant design, Rust state machine |
| Orchestrator-driven partial re-run | Depends on above |
| Human intervention on task failure | Same family as partial re-run |
| Cross-session retry of failed tasks | Layer on top of resumption MVP in Rust |
| Resumption corruption detection | Needs Rust ownership model |
| Auto-suffix for concurrent same-graph runs | Convenience, low priority |
| Durable state checkpoints | Architectural plumbing |
| Multi-graph orchestration | Explicitly Rust-era |
| Signal directory restructure | High touch-count, better in greenfield |
| Structured concern definitions | Rust-era instruction architecture |
| `agentrelay-note` / `agentrelay-read` | Context sharing messaging |
| LLM-assisted agent routing | Design-heavy, benefits from Rust state machine |
| Agent forking | CLI support exists (`--fork-session`); full design deferred |
| Cross-workstream agent release | Depends on agent routing |
| Agent-assisted integration merging | Complex, benefits from Rust |
| Orchestrator log files | Architectural plumbing |
| Rust migration phases | Engine proxy → graph runner → full harness |

See `docs/BACKLOG.md` for full descriptions of each item.

---

## Success criteria for starting Rust

The Python version is ready to freeze when:

1. ✅ **The `agentrelay` CLI exists** as a user-facing entry point (PR #169).

2. ✅ **The data model is unified.** `TaskPaths` removed, `TaggedPath` +
   category-based input resolution is the single mechanism (PR #170).

3. ✅ **E2E tests pass with OCI isolation** across representative graph
   categories — all 20 scenarios (PR #178).

4. ✅ **Diagram tooling is settled.** D2 + ELK layout engine, monolith
   SVG dropped, per-module diagrams as primary navigation (PR #181).

5. ✅ **A partial graph run can be resumed** without resetting and
   re-running everything. Completed tasks are skipped, failed tasks retry,
   unstarted tasks proceed. Primitive and batch rollback commands
   (`reset-task`, `reset-workstream`, `teardown-workstream`, `reset-to`)
   cover targeted undo. (Phase 4 — sprint 2026-04-12, completed 2026-04-23)

6. **Persistent agents validated** (optional but recommended) — static
   agent assignment works, empirical data on whether persistent context
   improves task output, failure modes documented. Evidence informs the
   Rust agent lifecycle design. (Phase 4.5)

7. **A new user can understand what agentrelay does and try it** from the
   README and docs alone — without reading source code or sprint docs.
   (Phase 5)

8. **Documentation reflects the current state** — OCI as default, current
   CLI surface, design philosophy articulated, no stale references to
   removed features or prototype layer. (Phase 5)
