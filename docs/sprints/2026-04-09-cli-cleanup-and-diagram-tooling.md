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

### Diagram tooling: D2 + dagre

**Decision:** Switch from TALA to dagre as the D2 layout engine.

ELK, PlantUML, and Mermaid were evaluated earlier in the project. Dagre
has not been tried yet. It is bundled with D2 (no external dependency),
has no dimension limits, and — critically — requires zero changes to
`.d2` source files. The migration is a layout engine swap, not a format
rewrite.

**Trade-offs accepted:**
- Layout quality will be less compact than TALA. Acceptable — the
  per-module diagrams (5–15 classes each) are where readability matters
  most, and dagre handles those well.
- D2 itself depends on Terrastruct (dormancy risk). Accepted for now —
  the `.d2` syntax is human-readable and could be mechanically converted
  to another format later if needed. The Rust port will regenerate
  diagrams from scratch regardless.

**If dagre layout quality is unacceptable:** Re-evaluate PlantUML as
the fallback. The `.d2` source files would need conversion, but
`generate_module_diagrams.py` already parses the D2 structure and could
emit PlantUML instead.

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

### PR B: Switch diagram layout engine to dagre

**Scope:** Small — no `.d2` source file changes needed. The migration is
a config change + re-render + doc updates.

**Changes:**
1. In `tools/render_diagrams.sh`:
   - Change `RENDER_LAYOUT="tala"` → `RENDER_LAYOUT="dagre"`
   - Remove `DETAILED_TALA_SEEDS` variable and `--tala-seeds` flag
   - May need to adjust `RENDER_SCALE` / `RENDER_PAD` for dagre output
2. Re-render all SVGs with dagre:
   - `docs/diagrams/uml/diagram-detailed.svg`
   - `docs/diagrams/uml/diagram-modules.svg`
   - 18 per-module SVGs in `docs/diagrams/uml/modules/`
3. Visually review rendered output — especially the detailed diagram and
   a few representative per-module diagrams. If dagre layout quality is
   unacceptable, document what's wrong and evaluate PlantUML as fallback.
4. Update docs:
   - `docs/DIAGRAM.md` — remove TALA references, note dagre
   - `CLAUDE.md` — remove TALA/`d2plugin-tala` requirement if mentioned
   - `docs/BACKLOG.md` — update diagram tooling section to reflect
     decision
5. Remove TALA-specific backlog items (seeds workaround, dimension limit
   stripping proposal) if dagre resolves them.

**Files touched:**
- `tools/render_diagrams.sh` (layout engine + remove seeds)
- `docs/diagrams/uml/` — re-rendered SVGs (no `.d2` source changes)
- `docs/DIAGRAM.md`, `CLAUDE.md`, `docs/BACKLOG.md` (doc updates)

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

### Ordering

PRs A, B, and C are independent and can be developed in parallel. None
touches runtime code (PR C changes CLI plumbing and YAML extraction,
not the orchestrator itself).

## Out of scope

- Graph resumption (Phase 4 — next sprint)
- Documentation overhaul (Phase 5)
- New features or runtime code changes
- Backlog items deferred to Rust (see `docs/planning/pre-rust-roadmap.md`)
