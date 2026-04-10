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

---

## Remaining work

### Phase 3: CLI cleanup + diagram tooling

**Goal:** Clear small debts and settle the diagram tooling stack so
later sprints build on a clean foundation.

#### CLI cleanup

Minor fixes surfaced during Phase 2:

- **Fix `--max-concurrency` help text**: Currently reads "Maximum
  concurrent task attempts" — should be "Maximum concurrent tasks".
  Two locations: `cli.py` and `run_graph.py`.
- **Short options for remaining args**: `--max-task-attempts`,
  `--teardown-mode`, `--anthropic-credential`, `--dry-run` lack short
  forms. The `--fail-fast-*` flags are awkward to shorten due to
  `BooleanOptionalAction` — may leave as-is.

Small effort — half-day PR.

#### Diagram layout engine: TALA → dagre

The current setup (D2 + TALA) hits TALA's internal dimension limits on
the detailed diagram. TALA is closed-source and Terrastruct appears
dormant since October 2025. The `--tala-seeds` workaround is fragile.

**Decision:** Switch to dagre (bundled with D2, no external dependency).
Keep all `.d2` source files unchanged — this is a layout engine swap,
not a format migration. ELK, PlantUML, and Mermaid were evaluated
earlier; dagre has not been tried. If dagre layout quality is
unacceptable, PlantUML is the fallback.

**Scope:** Small — change `render_diagrams.sh`, re-render SVGs, update
docs. No `.d2` source or `generate_module_diagrams.py` changes needed.

### Phase 4: Graph resumption (MVP)

**Goal:** Make it easy to pick up where you left off — the
highest-value improvement for anyone tinkering with the project.

When a graph is re-launched and `.workflow/<graph>/` already exists,
probe the actual state on disk and resume instead of refusing.

**Why now:** The backlog notes that *"the Python version will be the
public-facing testing ground for early users during the conversion,
and 'reset and re-run the entire graph because task 8 failed' is a
poor first experience."* This is the highest-value user-facing
improvement for tinkerers.

**Architecture advantage:** Task status is already derived from signal
files on disk (`_read_task_status_from_signals()`), not stored in
memory. The building blocks for resumption exist.

**MVP scope:**
1. Replace conflict check in `run_graph.py` with state probing
   (auto-detect resume)
2. `TaskRuntimeBuilder.from_disk()` / `WorkstreamRuntimeBuilder.from_disk()`
   — reconstruct runtimes from signal files and filesystem state
3. Resume-aware worktree/branch preparation (skip re-creation if exists)
4. Tests

**What the MVP skips** (deferred to Rust):
- Cross-session retry of failed tasks
- Corruption detection / worktree validation
- Partial re-run of specific task subsets
- Human-triggered re-run of completed tasks

**What it delivers:** "Graph interrupted or task 8 failed? Re-run
`agentrelay run <graph>`. Completed tasks skip, failed tasks retry,
unstarted tasks proceed."

Estimated effort: 2–3 days.

### Phase 5: Documentation sprint

**Goal:** Make the project legible to outsiders. The Python codebase is
feature-complete (1448 tests, 21 e2e graphs, full OCI support) — the
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

#### Docs site cleanup

- Fix API reference rendering issues (Sphinx-isms in docstrings)
- Remove stale prototype references
- Ensure the mkdocs site at duanegoodner.github.io/agentrelay works well
- **Interactive module overview**: Make the module overview diagram
  clickable — each module box links to its per-module detailed diagram.
  Low effort, high discoverability value.

### Phase 6: Freeze Python, begin Rust

**Gate:** Phases 3–5 complete. Diagram tooling is settled, graph
resumption works, documentation reflects the current system.

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

4. **Diagram tooling is settled.** A sustainable rendering stack is chosen
   and migrated to, so the Rust project inherits a working pipeline.
   (Phase 3)

5. **A partial graph run can be resumed** without resetting and re-running
   everything. Completed tasks are skipped, failed tasks retry, unstarted
   tasks proceed. (Phase 4 — MVP)

6. **A new user can understand what agentrelay does and try it** from the
   README and docs alone — without reading source code or sprint docs.
   (Phase 5)

7. **Documentation reflects the current state** — OCI as default, current
   CLI surface, design philosophy articulated, no stale references to
   removed features or prototype layer. (Phase 5)
