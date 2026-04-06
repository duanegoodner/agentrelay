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

## Remaining work

### Phase 1: CLI & data model cleanup (next sprint)

**Goal:** Make the Python version feel like a real tool and unify the data
model so the Rust port starts clean.

#### `agentrelay` top-level CLI

Register an `agentrelay` console script in `pyproject.toml` with
subcommands:

```
agentrelay run <graph.yaml> [--target-repo <path>] [flags]
agentrelay reset <graph.yaml> [--target-repo <path>]
agentrelay check [--target-repo <path>]
agentrelay dry-run <graph.yaml>
```

`--target-repo` defaults to the current directory. Someone working in a
target repo can type `agentrelay run graph.yaml`. The `pixi run e2e`
wrapper becomes an internal convenience for agentrelay developers.

Small effort — a single `cli.py` module with `argparse` subcommands
delegating to `run_graph.main()` and `reset_graph.main()`.

#### Replace `TaskPaths` with category-based inputs

`TaskPaths` (`src`/`test`/`spec`) and the output manifest's `category`
field serve overlapping purposes. Categories proved more flexible. With
`inputs_from` validated end-to-end (PR #163), category-based input
resolution is the unified model.

This is a single PR that removes `TaskPaths` entirely — not a two-step
deprecate-then-remove. There are no external consumers of the class; all
consumers are internal and changed in the same PR. Leaving dead code in
the reference implementation would create confusion during the Rust port
about whether it needs to be ported.

**Changes:**
- `paths` in graph YAML remains valid as sugar — internally converts
  `paths.src` → `category: src`, `paths.test` → `category: test`, etc.
- `TaskPaths` class deleted from `task.py`
- `TaskManifest` uses category-tagged file lists instead of
  `src_paths`/`test_paths`/`spec_path`
- Role templates use category-based variables instead of
  `$src_paths`/`$test_paths`
- Ensures the Rust port builds on the unified model with no dead taxonomy

**Scope:** Moderate — touches `task.py`, `builder.py`, `manifest.py`,
`templates.py`, 4 template markdown files, 3 test files, ~39 graph YAML
files (backward compatible — `paths:` still parses). See backlog
"Output-Driven Task Composition" section for details.

#### OCI as documented default

Update docs, graph YAML examples, and `GUIDE.md` to recommend OCI
isolation as the default. `SandboxType.NONE` documented as opt-out for
development.

#### Quick doc fixes

Any low-effort documentation improvements surfaced during the sprint.

### Phase 2: E2E validation with OCI isolation

**Goal:** Validate the complete system end-to-end with OCI containers
before freezing Python.

Run representative graphs across all graph categories (`smoke/`,
`concerns/`, `roles/`, `failure/`, `workstreams/`, `gates/`, `adr/`,
`isolation/`, `graph_awareness/`) with OCI isolation enabled. This:

- Validates container infrastructure under real workloads
- Surfaces any remaining friction or bugs
- Produces the behavioral baseline the Rust port reimplements against
- Exercises `inputs_from` and the new integration PR body format

Fix whatever breaks. This round replaces the "full e2e test pass"
pre-migration gate described in the backlog.

### Phase 3: Freeze Python, begin Rust

**Gate:** E2E validation passes with OCI isolation across representative
graphs.

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
| Auto-suffix for concurrent same-graph runs | Convenience, low priority |
| Resume hooks / durable state checkpoints | Architectural plumbing |
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

1. **A new user can run agentrelay from the CLI** on a non-trivial graph
   for a real (non-toy) project, get a good idea of how things work, and
   potentially accomplish useful work. Rough edges are acceptable.

2. **The data model is unified.** `TaskPaths` is removed, category-based
   input resolution is the single mechanism, and `inputs_from` is validated.

3. **E2E tests pass with OCI isolation** across representative graph
   categories.

4. **The `agentrelay` CLI exists** as a user-facing entry point (not just
   `python -m agentrelay.run_graph` or `pixi run e2e`).

5. **Documentation reflects the current state** — OCI as default, current
   CLI surface, no stale references to removed features.
