# Sprint Notes — 2026-04-06: CLI & Data Model Cleanup

> **Status: Complete.** Both PRs (A–B) merged, plus a follow-up fix (#171).
> PRs developed in parallel across git worktrees; merged B→A with no
> conflicts. 1348 tests after all PRs landed.

## Goal

Make the Python orchestrator feel like a real tool and unify the data
model before freezing Python for the Rust migration.

This is the second and final pre-Rust sprint. After this, the remaining
work is e2e validation with OCI isolation, then Rust begins.

## Context

Sprint 2026-04-05 shipped `inputs_from`, integration PR body refinement,
and the final fail-fast CLI flag. The output-driven composition pipeline
is functional end-to-end: agents declare outputs via `agentrelay-declare`,
downstream tasks consume them via `inputs_from`, and the orchestrator
resolves everything at prepare time.

Two gaps remain before the Python version is ready to freeze:

1. **No user-facing CLI.** The entry point is `python -m agentrelay.run_graph`
   — functional but not discoverable. There's no `agentrelay` command.
   The `pixi run e2e` wrapper exists but is developer-oriented.

2. **Dual path taxonomy.** `TaskPaths` (`src`/`test`/`spec`) and output
   manifest categories (`stubs`, `tests`, `implementation`) coexist.
   Both describe the semantic role of files a task works with, but
   `TaskPaths` is a fixed three-slot taxonomy while categories are
   free-form and proved more flexible. With `inputs_from` validating
   category-based resolution end-to-end, `TaskPaths` is now redundant.
   If it ships to Rust, the Rust port carries both systems.

See `docs/planning/pre-rust-roadmap.md` for the overall pre-Rust strategy.

## Architecture notes

**Top-level CLI (PR A):** Register an `agentrelay` console script in
`pyproject.toml` with subcommands: `run`, `reset`, `check`, `dry-run`.

Current CLI surface:
- `python -m agentrelay.run_graph <graph> [flags]` — run a graph (cd to
  target repo first)
- `python -m agentrelay.reset_graph <graph> [flags]` — reset a graph run
- `pixi run e2e <graph> <target-repo> [flags]` — wrapper that cd's to
  target repo

Proposed:
```
agentrelay run <graph.yaml> [--target-repo <path>] [flags]
agentrelay reset <graph.yaml> [--target-repo <path>]
agentrelay check [--target-repo <path>]
agentrelay dry-run <graph.yaml>
```

`--target-repo` defaults to the current directory (same as `run_graph.py`
today). Someone working in a target repo types `agentrelay run graph.yaml`.

Implementation: a single `src/agentrelay/cli.py` module with `argparse`
subcommands. Each subcommand delegates to the existing `run_graph.main()`
or `reset_graph.main()` functions (or their underlying async functions).
The `pixi run e2e` wrapper remains as an internal convenience for
agentrelay developers running cross-repo tests.

Changes touch:
- `src/agentrelay/cli.py` — new module, subcommand dispatch
- `pyproject.toml` — add `agentrelay = "agentrelay.cli:main"` to
  `[project.scripts]`
- `CLAUDE.md` — update command table
- `docs/GUIDE.md` — update CLI examples

**Replace `TaskPaths` (PR B):** Remove `TaskPaths` entirely and replace
with category-tagged file lists on the manifest.

Current state:
- `TaskPaths` (task.py:88-100) has three fields: `src`, `test`, `spec`
- `Task.paths: TaskPaths` (task.py:200)
- `TaskManifest` has `src_paths`, `test_paths`, `spec_path` (manifest.py:86-88)
- `build_manifest()` extracts `task.paths.src`, `.test`, `.spec` (manifest.py:128-130)
- `manifest_to_dict()` serializes a `"paths"` section (manifest.py:164-168)
- `templates.py` substitutes `$src_paths`, `$test_paths`, `$spec_path`
  into role templates (templates.py:161-169)
- All 4 role templates use `$src_paths` and/or `$test_paths`
- `builder.py` parses `paths:` from YAML via `_parse_paths()` → `TaskPaths`

Target state:
- `TaskPaths` class deleted
- `Task` stores paths as category-tagged tuples (e.g.,
  `tagged_paths: tuple[TaggedPath, ...]` where `TaggedPath` has `path`,
  `category`)
- Graph YAML `paths:` still parses — `paths.src` becomes entries with
  `category="src"`, `paths.test` becomes `category="test"`, `paths.spec`
  becomes a single entry with `category="spec"`. Backward compatible.
- `TaskManifest` replaces `src_paths`/`test_paths`/`spec_path` with a
  single `tagged_paths: tuple[TaggedPath, ...]` field
- `manifest_to_dict()` serializes as a `"paths"` list of
  `{"path": "...", "category": "..."}` objects — same shape as
  `"input_files"` for consistency
- Role templates use `$paths_by_category` or similar — the template
  substitution builds a formatted string from the tagged paths, grouped
  by category. E.g., spec_writer gets `"src: path/to/file.py"` instead
  of `$src_paths`
- `input_files` (from `inputs_from`) and `tagged_paths` (from `paths:`)
  coexist on the manifest. They serve different purposes:
  `tagged_paths` = explicitly declared by graph author;
  `input_files` = resolved at runtime from upstream outputs

Key design decision: `TaggedPath` vs raw tuples. A small frozen dataclass
(`path: Path`, `category: str`) is clearest and consistent with
`InputFileInfo`. The category strings are the same free-form strings used
by `OutputEntry.category` — no enum yet (deferred to Rust per backlog).

Changes touch:
- `src/agentrelay/task.py` — delete `TaskPaths`, add `TaggedPath`, change
  `Task.paths` to `Task.tagged_paths: tuple[TaggedPath, ...]`
- `src/agentrelay/task_graph/builder.py` — `_parse_paths()` returns
  `tuple[TaggedPath, ...]` instead of `TaskPaths`
- `src/agentrelay/agent_comm_protocol/manifest.py` — replace
  `src_paths`/`test_paths`/`spec_path` with `tagged_paths`
- `src/agentrelay/agent_comm_protocol/templates.py` — change template
  substitution to use category-grouped formatting
- `src/agentrelay/templates/*.md` — update 4 role templates to use new
  variables
- `test/test_task.py` — remove `TestTaskPaths`, add `TestTaggedPath`
- `test/agent_comm_protocol/test_manifest.py` — update manifest tests
- `test/agent_comm_protocol/test_templates.py` — update template tests
- `test/task_graph/test_task_graph_builder.py` — update YAML parsing tests
- `docs/diagrams/uml/diagram-detailed.d2` — update task module diagram
- `CLAUDE.md` — if schema docs reference `TaskPaths`

Graph YAML files do NOT need changes — the `paths:` syntax is preserved
as sugar.

---

## PR plan

### PR A: `agentrelay` top-level CLI

- Branch: `feat/cli-entry-point`

Register an `agentrelay` console script with subcommands for run, reset,
check, and dry-run.

**Changes:**
- `src/agentrelay/cli.py` — new module with `argparse` subcommands
  delegating to `run_graph` and `reset_graph`.
- `pyproject.toml` — add `agentrelay = "agentrelay.cli:main"` entry point.
- `CLAUDE.md` — update command table with `agentrelay` commands.
- `pixi.toml` — optionally add `pixi run agentrelay` task.

**Acceptance criteria:**
- [ ] `agentrelay run <graph> [flags]` runs a graph (equivalent to
      `python -m agentrelay.run_graph`)
- [ ] `agentrelay reset <graph> [flags]` resets a graph run
- [ ] `agentrelay dry-run <graph>` validates and prints execution plan
- [ ] `--target-repo <path>` overrides the working directory (defaults to
      cwd)
- [ ] All existing `run_graph.py` flags pass through correctly
- [ ] `agentrelay --help` shows available subcommands
- [ ] `pixi run check` passes

---

### PR B: Replace `TaskPaths` with category-tagged paths

- Branch: `feat/replace-task-paths`

Remove `TaskPaths` and unify path handling through category-tagged
entries, ensuring the Rust port builds on a single path taxonomy.

**Changes:**
- `src/agentrelay/task.py` — delete `TaskPaths`, add `TaggedPath`
  dataclass, change `Task.paths` → `Task.tagged_paths`.
- `src/agentrelay/task_graph/builder.py` — `_parse_paths()` returns
  `tuple[TaggedPath, ...]`. Graph YAML `paths:` syntax preserved.
- `src/agentrelay/agent_comm_protocol/manifest.py` — replace
  `src_paths`/`test_paths`/`spec_path` with `tagged_paths`.
- `src/agentrelay/agent_comm_protocol/templates.py` — category-grouped
  path formatting for template substitution.
- `src/agentrelay/templates/*.md` — update 4 role templates.
- Tests: update `test_task.py`, `test_manifest.py`, `test_templates.py`,
  `test_task_graph_builder.py`.
- `docs/diagrams/uml/diagram-detailed.d2` — update task module.

**Acceptance criteria:**
- [ ] `TaskPaths` class no longer exists in the codebase
- [ ] Graph YAML `paths:` still parses (backward compatible)
- [ ] `paths.src` entries appear with `category="src"` in manifest
- [ ] `paths.test` entries appear with `category="test"` in manifest
- [ ] `paths.spec` entries appear with `category="spec"` in manifest
- [ ] Role templates render correctly with category-grouped paths
- [ ] `inputs_from` resolution still works (no regression)
- [ ] `manifest.json` serialization uses the new `"paths"` list format
- [ ] `pixi run check` passes

---

## Dependency ordering

PR A (CLI) and PR B (TaskPaths replacement) are independent. They touch
entirely different areas of the codebase:

- PR A: `cli.py` (new), `pyproject.toml`, `CLAUDE.md`
- PR B: `task.py`, `builder.py`, `manifest.py`, `templates.py`,
  template markdown files, tests, diagram

No shared files. Both developed in parallel across worktrees and merged
in any order. Actual merge order: B first (#169), then A (#170).

## Merge log

| Order | PR | Title | Merge commit |
|---|---|---|---|
| 1 | #169 (B) | feat: replace TaskPaths with category-tagged TaggedPath | `9f49f6e` |
| 2 | #170 (A) | feat: agentrelay top-level CLI | `992724f` |
| 3 | #171 | fix: work around TALA dimension limit with seed selection | `4a26379` |

PR #171 was a follow-up fix: the detailed diagram (~80+ classes) exceeded
TALA's internal dimension limit after the TaggedPath rename in PR B.
Resolved by passing `--tala-seeds` with seeds that produce layouts within
the limit. Also added a diagram tooling evaluation item to the backlog.

## What comes after this sprint

Per `docs/planning/pre-rust-roadmap.md`:

1. **E2E validation with OCI isolation** — run representative graphs
   across all categories with OCI enabled. Fix what breaks. This produces
   the behavioral baseline for the Rust port.
2. **Freeze Python, begin Rust.**
