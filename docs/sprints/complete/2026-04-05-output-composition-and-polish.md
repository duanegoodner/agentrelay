# Sprint Notes — 2026-04-05: Output Composition & Execution Polish

> **Status: Complete.** All 3 PRs (A–C) merged. PRs developed in parallel
> across git worktrees; merged sequentially A→B→C with no conflicts.
> 1348 tests after all PRs landed.

## Goal

Make output-driven task composition functional end-to-end by shipping
`inputs_from`, and improve the human review experience with better
integration PR bodies. Complete the fail-fast CLI configuration surface.

This is the final feature sprint before the Rust migration. The aim is to
bring the Python orchestrator to a state where a new user can run a
non-trivial graph from the CLI, get a good idea of how things work, and
potentially accomplish useful work with it.

## Context

Sprint 2026-04-04 shipped `agentrelay-declare` and `outputs.json` — agents
can now declare what files they produce, with semantic categories (stubs,
tests, implementation, etc.). But without a consumer, `outputs.json` is
metadata with no effect. The `inputs_from` graph YAML extension is the
mechanism that makes output manifests useful: downstream tasks discover
their input files at prepare time by reading upstream `outputs.json`,
replacing hardcoded `paths` with runtime-resolved file lists.

The integration PR body is the primary artifact a human reviews after a
graph run. Currently it uses task metadata (description, PR URL, concerns)
but ignores agent-written `summary.md` files. Incorporating summaries makes
the integration PR a better audit trail.

`fail_fast_on_internal_error` has no CLI flag — the last gap in the
fail-fast configuration surface after PR #159 added the workstream error
flag.

## Design philosophy: `inputs_from` as guidance, not restriction

`inputs_from` is a **convenience and contract mechanism**, not an access
control mechanism. It serves two purposes:

1. **Convenience**: The orchestrator resolves upstream `outputs.json` at
   prepare time and places concrete file paths in the agent's
   `manifest.json`. The agent gets "here are your input files" without
   needing to navigate signal directories or parse upstream manifests.
   This particularly helps weaker agents.

2. **Contract**: The graph YAML now documents the intended data flow
   between tasks. "test_queue takes stubs from spec_queue" is explicit
   in the YAML, not implicit in agent behavior. Valuable for auditability,
   graph comprehension, and as a behavioral spec for the Rust rewrite.

**`inputs_from` is not an access restriction.** Agents retain full graph
awareness (shipped in sprint 2026-04-03): the graph YAML, `.workflow/`
conventions, and the ability to read any completed task's signal files.
`inputs_from` says "start here," not "stay here." An agent that reads a
sibling task's `concerns.log` or `summary.md` and adjusts its approach is
exhibiting the resourcefulness we want to preserve.

Likewise, the optional `category` filter on `inputs_from` controls which
files get resolved into the manifest — not what the agent is allowed to
see. `category: stubs` means "resolve stubs into my manifest for
convenience"; the agent can still explore other categories or other tasks'
artifacts via filesystem reads.

**Current posture: flexible by default, observe, then restrict.** We are
in development mode, running toy projects in a controlled environment.
The deliberate-observation-before-enforcement principle applies: we don't
yet have evidence that agents exploring beyond their declared inputs
causes problems, and restricting prematurely would sacrifice learning
about how agents use broad context. The existing graph awareness
infrastructure was explicitly designed to give agents wide visibility so
we can study what they do with it.

**The path to hard restrictions is clear.** OCI isolation already provides
the substrate for precise access control. When agentrelay is used for
sensitive projects or production environments, per-task filesystem
restrictions can be implemented via container bind mount scoping — the
agent physically cannot see signal directories that aren't mounted.
Per-task signal dir visibility restrictions and OCI mount tightening are
both in the backlog, deferred not because they're hard to build, but
because we need observation data to know which restrictions actually
matter. The right knobs will emerge from seeing what goes wrong without
them.

**Summary of the three layers an agent has access to:**

| Layer | What the agent gets | Source |
|---|---|---|
| Graph awareness (shipped) | Full graph YAML, `.workflow/` conventions, ability to read any task's signal files | Sprint 2026-04-03 |
| `inputs_from` resolution (this sprint) | Specific file paths resolved into `manifest.json` | Orchestrator reads upstream `outputs.json` at prepare time |
| Task description | Natural language intent | Graph YAML `description` field |

Each layer adds specificity. None removes the layer below it.

## Architecture notes

**`inputs_from` resolution (PR A):** At prepare time, when a task has
`inputs_from`, the orchestrator reads the referenced upstream task's
`outputs.json` from its signal directory, optionally filters by category,
and merges the resolved file paths into the task's manifest. The agent
sees a single resolved set of input files in `manifest.json` — it doesn't
need to know whether they came from `paths` or `inputs_from`.

Key design decisions (from `docs/discussions/OUTPUT_DRIVEN_COMPOSITION.md`):
- `inputs_from` can reference a single upstream task (`task` + optional
  `category`) or a list for multiple upstream sources.
- Coexists with `paths` — the resolved input set is the union.
- `inputs_from.task` must be in the task's `dependencies` (validated at
  graph construction time).
- Missing `outputs.json` on the referenced upstream task is a preparation
  error — the task cannot proceed.

**Integration PR body refinement (PR B):** `_build_pr_body` in
`GhWorkstreamIntegrator` now reads `summary.md` from each task's signal
directory and includes it as a collapsible `<details>` section. Long task
descriptions are truncated. Tasks without descriptions fall back to task
ID + role. The orchestrator also populates `TaskSummary` objects during
workstream execution for richer PR bodies.

**`fail_fast_on_internal_error` CLI flag (PR C):** Mirrors PR #159's
pattern. `--fail-fast-on-internal-error` / `--no-fail-fast-on-internal-error`
added to `run_graph.py`. Graph YAML `fail_fast_on_internal_error` field
parsed via `_extract_operational_config`. CLI > YAML > default (`True`)
precedence. Completes the fail-fast configuration surface.

---

## PR plan

### PR A: `inputs_from` graph YAML extension — Merged (#163)

- Branch: `feat/inputs-from`

Downstream tasks reference upstream outputs by task ID and optional
category instead of hardcoded file paths. The orchestrator resolves
`inputs_from` at prepare time by reading the upstream task's
`outputs.json`.

**Changes:**
- `src/agentrelay/task.py` — added `InputsFrom` dataclass and optional
  `inputs_from` field on `Task`.
- `src/agentrelay/task_graph/builder.py` — parse `inputs_from` from YAML,
  validate that each referenced task is a dependency.
- `src/agentrelay/agent_comm_protocol/manifest.py` — resolve `inputs_from`
  at manifest build time: read upstream `outputs.json`, filter by category,
  merge with `paths`.
- `src/agentrelay/agent_comm_protocol/templates.py` — added resolved input
  files to instructions ("Input Files" section).
- `src/agentrelay/task_runner/implementations/task_preparer.py` — wired
  `inputs_from` resolution into the prepare step.
- Updated `CLAUDE.md` graph YAML schema docs.
- Added `graphs/smoke/inputs_from_chain.yaml` e2e graph.

**Acceptance criteria:**
- [x] `inputs_from` with `task` + `category` resolves files from upstream
      `outputs.json`
- [x] `inputs_from` as a list resolves files from multiple upstream tasks
- [x] `inputs_from` coexists with `paths` (union of both)
- [x] Missing `outputs.json` on upstream task raises a preparation error
- [x] Validation rejects `inputs_from` referencing a non-dependency task
- [x] Resolved input files appear in the agent's `manifest.json`
- [x] Agent instructions include the resolved input file list
- [x] `pixi run check` passes

---

### PR B: Integration PR body refinement — Merged (#164)

- Branch: `feat/integration-pr-body`

Incorporate agent-written `summary.md` content into integration PR bodies
and improve formatting.

**Changes:**
- `src/agentrelay/workstream/core/runtime.py` — added `summary_text`
  field to `TaskSummary`.
- `src/agentrelay/workstream/implementations/workstream_integrator.py` —
  read `summary.md`, populate `TaskSummary.summary_text`, render summaries
  as collapsible `<details>` sections, truncate long descriptions, fall
  back to task ID for missing descriptions.
- `src/agentrelay/orchestrator/orchestrator.py` — populate `summary_text`
  during workstream execution.

**Acceptance criteria:**
- [x] Integration PR body includes `summary.md` content for tasks that
      have it
- [x] Summaries render as collapsible sections (not inline wall-of-text)
- [x] Long task descriptions are truncated with a sensible cutoff
- [x] Tasks without descriptions show task ID + role instead of
      "(no description)"
- [x] `pixi run check` passes

---

### PR C: `fail_fast_on_internal_error` CLI flag — Merged (#165)

- Branch: `feat/fail-fast-internal-cli`

Complete the fail-fast configuration surface by adding a CLI flag for
`fail_fast_on_internal_error`.

**Changes:**
- `src/agentrelay/run_graph.py` — added `--fail-fast-on-internal-error` /
  `--no-fail-fast-on-internal-error` boolean flag. Parsed optional
  `fail_fast_on_internal_error` field from graph YAML via
  `_extract_operational_config`. Wired through `_build_config_from_args`
  to `OrchestratorConfig`. CLI > YAML > default (`True`) precedence.

**Acceptance criteria:**
- [x] `--no-fail-fast-on-internal-error` disables the flag
- [x] Graph YAML `fail_fast_on_internal_error: false` disables the flag
- [x] CLI flag overrides graph YAML setting
- [x] Default remains `True` when neither CLI nor YAML specifies
- [x] `pixi run check` passes

---

## Dependency ordering

PRs A through C were independent — no code dependencies between them.
Developed in parallel across three git worktrees. Merged sequentially
A→B→C with no conflicts.

## Pre-Rust migration: deprecate `TaskPaths` in favor of categories

`TaskPaths` (`src`/`test`/`spec`) and output manifest categories (`stubs`,
`tests`, `implementation`, etc.) serve overlapping purposes — both describe
the semantic role of files a task works with. `TaskPaths` was the first
approach; categories emerged later and proved more flexible. With
`inputs_from` shipping in this sprint, category-based input resolution is
now validated end-to-end.

Before beginning the Rust migration, migrate non-generic role templates to
use category-based input resolution instead of `$src_paths`/`$test_paths`.
This ensures the Rust port builds on the unified model rather than carrying
both systems. `paths` in the graph YAML would become sugar for inline
category declarations, and `TaskPaths` would be replaced by category-tagged
file lists on the manifest.

Tracked in backlog under "Output-Driven Task Composition." Planned for
next sprint (CLI & data model cleanup).

## What's explicitly deferred

These items from the output-driven composition and orchestrator execution
backlog categories are deferred to the Rust migration:

- **`expected_outputs` graph YAML extension** — useful but not required
  for `inputs_from` to work. Better designed in Rust with compile-time
  validation.
- **Role template simplification** — observe how `inputs_from` changes
  the role dynamics first; simplify in Rust if the pattern validates.
- **Typed output categories** — needs real e2e usage data before
  introducing an enum.
- **Human-triggered partial re-run** — significant design work, better as
  a Rust-native state machine.
- **Orchestrator-driven partial re-run (LLM judgment)** — depends on
  human-triggered re-run.
- **Human intervention on task failure** — same family as partial re-run.
- **Auto-suffix for concurrent same-graph runs** — convenience, low
  priority.
- **Resume hooks / durable state checkpoints** — architectural plumbing
  better suited to Rust.
- **Multi-graph orchestration** — explicitly a Rust-era item.
