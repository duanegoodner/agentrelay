# Sprint Plan — 2026-04-09: CLI Cleanup + Diagram Tooling

> **Status: Planning.**

## Goal

Clear small CLI debts and settle the diagram tooling stack so later
sprints (graph resumption, documentation) build on a clean foundation.

This is Phase 3 of the pre-Rust roadmap.

## Context

Sprint 2026-04-07 completed Phase 2 — all 20 e2e OCI scenarios pass,
1448 tests, graph inventory consolidated from 29 to 21 graphs. The
Python orchestrator's feature surface is proven. What remains before the
Rust freeze is usability polish (this sprint + graph resumption) and
documentation.

Two issues surfaced during Phase 2:

1. **CLI rough edges.** The `--max-concurrency` help text is wrong
   ("task attempts" instead of "tasks"), and several arguments still lack
   short options.

2. **Diagram tooling fragility.** The detailed diagram exceeds TALA's
   internal dimension limits. A `--tala-seeds` workaround keeps it
   rendering, but TALA is closed-source and Terrastruct appears dormant
   since October 2025. Per-module diagrams render fine. The Rust
   migration will rewrite diagram tooling — choosing now avoids carrying
   two systems across the boundary.

## Decisions

### Diagram tooling: D2 + ELK, drop monolith diagram

**Decision:** Switch from TALA to ELK as the D2 layout engine, and
stop rendering the 80+ class detailed monolith diagram as a single SVG.

**Layout engine:** ELK is bundled with D2 (no external dependency,
no license required), actively maintained by Eclipse, and handles any
diagram size. Dagre was tried first but crashes on the detailed diagram
(`TypeError` in the Go port for large inputs). TALA had dimension
limits and depends on closed-source, dormant Terrastruct.

**Drop the monolith:** The detailed diagram (`diagram-detailed.d2`)
remains as the authoritative D2 source — `generate_module_diagrams.py`
parses it to produce per-module diagrams and the module overview. But
it is no longer rendered as a single SVG. The 80+ class monolith was
too large to be useful to human viewers. The module overview + 18
per-module diagrams provide better navigation.

**Future:** An interactive module overview (click/hover to see per-module
detail) is planned for the documentation sprint (Phase 5).

## Plan

### PR A: CLI cleanup

**Scope:** Half-day effort.

**Changes:**
1. Fix `--max-concurrency` help text in `cli.py` and `run_graph.py`:
   "Maximum concurrent task attempts" → "Maximum concurrent tasks"
2. Add short options for arguments that lack them:
   - `-a` → `--max-task-attempts` (or `-A`; avoid collision with `-a`
     if used elsewhere)
   - `-d` → `--dry-run`
   - `-T` → `--teardown-mode`
   - `--anthropic-credential` — evaluate whether a short form is
     warranted (long flag, infrequent use)
   - `--fail-fast-*` — leave as-is (`BooleanOptionalAction` makes
     short forms awkward)
   - `-e` → `--env` on the `check` subcommand
3. Keep `cli.py` and `run_graph.py` help text in sync.

**Files touched:** `src/agentrelay/cli.py`, `src/agentrelay/run_graph.py`,
tests for CLI argument parsing.

### PR B: Switch to ELK layout engine, drop monolith diagram

**Scope:** Small — layout engine swap + remove monolith SVG render.

**Changes:**
1. In `tools/render_diagrams.sh`:
   - Change `RENDER_LAYOUT="tala"` → `RENDER_LAYOUT="elk"`
   - Remove `DETAILED_TALA_SEEDS` variable and `--tala-seeds` flag
   - Remove the detailed diagram render step (keep `.d2` source as
     input to `generate_module_diagrams.py`)
2. Delete `docs/diagrams/uml/diagram-detailed.svg` (no longer rendered)
3. Re-render all SVGs with ELK:
   - `docs/diagrams/uml/diagram-modules.svg`
   - 18 per-module SVGs in `docs/diagrams/uml/modules/`
4. Update `.githooks/pre-commit` — skip `diagram-detailed.d2` in the
   `.d2`→`.svg` co-staging check (source-only, no rendered SVG)
5. Update docs:
   - `docs/DIAGRAM.md` — remove detailed diagram section, note ELK
   - `CLAUDE.md` — remove TALA/`d2plugin-tala` requirement, update
     diagram workflow description
   - `docs/BACKLOG.md` — replace TALA-specific items with interactive
     module overview idea
   - `docs/planning/pre-rust-roadmap.md` — add interactive overview
     to Phase 5

**Files touched:**
- `tools/render_diagrams.sh` (layout engine + remove detailed render)
- `.githooks/pre-commit` (skip source-only `.d2`)
- `docs/diagrams/uml/diagram-detailed.svg` (deleted)
- `docs/diagrams/uml/` — re-rendered SVGs
- `docs/DIAGRAM.md`, `CLAUDE.md`, `docs/BACKLOG.md`,
  `docs/planning/pre-rust-roadmap.md` (doc updates)

### PR C: Graph YAML fields for orchestrator config

**Scope:** Small — same pattern as existing `fail_fast_*` YAML fields.

An audit of CLI flags vs graph YAML fields (2026-04-10) identified
three `OrchestratorConfig` fields that are CLI-only with no YAML
equivalent, plus one YAML field (`keep_panes`) with no CLI flag.
Graph authors often know the right values for these settings, and
forcing CLI specification is friction for users running someone
else's graph.

**New graph-level YAML fields** (all optional, CLI overrides YAML):

| YAML field | CLI flag | Default | Notes |
|---|---|---|---|
| `max_concurrency` | `-c` | 1 | Graph with 4 workstreams should say `max_concurrency: 4` |
| `max_task_attempts` | `-a` | 1 | Graph with flaky tasks can set retry budget |
| `teardown_mode` | `-T` | `on_success` | Debugging graphs benefit from `never` |

**New CLI flag** (YAML field already exists):

| CLI flag | YAML field | Default |
|---|---|---|
| `-k, --keep-panes` | `keep_panes` | false |

**Precedence:** CLI > YAML > default (same pattern as `fail_fast_*`).

**Changes:**
1. `run_graph.py` — `_pop_operational_keys()`: extract three new fields
   from raw YAML dict
2. `run_graph.py` — `run_graph()`: accept YAML values, merge with CLI
   using CLI-wins precedence, pass to `_build_config_from_args()` or
   `OrchestratorConfig` construction
3. `cli.py` — add `-k, --keep-panes` boolean flag; wire through to
   `run_graph()`
4. `run_graph.py` `_build_parser()` — add `-k, --keep-panes`
5. Tests: extend `test_cli.py` and `test_run_graph.py` with YAML
   override + CLI precedence tests
6. Docs: update `CLAUDE.md` graph YAML schema, `docs/GUIDE.md` flags
   table, `docs/BACKLOG.md` (mark resolved)

**Files touched:** `cli.py`, `run_graph.py`, `test_cli.py`,
`test_run_graph.py`, `CLAUDE.md`, `docs/GUIDE.md`, `docs/BACKLOG.md`

### PR D: Fix OCI container cleanup on task retry

**Scope:** Small-medium — touches task runner lifecycle and sandbox
teardown wiring.

**Bug:** When a task fails under OCI sandbox mode and the orchestrator
retries it (`-a > 1`), the old Docker container still exists with name
`agentrelay-<graph>-<task_id>`. The retry's `docker run` fails with
"Conflict. The container name is already in use." Discovered during
e2e testing of `blocked-downstream` graph with `-a 2 -S oci`.

**Root cause (two gaps):**
1. `WorktreeTaskTeardown` never calls `sandbox.teardown()` — the
   `OciSandbox` instance is created in the launcher but not passed
   to the teardown handler.
2. Default `TearDownMode.ON_SUCCESS` means teardown doesn't run on
   failure at all — so even if sandbox teardown were wired in, it
   wouldn't fire when it's needed most (before a retry).

**Fix approach:**

Container cleanup should be **unconditional** — a stale container
always blocks retries regardless of the user's teardown preference.
The `TearDownMode` setting controls tmux pane and worktree cleanup
(useful for debugging), but container removal has no debugging value
and must happen before a retry can succeed.

1. Store the `AgentSandbox` instance in `TaskArtifacts` (or pass it
   to the teardown handler via the builder). The sandbox is created
   in `TmuxTaskLauncher` — after launch, attach it to the runtime so
   teardown can access it.
2. In `WorktreeTaskTeardown.teardown()`, call `sandbox.teardown()`
   **unconditionally** (before the `_should_teardown()` gate that
   controls pane/branch cleanup). This ensures the container is
   removed on failure, success, and even when `TearDownMode.NEVER`
   is set.
3. In `TaskRuntime.reset_for_retry()` or the orchestrator retry path,
   ensure sandbox teardown runs before re-preparation. This is the
   belt-and-suspenders path — if teardown already ran, `OciSandbox`
   handles the idempotent case (stop/rm swallow errors for missing
   containers).

**Files touched:**
- `src/agentrelay/task_runner/implementations/task_teardown.py` —
  call `sandbox.teardown()` unconditionally
- `src/agentrelay/task_runner/implementations/task_launcher.py` —
  store sandbox in runtime artifacts after launch
- `src/agentrelay/task_runtime/runtime.py` — add sandbox field to
  `TaskArtifacts` (or accept it as optional)
- `src/agentrelay/orchestrator/builders.py` — wire sandbox through
  builder
- Tests: mock sandbox teardown in task runner tests, add retry
  scenario test

### PR E: Record effective run config

**Scope:** Small — single file write at orchestrator startup.

After all CLI > YAML > default resolution, write the effective
configuration to `.workflow/<graph>/run_config.json`. Currently
there's no record of what values were actually used — if a CLI flag
overrides a YAML value, only the YAML copy is preserved. This makes
post-mortem debugging and future graph resumption harder.

**Rough outline:**
1. After config resolution in `run_graph()`, serialize the effective
   `OrchestratorConfig` + other resolved settings (model, sandbox,
   credential name, keep_panes, verbose) to JSON
2. Write to `.workflow/<graph>/run_config.json` alongside the existing
   `run_info.json`
3. Tests: verify file is written with expected content

### Ordering

PRs A–E are independent and can be developed in parallel.
A and B are pure CLI/docs (both merged). C is CLI plumbing and YAML
extraction. D touches runtime code (task runner lifecycle + sandbox
teardown). E is a single file write at startup.

## Out of scope

- Graph resumption (Phase 4 — next sprint)
- Documentation overhaul (Phase 5)
- Backlog items deferred to Rust (see `docs/planning/pre-rust-roadmap.md`)
