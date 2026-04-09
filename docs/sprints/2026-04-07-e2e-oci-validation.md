# Sprint Plan — 2026-04-07: E2E Validation with OCI Isolation

> **Status: In progress.** PRs A, B, and C merged (#174, #175, #176). PR D next.

## Goal

Validate the complete system end-to-end with OCI containers before
freezing Python. This is Phase 2 of the pre-Rust roadmap.

Success criteria: representative graphs from every category pass with
OCI isolation enabled. The result is the behavioral baseline the Rust
port reimplements against.

## Context

Sprint 2026-04-06 shipped the `agentrelay` CLI and the `TaggedPath`
data model unification. The Python orchestrator's feature surface is
complete. What remains is proving it works under OCI isolation across
the full graph taxonomy, fixing what breaks, and cleaning up the graph
collection.

Currently only 3 graphs (all in `isolation/`) have OCI sandbox config.
The other 26 graphs run without isolation.

## Decisions

1. **CLI `--sandbox` override** — yes. Add `--sandbox oci` /
   `--sandbox none` flag so any graph can run in either mode without
   YAML changes.

2. **Graph consolidation:**
   - `graph_awareness/` 3→1: keep one graph, use `--model` for variants.
   - Remove `workstreams/diamond_4_workstreams_auto_merge_false.yaml`
     (`auto_merge: false` is the default — redundant with
     `diamond_4_workstreams.yaml`).
   - Remove `roles/experiments/` (all 4 single-role graphs). The full
     pipeline graph subsumes them.
   - Remove `roles/pipeline_compat.yaml` after confirming `paths:` sugar
     still works. Unit tests in `_parse_paths()` cover the sugar.
   - Move `gates/pixi_run_test.yaml` → `smoke/`. Gates are established
     functionality, not a separate test category.

3. **Credential testing:** Both API key and OAuth entries in the
   credentials YAML. OAuth is the primary credential for most runs.
   Some runs explicitly use `--anthropic-credential <api_key_name>` to
   exercise the env-var injection path.

4. **Target repo:** Continue using `agentrelaydemos`. Parallel graph
   runs safe by construction once graph index and tmux naming changes
   land.

5. **Role experiments:** Remove. Full pipeline is sufficient.

6. **`gates/` category:** Merge into `smoke/`.

7. **Graph index:** Require all graphs to be registered in an index
   that enforces name uniqueness. Graphs are selected by name from the
   index, not by raw file path. Scan-on-every-run (no stale index).

8. **Tmux session auto-detect:** Remove `tmux_session` from graph YAML
   schema. Auto-detect current tmux session when launched from within
   tmux. CLI `--tmux-session` / `-s` remains as an explicit override.

9. **Tmux window naming:** Change from bare `task_id` to
   `{graph_name}-{task_id}` so parallel graph runs in the same session
   cannot collide.

## Pre-work: graph audit and cleanup

### Current inventory (29 graphs, 9 categories)

| Category | Count | What they test |
|---|---|---|
| `smoke/` | 3 | Serial chain, parallel tasks, `inputs_from` chain |
| `workstreams/` | 6 | Diamond topologies (1ws, 4ws), auto-merge variants, serial ordering |
| `roles/` | 6 | 4-role pipeline (tagged_paths + compat), 4 single-role experiments |
| `concerns/` | 3 | Design concerns, ops concerns, concerns + auto-merge |
| `failure/` | 3 | Agent failure, blocked downstream, gate retry exhaustion |
| `isolation/` | 3 | Basic OCI, token tiers, permission boundary |
| `gates/` | 1 | Pixi pytest gate with implementer role |
| `graph_awareness/` | 3 | Spec-test-impl chain (haiku, sonnet, opus variants) |
| `adr/` | 1 | ADR generation with `adr_verbosity: standard` |

### Post-consolidation inventory (21 graphs, 8 categories)

| Category | Count | Changes |
|---|---|---|
| `smoke/` | 4 | +1 (gate graph moved in from `gates/`) |
| `workstreams/` | 5 | -1 (`auto_merge_false` removed) |
| `roles/` | 1 | -5 (4 experiments + compat removed) |
| `concerns/` | 3 | unchanged |
| `failure/` | 3 | unchanged |
| `isolation/` | 3 | unchanged |
| `graph_awareness/` | 1 | -2 (model variants removed; use `--model`) |
| `adr/` | 1 | unchanged |

`gates/` category removed (merged into `smoke/`).

### Syntax migration

Graphs being removed don't need migration. Only one remaining graph
uses old `paths:` syntax:
- `smoke/pixi_run_test.yaml` (moved from `gates/`) — migrate to
  `tagged_paths:`

## E2E validation scenarios

Scenarios to validate, organized by what could break under OCI.

### Agent lifecycle under OCI

| # | Scenario | What could break | Graph |
|---|---|---|---|
| 1 | Single task in container, creates PR, merges | Container startup, worktree mount, `gh` access | `isolation/basic_oci.yaml` |
| 2 | Serial task chain in containers | Signal file visibility, worktree freshness | `smoke/quick_chained.yaml` |
| 3 | Parallel tasks in separate containers | Concurrent container lifecycle | `smoke/quick_parallel.yaml` |
| 4 | Multi-task pipeline with roles and gates | Role templates + gate execution in containers | `roles/pipeline.yaml` |

### Credential and permission isolation

| # | Scenario | What could break | Graph |
|---|---|---|---|
| 5 | Token tier differentiation (standard vs read_only) | Env var injection, PAT scoping | `isolation/token_tiers.yaml` |
| 6 | Permission boundary (can't push to main) | Pre-push hook in container | `isolation/permission_boundary.yaml` |
| 7 | Anthropic API key injection | `_ANTHROPIC_API_KEY` env var in container | Any OCI graph + `--anthropic-credential <api_key>` |
| 8 | Anthropic OAuth injection | Volume mount of credentials file | Any OCI graph + `--anthropic-credential <oauth>` |

### Cross-task data flow under OCI

| # | Scenario | What could break | Graph |
|---|---|---|---|
| 9 | `inputs_from` resolution | Upstream `outputs.json` readable from downstream container | `smoke/inputs_from_chain.yaml` |
| 10 | Graph awareness (graph YAML mount) | Read-only `.workflow/<graph>/graph.yaml` mount | `graph_awareness/spec_test_impl.yaml` |
| 11 | ADR instructions in container | ADR policy file accessible | `adr/adr_standard.yaml` |

### Workstream topology under OCI

| # | Scenario | What could break | Graph |
|---|---|---|---|
| 12 | Diamond across workstreams | Cross-workstream gate checking | `workstreams/diamond_4_workstreams.yaml` |
| 13 | Auto-merge with OCI | Integration PR creation + auto-merge | `workstreams/diamond_4_workstreams_auto_merge.yaml` |
| 14 | Serial workstream ordering | Task serialization within one workstream | `workstreams/serial_workstream.yaml` |

### Failure handling under OCI

| # | Scenario | What could break | Graph |
|---|---|---|---|
| 15 | Agent signals failure from container | `.failed` sentinel from container | `failure/agent_fails.yaml` |
| 16 | Blocked downstream after failure | Upstream fails, downstream never launches | `failure/blocked_downstream.yaml` |
| 17 | Gate retry exhaustion | Container teardown/relaunch on retry | `failure/retry_on_gate_failure.yaml` |

### Concern capture under OCI

| # | Scenario | What could break | Graph |
|---|---|---|---|
| 18 | Design concern from container | `agentrelay-concern` writes to signal dir | `concerns/log_concerns.yaml` |
| 19 | Ops concern from container | `agentrelay-ops-concern` writes from container | `concerns/log_ops_concerns.yaml` |
| 20 | Concerns block auto-merge | Concern-gated auto-merge with containerized agent | `concerns/log_concerns_automerge_enabled.yaml` |

## Parallel e2e run notes

After PRs A–D land, parallel graph runs are safe by construction:

- **Graph index** enforces unique names within a graph directory.
- **Tmux windows** use `{graph_name}-{task_id}`, so different graphs
  cannot collide even in the same tmux session.
- All other resources (worktrees, signals, branches, PRs, Docker
  containers/networks) are already graph-namespaced.
- The existing `_check_for_conflicts()` guard prevents concurrent runs
  of the same graph.

No special preconditions needed — just run from the same tmux session:
```
agentrelay run quick-chained -t /data/git/agentrelaydemos/main ...
agentrelay run diamond-4-workstreams -t /data/git/agentrelaydemos/main ...
```

---

## PR plan

### PR A: CLI short options and `--sandbox` override — merged (#174)

- Branch: `feat/cli-short-options`

Add short forms for frequently-used flags and a `--sandbox` CLI
override that lets any graph run in OCI or non-OCI mode without
modifying graph YAML.

**Changes:**
- `src/agentrelay/cli.py` — add short option aliases; add `--sandbox`
  / `-S` argument (`oci` | `none`) to `run` subcommand.
- `src/agentrelay/run_graph.py` — accept `sandbox_override` parameter;
  apply it to all tasks when set. Add short options to `_build_parser()`
  for parity.
- `src/agentrelay/orchestrator/` — wire `sandbox_override` through
  config/builder chain.
- Tests: unit tests for CLI parsing and sandbox override propagation.
- `CLAUDE.md` — update command table with short options.

**Short options:**

| Long form | Short |
|---|---|
| `--target-repo` | `-t` |
| `--model` | `-m` |
| `--max-concurrency` | `-c` |
| `--tmux-session` | `-s` |
| `--credentials` | `-C` |
| `--sandbox` | `-S` |

**Acceptance criteria:**
- [ ] `agentrelay run -t <repo> -m <model> -c 2 -s mysession graphs/smoke/quick_chained.yaml` works
- [ ] `agentrelay run -S oci graphs/smoke/quick_chained.yaml` applies
      OCI to all tasks
- [ ] `agentrelay run -S none graphs/isolation/basic_oci.yaml` disables
      OCI even if graph YAML specifies it
- [ ] Short options also work on `run_graph.py` direct invocation
- [ ] `pixi run check` passes

---

### PR B: Graph index and name-based selection — merged (#175)

- Branch: `feat/graph-index`

Introduce a graph index that scans a directory for graph YAML files,
validates name uniqueness, and lets graphs be selected by name instead
of file path.

**Design:**
- `agentrelay run <name> -g <graph-dir>` resolves `<name>` via the
  index built from `<graph-dir>`.
- The index is built by scanning the graph directory recursively for
  `.yaml` files, reading the `name:` field from each, and building a
  `{name: path}` mapping. Duplicate names → error at scan time.
- `--graph-dir` / `-g` is required when using name-based selection.
  No hardcoded default — in agentrelay dev we pass `-g graphs/`, in
  a target repo the user passes `-g` pointing to their graph directory.
- Scan happens on every run (21 YAML files is negligible).
- If the `graph` argument contains `/` or ends in `.yaml`, treat it as
  a path but validate that it is present in the index. No un-indexed
  graphs allowed when `-g` is specified.
- If `-g` is not specified, the `graph` argument is treated as a file
  path (backward compatible — no index involved).
- `agentrelay list -g <dir>` — new subcommand that prints a table of
  available graphs (name, category/subdirectory, path).

**Changes:**
- `src/agentrelay/cli.py` — add `--graph-dir` / `-g` arg to `run`,
  `reset`, `dry-run` subcommands; add `list` subcommand; resolve graph
  name → path before delegating.
- New module (e.g., `src/agentrelay/graph_index.py`) for index
  scanning, validation, and resolution.
- Tests: unit tests for index scanning, uniqueness enforcement,
  name resolution, path-based validation.

**Acceptance criteria:**
- [ ] `agentrelay run quick-chained -g graphs/` resolves and runs the
      graph
- [ ] `agentrelay run graphs/smoke/quick_chained.yaml -g graphs/`
      validates path is in the index
- [ ] `agentrelay run graphs/smoke/quick_chained.yaml` (no `-g`)
      works as before (backward compatible)
- [ ] Duplicate graph names in the same directory → clear error
- [ ] `agentrelay list -g graphs/` prints name/category/path table
- [ ] `pixi run check` passes

---

### PR C: Tmux session auto-detect and window naming — merged (#176)

- Branch: `feat/tmux-auto-session`

Remove `tmux_session` from the graph YAML schema. Auto-detect the
current tmux session. Prefix tmux window names with the graph name
to prevent collisions during parallel runs.

**Design:**
- **Session resolution order:**
  1. CLI `--tmux-session` / `-s` (explicit override)
  2. Current tmux session (detect via `tmux display-message -p '#S'`
     when `$TMUX` env var is set)
  3. Error: "not in a tmux session and --tmux-session not specified"
- **Window naming:** change from `task_id` to `{graph_name}-{task_id}`.
- **Graph YAML cleanup:** Remove `tmux_session:` from all 26 graph
  YAML files, from `_extract_operational_config()`, and from
  `_apply_overrides()`. Remove from CLAUDE.md graph YAML schema.

**Changes:**
- `src/agentrelay/ops/tmux.py` — add `current_session()` function.
- `src/agentrelay/agent/implementations/tmux_agent.py` — change
  window name from `task_id` to `{graph_name}-{task_id}`.
- `src/agentrelay/run_graph.py` — change session resolution to use
  auto-detect; remove `tmux_session` from `_extract_operational_config`
  and `_apply_overrides`.
- `src/agentrelay/cli.py` — session comes from CLI or auto-detect,
  not from graph YAML.
- All 26 graph YAML files — remove `tmux_session: agentrelay` line.
- `CLAUDE.md` — remove `tmux_session` from graph YAML schema.
- Tests: unit tests for `current_session()`, session resolution
  priority, window name format.

**Acceptance criteria:**
- [ ] Launched from within tmux: auto-detects session, no
      `--tmux-session` needed
- [ ] Launched outside tmux without `--tmux-session`: clear error
- [ ] `--tmux-session` overrides auto-detection
- [ ] Tmux windows named `{graph_name}-{task_id}`
- [ ] No graph YAML contains `tmux_session:`
- [ ] Parallel runs of different graphs in same tmux session produce
      distinct window names
- [ ] `pixi run check` passes

---

### PR D: Graph consolidation and syntax migration

- Branch: `feat/graph-consolidation`

Remove redundant graphs, consolidate categories, and migrate remaining
old `paths:` syntax to `tagged_paths:`.

**Removals (8 graphs):**
- `graph_awareness/spec_test_impl_haiku.yaml` — use `--model` instead
- `graph_awareness/spec_test_impl_opus.yaml` — use `--model` instead
- `workstreams/diamond_4_workstreams_auto_merge_false.yaml` — default
  behavior, redundant
- `roles/pipeline_compat.yaml` — backward-compat shim, unit tests
  cover the sugar
- `roles/experiments/concern_spec_writer.yaml` — subsumed by pipeline
- `roles/experiments/concern_test_writer.yaml` — subsumed by pipeline
- `roles/experiments/concern_test_reviewer.yaml` — subsumed by pipeline
- `roles/experiments/concern_implementer.yaml` — subsumed by pipeline

**Moves:**
- `gates/pixi_run_test.yaml` → `smoke/pixi_run_test.yaml`
- Remove empty `gates/` directory
- Remove empty `roles/experiments/` directory

**Renames:**
- `graph_awareness/spec_test_impl_sonnet.yaml` →
  `graph_awareness/spec_test_impl.yaml` (drop model from filename;
  model comes from `--model` or graph-level default)

**Syntax migration:**
- `smoke/pixi_run_test.yaml` (moved from gates): `paths:` →
  `tagged_paths:`

**Other cleanup:**
- Update any README files in `graphs/` subdirectories if they
  reference removed files.
- Remove `roles/fixtures/` if only used by the removed experiments
  (check first — the pipeline graph may also use BoundedQueue fixtures).

**Acceptance criteria:**
- [ ] 21 graphs remain (down from 29)
- [ ] `gates/` directory removed
- [ ] `roles/experiments/` directory removed
- [ ] No graph uses old `paths:` syntax
- [ ] All graph names unique (passes index validation via
      `agentrelay list -g graphs/`)
- [ ] `pixi run check` passes

---

### PR E: E2E validation runs and fixes

- Branch: `feat/e2e-oci-validation`

Run all 21 graphs with `-S oci` against `agentrelaydemos`. Fix
whatever breaks. This is the validation PR — it may be one PR or
split into several if different categories surface independent issues.

**Approach:**
1. Baseline run: run a representative subset *without* OCI to confirm
   graphs pass on current main. Catches pre-existing issues before
   adding the OCI variable.
2. OCI run: run all graphs with `-S oci`. Log results per scenario
   (referencing the 20 scenarios above).
3. Fix: for each failure, diagnose root cause (container infra,
   credential, signal file visibility, etc.). Fix and re-run.
4. Document: record which scenarios passed, which required fixes, and
   any remaining known issues.

**Credential testing:**
- Most runs use `--anthropic-credential <oauth_name>` (Max plan OAuth).
- At least one run per category uses
  `--anthropic-credential <api_key_name>` to exercise the env-var
  injection path.

**Parallel execution:**
- Run graphs from different categories in parallel in the same tmux
  session. Safe by construction after PRs A–D.

**Changes (expected, TBD based on what breaks):**
- Fixes to `sandbox/`, `ops/`, or `orchestrator/` code
- Possible adjustments to Docker image or setup scripts
- Any necessary signal dir or mount path fixes

**Acceptance criteria:**
- [ ] All 20 scenarios pass with OCI isolation
- [ ] Both API key and OAuth credential injection validated
- [ ] Results documented (which graphs ran, which scenarios covered)
- [ ] `pixi run check` passes
- [ ] No regressions in non-OCI mode

---

## Dependency ordering

```
PR A (short options + sandbox) ─┐
                                ├──→ PR C (tmux) → PR D (graph consolidation) → PR E (e2e)
PR B (graph index) ─────────────┘
```

**PR A** and **PR B** are independent — A adds CLI flags and sandbox
override, B adds the graph index. No shared files. Can be developed
in parallel.

**PR C** depends on A and B merging first. It modifies `cli.py` (which
A and B both touch) and removes `tmux_session:` from all graph YAML
files. Having A and B stable first avoids three-way conflicts.

**PR D** depends on C. It removes/moves graph YAML files that C just
cleaned up (removed `tmux_session:` lines). Merging D on top of C
avoids touching the same files twice.

**PR E** depends on all of A–D. It uses `-S oci` from A, name-based
selection from B, auto-detected tmux sessions from C, and the
consolidated graph set from D.

## Known issue: TALA diagram rendering

The detailed diagram (`diagram-detailed.d2`) now exceeds TALA's internal
dimension limit (~32k x 28k) on all seeds 0–20. Per-module diagrams and
the module overview still render fine. This was marginal before PR B
(graph_index added 4 nodes) and is a pre-existing limitation of the
TALA layout engine.

**Proposed fix (this sprint):** Strip private/internal blocks
(`<<module>>` stereotype, `_`-prefixed) from the detailed diagram source
and keep them only in the per-module diagrams. Requires a small change
to `generate_module_diagrams.py` to support a two-tier source (public
surface in detailed, full internals in per-module). This would
significantly reduce node count in the detailed layout and restore
rendering headroom.

This can be a standalone PR slotted anywhere in the dependency chain
(no functional code changes).

## What comes after this sprint

Per `docs/planning/pre-rust-roadmap.md`:

- **Freeze Python, begin Rust.** Gate: all 20 scenarios pass with OCI.
  The Python codebase becomes the behavioral spec; the e2e graphs become
  the Rust port's acceptance criteria.
