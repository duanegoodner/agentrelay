# Changelog

Chronological log of significant changes to the main codebase. For full details see each PR on GitHub.

---

## 2026-04-09

### CLI cleanup and diagram tooling (sprint 2026-04-09 PRs A–G)

- **CLI cleanup** (PR #180): Fix `--max-concurrency` help text, add short
  options (`-a`, `-d`, `-T`, `-A`, `-C`, `-S`, `-W`, `-I`), shorten flag
  names (`--fail-fast-workstream`, `--fail-fast-internal`).
- **ELK layout engine** (PR #181): Switch from TALA to ELK for D2 diagram
  rendering. Drop monolith `diagram-detailed.svg` (source `.d2` remains
  as input to per-module generation). All 19 SVGs re-rendered.
- **Graph YAML config fields** (PR #182): `max_concurrency`,
  `max_task_attempts`, `teardown_mode` as graph-level YAML fields with
  CLI-wins precedence. `--keep-panes` CLI flag for existing YAML field.
  `OperationalConfig` dataclass replaces raw tuple.
- **OCI container retry fix** (PR D): Attempt-indexed container names
  (`agentrelay-{graph}-{task_id}-{attempt}`) and tmux window names prevent
  `docker run` name collisions on retry. `SandboxContext.attempt_num` field
  carries attempt number to sandbox operations. Sandbox instance stored on
  `TaskArtifacts`; `WorktreeTaskTeardown` calls `sandbox.teardown()` behind
  the existing `_should_teardown()` gate.
- **Default teardown mode → ALWAYS** (PR E): Change
  `OrchestratorConfig.task_teardown_mode` default from `ON_SUCCESS` to
  `ALWAYS`. Tmux panes, branches, and containers are now cleaned up on
  both success and failure. Persistent artifacts (`agent.log`,
  `summary.md`, per-attempt archives) provide the same debugging data.
  `ON_SUCCESS` and `NEVER` remain available via `-T` or graph YAML.
- **Record effective run config** (PR F): After CLI > YAML > default
  resolution, write `.workflow/<graph>/run_config.json` with the effective
  `OrchestratorConfig` fields plus model, sandbox, credential, keep_panes,
  and verbose settings. Provides a complete post-mortem record of what
  values were actually used for a run.
- **Uniform per-attempt signal directories** (PR G): Agent-written
  artifacts (`.done`, `.failed`, `concerns.log`, `ops_concerns.log`,
  `summary.md`, `agent.log`, `gate_last_output.txt`) now live under
  `signal_dir/attempts/<N>/` for every attempt, including the current
  one. Eliminates the split between archived and current-attempt layouts.
  Removes `_archive_attempt_artifacts()` and `_clear_agent_signals()`
  from `reset_for_retry()`. Orchestrator-managed files (`manifest.json`,
  `instructions.md`, `status/`, `outputs.json`) stay at signal_dir level.

---

## 2026-04-05

### Output composition and execution polish (sprint 2026-04-05 PRs A–C)

- **`inputs_from` graph YAML extension** (PR #163): `InputsFrom` dataclass
  and optional `inputs_from` field on `Task`. Downstream tasks reference
  upstream outputs by task ID and optional category. Orchestrator resolves
  `inputs_from` at prepare time by reading upstream `outputs.json`, filtering
  by category, and merging with explicit `paths`. Validation rejects
  references to non-dependency tasks. Resolved input files appear in
  `manifest.json` and agent instructions ("Input Files" section). Added
  `graphs/smoke/inputs_from_chain.yaml` e2e graph. Design philosophy:
  `inputs_from` is guidance, not restriction — agents retain full graph
  awareness and can explore beyond declared inputs.
- **Integration PR body refinement** (PR #164): `TaskSummary.summary_text`
  field populated from `summary.md` in each task's signal directory.
  Integration PR body now includes agent-written summaries as collapsible
  `<details>` sections. Long task descriptions truncated. Tasks without
  descriptions fall back to task ID + role instead of "(no description)".
- **`fail_fast_on_internal_error` CLI flag** (PR #165):
  `--fail-fast-on-internal-error` / `--no-fail-fast-on-internal-error` CLI
  flag and `fail_fast_on_internal_error` graph YAML field. Precedence: CLI
  overrides YAML, YAML overrides default (`True`). Completes the fail-fast
  configuration surface (workstream error flag shipped in PR #159).
- All 3 PRs developed in parallel across git worktrees, merged sequentially.
  1348 tests (75 new).

---

## 2026-04-04

### Execution quality and output manifests (sprint 2026-04-04 PRs A–E)

- **Capture agent.log on task failure** (PR #157): Extracted scrollback
  capture from `TmuxAddress.teardown()` into a new `capture_log()` method on
  `AgentAddress` / `TmuxAddress`. Added `TaskLogCapture` protocol and
  `WorktreeTaskLogCapture` implementation as a new task runner lifecycle step.
  `StandardTaskRunner.run()` calls `capture_log()` unconditionally in the
  `finally` block before the teardown decision. `TmuxAddress.teardown()` skips
  redundant capture if `agent.log` already exists (idempotent).
- **Retry agent awareness** (PR #158): New `## Previous Attempts` section in
  agent instructions when `attempt_num > 0`. Lists archived attempt
  directories with absolute paths, artifact filenames (`agent.log`,
  `gate_last_output.txt`, `summary.md`, `concerns.log`, `ops_concerns.log`),
  and guidance to review prior scrollback and identify root cause before
  writing code.
- **CLI and graph YAML control for fail-fast** (PR #159):
  `--no-fail-fast-on-workstream-error` CLI flag and
  `fail_fast_on_workstream_error` graph YAML field. Precedence: CLI overrides
  YAML, YAML overrides default (`True`). `fail_fast_on_internal_error` stays
  always-on (no flag). Updated `blocked_downstream.yaml` e2e graph to use
  the new field.
- **Skip empty integration PR** (PR #160): `GhWorkstreamIntegrator` checks
  `git.rev_list_count()` before calling `gh pr create`. If the integration
  branch has zero commits ahead of the base, transitions the workstream
  directly to MERGED — no integration PR created. Added `rev_list_count()`
  to `ops/git.py` and "skipped_integration" event to `ConsoleListener`.
- **Output manifests and `agentrelay-declare`** (PR #161):
  `OutputManifest` / `OutputEntry` data models in `agent_sdk/output_manifest.py`.
  `agentrelay-declare` CLI (`--path`, `--action created|modified`,
  `--category`) appends to `signal_dir/outputs.json`. `TaskHelper.declare_output()`
  convenience method. `outputs.json` added to Graph Awareness artifact listing
  in instructions. `agentrelay-declare` guidance added to "Submitting Your
  Work" section. Foundation for output-driven task composition
  (`docs/discussions/OUTPUT_DRIVEN_COMPOSITION.md`).
- All 5 PRs developed in parallel across git worktrees, merged sequentially.
  1273 tests (39 new).

---

## 2026-04-03

### Agent graph awareness (sprint 2026-04-03 PR A)

- **Graph YAML delivery** (`run_graph.py`): Single copy of the source graph
  YAML written to `.workflow/<graph>/graph.yaml` at startup, alongside the
  existing `run_info.json`. Byte-for-byte copy preserves comments and
  formatting. Agents derive the path from their signal directory (navigate
  up two levels).
- **Graph Awareness instructions** (`templates.py`): New conditional
  `## Graph Awareness` section in agent instructions. Includes: graph YAML
  absolute path, signal directory formula
  (`<signals_base>/<task-id>/`), per-task artifact names (`summary.md`,
  `concerns.log`, `ops_concerns.log`, `.done`), guidance on reading upstream
  summaries before starting work, and guidance on tailoring own summary for
  downstream consumers visible in the graph YAML.
- **OCI read-only mount** (`oci_sandbox.py`): `.workflow/<graph>/` mounted
  read-only in containers so isolated agents can read peer signal directories
  and the graph YAML. Agent's own signal directory remains read-write via
  existing mount (overlays the read-only parent for that subtree).
- **Isolation section update** (`templates.py`): "Workflow directory
  (read-only)" added to "What You Can Access". "Signal directories" removed
  from "What You Cannot Access".
- **Task preparer** (`task_preparer.py`): Passes `graph_yaml_path` and
  `signals_base_path` to `resolve_instructions()`.
- **Design docs**: Context-sharing design moved to
  `docs/discussions/CONTEXT_SHARING.md`. Output-driven composition design
  added at `docs/discussions/OUTPUT_DRIVEN_COMPOSITION.md`.
- **E2E test graphs**: `graphs/graph_awareness/spec_test_impl_{sonnet,haiku,opus}.yaml`
  — 3-task generic pipeline (spec→test→impl) with no `paths` fields and no
  role templates. Agents discover file locations from upstream summaries.
- 1234 tests (16 new). E2E validated: all tasks succeeded first attempt with
  Sonnet; gate passed first try.

---

## 2026-04-02

### Agent experience improvements (sprint 2026-04-01 PRs A–E)

- **`agentrelay-complete` retry fix** (PR #149): `create_pr()` probes for
  existing open PR before calling `gh pr create`; reuses it on retry. Updates
  body via `gh api` REST (not `gh pr edit`) to avoid GraphQL deprecation.
- **`COMPLETED` task status** (PR #150): New `TaskStatus.COMPLETED` for
  PR-less tasks instead of misusing `PR_MERGED`. `SUCCESS_STATUSES` frozenset
  centralizes the "task succeeded" check across 8 consumer sites.
- **`agentrelay-summary` CLI** (PR #151): New `agentrelay-summary --message`
  CLI and `TaskHelper.write_summary()` for PR-less task summaries.
- **Worktree CWD guidance** (PR #152): `## Working Directory` section in
  agent instructions with explicit worktree path to prevent Level 0 agents
  from navigating out of the worktree.
- **Retry artifact archive** (PR #153): `reset_for_retry()` copies
  agent.log, gate_last_output.txt, summary.md, concerns.log to
  `signal_dir/attempts/<N>/` before clearing signals.

---

## 2026-03-31

### OAuth and consolidated Anthropic credentials for containers (sprint 2026-03-30 PR A)

- **Container startup script** (`setup-credentials.py`): Generates
  `~/.claude/settings.json` at container startup instead of pre-seeding
  at build time. API key mode includes `apiKeyHelper`; OAuth mode omits
  it so Claude Code reads `.credentials.json` natively. Also copies
  OAuth credentials from read-only mount to writable location for token
  refresh.
- **Dockerfile update**: Removed baked-in `settings.json`. Added
  `claude-setup-credentials` to the startup chain (before
  `claude-trust-workdir`).
- **Consolidated credentials YAML**: New `anthropic` section with named,
  typed entries replacing the old `defaults` section. `CredentialType`
  enum (`api_key`, `oauth`) and `AnthropicCredential` frozen dataclass.
  `api_key` entries support `key` (inline) or `key_file` (read from
  file, tilde-expanded, whitespace-stripped) to keep secrets portable.
- **OciSandbox**: Accepts `AnthropicCredential | None` instead of raw
  path. Type-aware injection: `_ANTHROPIC_API_KEY` env var for API key
  mode, read-only volume mount for OAuth mode. Defensive guard rejects
  `ANTHROPIC_API_KEY` in `SandboxContext.env_vars`.
- **CLI**: `--anthropic-credential <name>` selects a named credential.
  Auto-selects when single entry, errors clearly with multiple. Graph
  YAML `anthropic_credential` operational key provides a default
  (CLI overrides).
- **FileCredentialProvider**: `resolve()` returns tier-only env vars
  (no more defaults merge). New `resolve_anthropic()` method with
  name lookup or auto-select. `anthropic_names` property.
- **Docs**: Credentials YAML schema in `SCHEMA.md`, three example
  credential files (`credentials-api-key.yaml`, `credentials-oauth.yaml`,
  `credentials-both.yaml`).
- 1187 tests (29 new). E2E validated both API key and OAuth modes with
  `basic_oci.yaml`.

---

## 2026-03-30

### Remaining e2e isolation testing (sprint 2026-03-26 PR F2)

- **token_tiers e2e**: Verified correct credential scoping across token tiers.
  `standard_task` (standard tier) pushed, created PR, and succeeded.
  `readonly_task` (read_only tier) pushed but failed at PR creation (403 —
  token lacks `pull_requests: write` scope). Agent recorded an ops concern
  about the missing permission. Graph outcome: `COMPLETED_WITH_FAILURES`.
- **permission_boundary e2e**: Verified pre-push hook blocks agent push to
  main. Agent attempted `git push origin HEAD:refs/heads/main`, hook rejected
  it (`IS_AI_AGENT=true`), agent recorded an ops concern with the exact hook
  error message, then recovered by pushing to its task branch and completing
  normally. Graph outcome: `SUCCEEDED` (48s).
- **permission_boundary.yaml fix**: Changed `token_tier` from `read_only` to
  `standard` so the test exercises the pre-push hook rather than a PAT
  permission denial.

---

### Container e2e infrastructure fixes (sprint 2026-03-26 PR Fcleanup)

- **UID alignment**: Docker base image creates `agent` user with UID 1000
  (matching typical host UID). Removes `ubuntu` user, eliminates
  `--group-add` workaround, and fixes `PermissionError` on reset cleanup.
- **Git credential helper**: Configured in Docker image so `git push` over
  HTTPS uses injected `GH_TOKEN` automatically. Agents no longer need to
  construct token URLs manually.
- **Claude Code first-run suppression**: Pre-seeded `~/.claude/settings.json`
  in framework image + `DISABLE_AUTOUPDATER` and
  `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` env vars in `OciSandbox`.
  Prevents onboarding prompts from consuming the orchestrator's kickoff.
- **reset_graph improvements**: `git worktree prune` after directory removal,
  local branch cleanup via `branch_list_local()` (catches branches missed by
  remote-only listing), `force_rm()` for Docker containers (handles exited
  containers that `stop` + `rm` missed).
- **E2e script decoupling**: `e2e_run.sh`, `e2e_reset.sh`, and `e2e_check.sh`
  now use `--manifest-path` to run from agentrelay's pixi env. Target repo no
  longer needs agentrelay as a dependency.
- Removed `--user` and `--group-add` parameters from `docker.build_run_command()`.

---

## 2026-03-29

### Agent boundary instructions, container fixes, and e2e isolation graphs (sprint 2026-03-26 PR F1)

- **Isolation boundary instructions**: `resolve_instructions()` gains a
  `sandbox_type` parameter. When `SandboxType.OCI`, a `## Isolation Boundary`
  section is injected describing what the agent can/cannot access, what exists
  beyond its boundary, and how to report when blocked.
- **`IS_AI_AGENT=true` env var**: Injected by `OciSandbox.wrap_command()` into
  all containerized agents. Foundation for runtime agent detection.
- **Git pre-push hook**: Baked into Docker base image at
  `/etc/agentrelay/hooks/pre-push`. Blocks pushes to `main`/`master` when
  `IS_AI_AGENT=true`. Global `core.hooksPath` configured for agent user.
- **Container execution fixes**: `bash -c` shell wrapper, `--group-add` for
  host GID file permissions, `.git` dir read-write mount, `TERM` env var for
  TUI rendering, `chmod` for cross-UID claude binary access, `safe.directory`
  wildcard in container git config.
- **E2E isolation test graphs**: `basic_oci.yaml`, `token_tiers.yaml`,
  `permission_boundary.yaml` in `graphs/isolation/`. `basic_oci.yaml`
  validated end-to-end.

---

### Docker images, network lifecycle, and CLI credentials (sprint 2026-03-26 PR E)

- **Three-layer Docker image**: `docker/base/Dockerfile` (ubuntu:24.04, git, gh,
  python3, agent SDK), `docker/toolchain/python/Dockerfile` (adds pixi),
  `docker/framework/claude-code/Dockerfile` (adds Claude Code via native installer).
  Build all layers with `pixi run docker-build`.
- **Docker network lifecycle**: `run_graph.py` creates a Docker network
  (`agentrelay-<graph>`) before orchestration and removes it in a finally block.
  Only activated when any task uses OCI sandbox.
- **`--credentials` CLI flag**: Path to credentials YAML file, wires
  `FileCredentialProvider` into the task runner builder.
- **Docker label-based container tracking**: Containers are labeled with
  `agentrelay.graph` and `agentrelay.task` for programmatic lookups.
  Container names include graph name: `agentrelay-<graph>-<task>`.
- **Reset Docker cleanup**: `reset_graph.py` stops/removes containers by label
  and removes the Docker network (best-effort, swallows errors).
- **OciSandbox validate-not-create**: `setup()` now validates network exists
  (raises RuntimeError if missing) instead of creating it.
- New `ops/docker.py` functions: `ps_by_label()`, `labels` parameter on
  `build_run_command()`.
- `build_standard_runner()` accepts optional `credential_provider` parameter.
- 1123 tests (16 new).

---

## 2026-03-26

### Per-module diagrams, diagram cleanup, and sprint plan (PR #137)

- **Per-module UML diagrams**: New `tools/generate_module_diagrams.py` extracts
  16 focused diagrams from `diagram-detailed.d2` — one per module, showing full
  types plus simplified external dependency stubs at reduced opacity. Also
  generates `diagram-modules.d2` inter-module overview.
- **Removed filtered variants**: Deleted `diagram-no-private`, `diagram-no-impl`,
  and `diagram-standard` views along with `tools/generate_diagrams.py` and
  `tools/d2_filters.py`. Per-module diagrams replace them as the primary
  reference for understanding individual modules.
- **Diagram links in docs**: Each API reference page links to its module diagram.
  `docs/DIAGRAM.md` includes a table of all 16 module diagrams.
- **Sprint plan**: Added `docs/sprints/2026-03-26-agent-isolation.md` — 6-PR
  sprint for tunable agent isolation (Docker containers, scoped PATs,
  `AgentSandbox` protocol, `FrameworkConfigAdapter`, credential provisioning).
- **Backlog cleanup**: Marked cross-workstream ordering as resolved (PR #134),
  auto-merge as resolved (PR #135), removed diagram rendering size limit item.

---

## 2026-03-24

### Wire ADR production into agent instructions (PR E)

- **Rename `AgentVerbosity` → `AdrVerbosity`**: clearer naming, consistent
  with `_AdrPolicy`.
- **ADR instruction injection**: `resolve_instructions()` gains an
  `adr_verbosity` parameter. When not `NONE`, a `## Architecture Decision
  Record` section is injected between "What to Do" and "Submitting Your Work"
  with verbosity-scaled guidance and output path `docs/adr/<task_id>.md`.
- **Three verbosity tiers**: STANDARD (Title, Status, Context, Decision,
  Consequences), DETAILED (+Alternatives Considered, Trade-offs, Implementation
  Notes), EDUCATIONAL (+annotations explaining each section's purpose).
- **`graphs/adr/` test category**: `adr_standard.yaml` graph with a single
  task at standard verbosity.

---

## 2026-03-22

### Restructure instructions.md as a work-order document

- **Work-order layout**: instructions.md now reads as a natural work order:
  Role → Tools → What to Do → Submitting Your Work → Task Details.
  Each role gets a descriptive sentence ("You are a SPEC_WRITER tasked
  with...") via `_ROLE_SENTENCES` dict.
- **Scope preludes**: each role template starts with an explicit scope
  statement (e.g., "Scope: write API stubs only") so agents know their
  boundaries before reading the steps.
- **Concerns during work**: concern recording guidance moved into "What to
  Do" (record as you work) instead of the submission section.
- **Task Details at the end**: task description appears last as a reference
  section. For generic tasks, the description IS the work and goes under
  "What to Do" directly.
- **Spec writer simplified**: removed markdown spec step — Python stubs
  with signatures and docstrings are the single source of truth.

### Ops concerns — separate channel for operational issues (PR B4)

- **Separate ops concerns channel**: Agents can now record operational concerns
  (build errors, missing deps, tooling friction) via `agentrelay-ops-concern`
  CLI, distinct from design concerns (`agentrelay-concern`). Stored in
  `ops_concerns.log` in the signal directory.
- **End-to-end pipeline**: `TaskHelper.record_ops_concern()` →
  `ops_concerns.log` → `SignalCompletionChecker` → `TaskArtifacts.ops_concerns`
  → `TaskSummary.ops_concerns` → integration PR body + console summary.
- **Separate rendering**: Ops concerns appear in their own `## Ops Concerns`
  section in both individual task PRs and integration PRs, and in a separate
  `Ops Concerns:` block in console output.
- **Workflow footer updated**: Step 2 now distinguishes design vs ops concerns
  with examples of each category.

---

## 2026-03-21

### Declared tools + TaskHelper CLI wrapper (PR B2)

- **Declared tools in graph YAML**: New `tools` field (list of tool names)
  at the graph level. The orchestrator validates each tool is available before
  launch and injects usage guidance into agent instructions. Starts with pixi;
  extensible via `TOOL_REGISTRY` in `tools.py`.
- **TaskHelper CLI wrapper**: Agents can now use shell commands instead of
  inline Python: `agentrelay-complete`, `agentrelay-failed`, `agentrelay-concern`.
  Eliminates shell-escaping issues with inline Python in zsh.
- **Workflow footer updated**: Shows CLI commands instead of Python snippets.
  Tools guidance section appears when tools are declared.

### Roles test graphs and multi-role pipeline (PR B)

- **Roles pipeline graph** (`graphs/roles/pipeline.yaml`): Four-role pipeline
  (spec_writer -> test_writer -> test_reviewer -> implementer) building a
  BoundedQueue class. Exercises role-specific templates, TaskPaths, and the
  full handoff chain for the first time with real agents.
- **Organic concern test**: The spec_writer description contains a deliberate
  contradiction (eviction vs OverflowError on full push) to test whether
  agents discover and report spec inconsistencies without explicit prompting.
- **Implementer template fix**: Updated `templates/implementer.md` to connect
  concern documentation to `helper.record_concern()` with guidance on what
  qualifies as a concern (contradictions, ambiguities, impossible requirements).
- **Backlog**: Added structured instruction architecture item (concern
  definitions as formal data, partially structured instructions.md,
  default-with-overrides pattern).

---

## 2026-03-20

### Signal-file-backed TaskStatus (PR A3)

- **TaskStatus is now derived from signal files on disk**, matching the
  WorkstreamStatus pattern from PR #115. Status files live under
  `.workflow/<graph>/signals/<task_id>/status/` with one file per status value
  (`pending`, `running`, `pr_created`, `pr_merged`, `failed`).
- **`TaskRuntime.status`** is a computed property reading from signal files.
  Falls back to `PENDING` (or `FAILED` if an error is recorded) when no
  signal directory has been set.
- **`TaskState.status` field removed** — status is no longer stored in memory.
- **New mark methods** on `TaskRuntime`: `mark_running()`, `mark_pr_created()`,
  `mark_pr_merged()`. Existing `mark_pending()` and `mark_failed(error)` updated
  to write signal files.
- **`StandardTaskRunner._transition()`** validates lifecycle edges then delegates
  to the appropriate mark method. FAILED transitions use `mark_failed(error)`
  directly at call sites.
- **`reset_for_retry()`** clears all status signal files before writing a fresh
  `pending` file.

---

## 2026-03-19

### Docs, demo graphs, and E2E testing (PR P)

- **Demo graphs**: Replaced outdated `graphs/demo.yaml` with two tested demos
  (`quick_parallel.yaml`, `quick_chained.yaml`) versioned alongside the code.
- **E2E scripts**: Three shell scripts in `tools/` for running graphs against
  external target repos:
  - `e2e_run.sh` — validates target repo, runs a graph.
  - `e2e_reset.sh` — resets a graph run in a target repo.
  - `e2e_check.sh` — preflight check (pixi, agentrelay dependency, Python, gh auth,
    agent environment, working tree cleanliness, leftover state).
- **Conflict detection**: `run_graph` now errors if `.workflow/<graph>` or
  `.worktrees/<graph>` already exists, preventing corrupted state from overlapping
  runs. `--dry-run` reports conflicts as warnings.
- **Pixi tasks**: `e2e`, `e2e-reset`, `e2e-check`.
- **Updated docs**: GUIDE.md rewritten with current-architecture-first CLI reference
  and E2E section. WORKFLOW.md expanded with practical run/reset cycle examples.

---

## 2026-03-18

### Composition and CLI entry point (PR N2)

- **`build_standard_workstream_runner()`**: New builder in `orchestrator/builders.py`
  that wires `GitWorkstreamPreparer`, `GhWorkstreamMerger`, and `GitWorkstreamTeardown`
  into a `StandardWorkstreamRunner`. Mirrors the `build_standard_runner()` pattern.
- **`run_graph.py`**: New top-level module providing:
  - `run_graph()` async composition function: loads YAML, builds graph + runners +
    orchestrator, and runs to completion.
  - `dry_run()`: validates graph YAML and prints execution plan (task order,
    dependencies, workstreams).
  - CLI via `python -m agentrelay.run_graph <graph.yaml>` with flags:
    `--max-concurrency`, `--max-task-attempts`, `--teardown-mode`, `--tmux-session`,
    `--model`, `--dry-run`.
- **Operational YAML keys**: `tmux_session`, `keep_panes`, `model` are popped from
  the raw YAML before graph parsing, allowing `TaskGraphBuilder` to stay unchanged.
  CLI flags override YAML values.
- **19 new tests**: unit tests for YAML preprocessing, builder, and dry-run; integration
  tests verifying full wiring from graph YAML through orchestrator with test doubles.

### Reset tool (PR O)

- **`reset_graph.py`**: New top-level module for resetting a repository to its
  pre-graph-run state. Reads `.workflow/<graph>/run_info.json` (written by `run_graph`),
  then: closes open PRs, resets main and force-pushes (with ancestry safety check),
  deletes remote/local branches, removes worktree and workflow directories.
  - `plan_reset()` / `execute_reset()`: separated planning from execution for testability.
  - CLI via `python -m agentrelay.reset_graph <graph.yaml>` with `--yes` flag.
  - Out-of-order reset detection: skips main-branch reset if `start_head` is not an
    ancestor of current HEAD, still performs all other cleanup.
  - Idempotent: re-running after a successful reset is safe.
- **`run_info.json`**: `run_graph` now writes `start_head` + `started_at` to
  `.workflow/<graph>/run_info.json` before orchestrator runs.
- **New ops primitives**: `git.rev_parse_head`, `git.merge_base_is_ancestor`,
  `git.reset_hard`, `git.push_force_with_lease`, `git.ls_remote_branches`,
  `gh.pr_list`, `gh.pr_close`.
- **10 new tests**: plan/execute against temp git repos with remotes, out-of-order
  detection, idempotency, PR closing (mocked), run_info.json integration.

---

## 2026-03-16

### Add graphical popups to overview diagram

- **Per-package mini SVGs**: `tools/generate_overview.py --mode package-svgs` extracts
  each top-level package's D2 block from `docs/diagram.d2`, renders it as a standalone
  SVG via `d2`, and embeds all 13 mini SVGs (base64-encoded) in the overview HTML.
- **Click-to-open popups**: Clicking a package box opens a centered panel showing
  that package's D2-rendered class diagram. Clicking an arrow shows both endpoint
  packages side-by-side with a text list of class-level connections. Click outside
  or press Escape to close.
- **Build pipeline**: `pixi run diagram` now runs the `package-svgs` mode after
  rendering the overview SVG, producing `docs/pkg-detail/*.d2` and `*.svg` files.
- **21 new tests** covering D2 block extraction, per-package file generation,
  SVG rendering (mocked subprocess), and popup HTML generation.

### Add two-tier diagram system with auto-generated overview

- **Overview generator**: New `tools/generate_overview.py` parses `docs/diagram.d2`,
  extracts top-level packages and cross-package relationships, deduplicates arrows to
  one per package pair, and writes `docs/diagram-overview.d2` with tooltips listing
  each package's classes.
- **Two rendered views**: `pixi run diagram` now generates both `diagram-overview.svg`
  (13 package boxes, ~19 directional arrows) and `diagram.svg` (full class detail).
- **Zero-drift**: Overview is derived from the detail diagram — single source of truth.
- **27 new tests** covering parsing, deduplication, edge cases, and end-to-end
  validation against the real diagram.

### Migrate design diagram from PlantUML to D2

- **Tool change**: Replaced PlantUML with D2 using the ELK layout engine for better
  handling of nested containers and cross-package relationship arrows at scale.
- **Faithful translation**: All ~80 classes/interfaces/enums across 12+ packages and
  ~170 relationships preserved in the new `docs/diagram.d2` source.
- **Dependency swap**: Replaced `plantuml` with `d2` in pixi.toml; `pixi run diagram`
  now invokes `d2 --layout elk`.
- Archived original PlantUML source as `docs/diagram.puml.archived` for reference.

### Extract _OrchestratorRun from Orchestrator

- **Separation of concerns**: Split `Orchestrator` into an immutable config
  holder and `_OrchestratorRun`, a module-private execution context that owns
  all mutable state for one `run()` invocation.
- **Readable main loop**: `execute()` is ~20 lines — initialize, dispatch,
  handle deadlock, await, process completions, build result.
- **Simplified helper signatures**: Helpers access `self._task_runtimes`,
  `self._orchestrator.graph`, etc. directly instead of threading 3-6 parameters.
- **Deduplicated fail-fast**: Extracted `_fail_fast_cancel()` to replace the
  3 repeated cancel-mark-clear patterns.
- Pure refactoring — no behavioral changes, all existing tests pass unchanged.

---

## 2026-03-15

### Wire WorkstreamRunner into Orchestrator

- **WorkstreamRunner as Protocol**: Promoted `WorkstreamRunner` to a Protocol
  (matching the `TaskRunner` pattern). Renamed the concrete implementation to
  `StandardWorkstreamRunner`. The Orchestrator depends only on the protocol.
- **Orchestrator lifecycle wiring**: Added `workstream_runner` as a required field
  on `Orchestrator`. The orchestrator now calls `prepare()` before the first task
  in a workstream, `merge()` when all tasks reach `PR_MERGED`, and `teardown()`
  after the main loop exits.
- **MERGE_READY status**: Added `WorkstreamStatus.MERGE_READY` as an intermediate
  state between `ACTIVE` and `MERGED`. Enables future human-approval gates before
  integration branch merge.
- **Derived active-task check**: Removed `active_task_id` from `WorkstreamState`
  and the `activate()`/`deactivate()` methods from `WorkstreamRuntime`. The
  one-task-per-workstream constraint is now enforced by scanning task runtimes
  for `RUNNING`/`PR_CREATED` status.
- **fail_fast_on_workstream_error**: New `OrchestratorConfig` option (default
  `True`). When a workstream fails during `prepare()`, prevents preparing new
  workstreams but does not cancel in-flight work.
- Updated diagram, exports, and all orchestrator tests.

---

## 2026-03-14

### Flatten WorkstreamRunnerIO into WorkstreamRunner

- Removed `WorkstreamRunnerIO` intermediate dataclass. `WorkstreamRunner` now
  holds the three per-step protocol fields (`_preparer`, `_merger`, `_teardown`)
  directly, matching the pattern established by `StandardTaskRunner` on the
  task side.
- Deleted `test/workstream/implementations/test_workstream_runner_io.py` (tested
  the removed composition class).
- Updated diagram, architecture docs, and exports.

### StandardTaskRunner with per-step dispatch

- **TaskRunner protocol**: Promoted `TaskRunnerLike` to `TaskRunner` (protocol in
  `task_runner/core/runner.py`). The orchestrator depends only on this protocol.
- **StandardTaskRunner**: Renamed the concrete `TaskRunner` class to
  `StandardTaskRunner`. Replaced `io: TaskRunnerIO` with six `StepDispatch[T]`
  fields that co-locate step sequencing and implementation dispatch.
- **StepDispatch[T]**: New generic frozen dataclass in `task_runner/core/dispatch.py`.
  Selects per-step protocol implementations based on `(AgentFramework, type[AgentEnvironment])`
  dispatch key. Supports `entries` dict + `default` fallback.
- **Workstream context via TaskState**: Added `integration_branch` and
  `workstream_worktree_path` fields to `TaskState` and `TaskStateView`. The
  orchestrator sets these from `WorkstreamRuntime.state` before dispatch, removing
  workstream-specific constructor args from `WorktreeTaskPreparer` and `GhTaskMerger`.
- **Builder**: New `build_standard_runner()` factory in
  `task_runner/implementations/standard_runner_builder.py` wires the standard
  worktree + tmux + Claude Code implementations via `StepDispatch` defaults.
- **TaskRunnerIO**: Retained but marked deprecated; no longer the primary
  composition mechanism.
- **Removed `TaskRunnerLike`** from `orchestrator/` — replaced by imported
  `TaskRunner` protocol from `task_runner`.

---

## 2026-03-13

### Add workstream-level protocol implementations

- Three concrete classes implementing the `WorkstreamRunnerIO` per-step
  protocols, composing `ops/` primitives:
  - `GitWorkstreamPreparer` — creates git worktree and integration branch,
    pushes to origin with upstream tracking
  - `GhWorkstreamMerger` — creates and merges workstream integration PR via
    GitHub CLI, updates local merge-target ref
  - `GitWorkstreamTeardown` — removes worktree, deletes local and remote
    integration branch (best-effort cleanup)
- Added `git.push_delete_branch()` thin wrapper to `ops/git.py`

### Fix task-level workspace model

- `WorktreeTaskPreparer` no longer creates a per-task worktree. Instead it
  creates a task branch in the shared workstream worktree via
  `git.branch_create()` + `git.checkout()`. New `workstream_worktree_path`
  config field points to the worktree owned by the workstream preparer.
- `WorktreeTaskTeardown` no longer removes the worktree (owned by workstream
  teardown). Still deletes the task branch and captures agent logs.
- Added `git.checkout()` thin wrapper to `ops/git.py`.

### Add task-level protocol implementations

- Six concrete classes implementing the `TaskRunnerIO` per-step protocols,
  composing `ops/` primitives and protocol builders from the `agent_comm_protocol/`
  package:
  - `WorktreeTaskPreparer` — creates git worktree, writes `manifest.json`,
    `policies.json`, and `instructions.md` to the signal directory
  - `TmuxTaskLauncher` — delegates to `TmuxAgent.from_config()` to launch
    Claude Code in a tmux pane
  - `TmuxTaskKickoff` — sends kickoff instructions to the launched agent
  - `SignalCompletionChecker` — async-polls for `.done`/`.failed` signal
    files and parses them into `TaskCompletionSignal`
  - `GhTaskMerger` — merges task PR via `gh`, updates local integration
    branch ref, writes `.merged` signal
  - `WorktreeTaskTeardown` — captures agent log, kills tmux window, removes
    worktree and branch (best-effort cleanup)
- Completed `TmuxAgent` stubs: `from_config()` creates tmux window and
  launches Claude Code; `send_kickoff()` waits for TUI ready then sends prompt
- Added `signal_dir: Optional[Path]` to `TaskState` and `TaskStateView`
- Implementation modules named after their protocol (`task_preparer.py`
  implements `TaskPreparer`, etc.) with docstrings cross-referencing the protocol
- 768 tests pass, 0 pyright errors

### Mirror src/agentrelay/ package structure in test/

- Restructured flat `test/` directory (29 files at root) into subdirectories
  matching `src/agentrelay/` package layout: `agent/`, `agent_comm_protocol/`,
  `errors/`, `ops/`, `orchestrator/`, `spec/`, `task_graph/`, `task_runner/`,
  `task_runtime/`, `workstream/`
- Renamed files where subdirectory makes prefix redundant (e.g.
  `test_ops_git.py` → `ops/test_git.py`, `test_protocol_manifest.py` →
  `agent_comm_protocol/test_manifest.py`)
- Top-level modules (`test_task.py`, `test_environments.py`, `test_workspace.py`)
  and cross-cutting `test_docs_examples.py` remain at `test/` root
- No source edits — all imports are absolute; `conftest.py` stays at root;
  pytest discovers subdirectories recursively
- 731 tests pass, 0 pyright errors

### Add protocol schemas, builders, and templates

- New `agent_comm_protocol/` package implementing Layers 1-3 of the agent
  communication protocol defined in `AGENT_COMM_PROTOCOL.md`
- `agent_comm_protocol/manifest.py` — `TaskManifest` frozen dataclass +
  `build_manifest()` builder + `manifest_to_dict()` serializer (Layer 1:
  structured task facts). Uses `AgentRole` enum and `pathlib.Path` for type safety.
- `agent_comm_protocol/policies.py` — `WorkflowPolicies` frozen dataclass +
  `build_policies()` builder + `policies_to_dict()` serializer (Layer 3:
  composable workflow config). Introduces `WorkflowAction` and `PrBodySection`
  enums for type-safe policy actions.
- `agent_comm_protocol/templates.py` — `resolve_instructions()` loads and
  parameterizes role templates using `string.Template` (Layer 2: work instructions)
- New `spec/` package with `SpecRepresentation` protocol and `PythonStubSpec`
  implementation (spec format abstraction)
- Four role templates in `src/agentrelay/templates/`: `spec_writer.md`,
  `test_writer.md`, `test_reviewer.md`, `implementer.md`
- `TaskPaths` fields changed from `str` to `pathlib.Path` for type-safe path handling
- Builder functions accept explicit parameters (not TaskGraph/TaskRuntime) to
  keep the protocol layer decoupled from graph and runtime layers

### Define agent communication protocol

- Added `docs/AGENT_COMM_PROTOCOL.md` — specification for orchestrator-agent
  communication, replacing the monolithic instruction builder approach from
  PR #90 (closed)
- Five-layer protocol: task manifest (structured facts), work instructions
  (natural language, template-driven), workflow policies (composable JSON),
  signaling contract (abstract), and framework adapter (environment-specific)
- Role templates for formulaic tasks (test_writer, implementer, etc.) avoid
  duplicating instructions across identical task types
- Abstract workflow step vocabulary (commit_and_push, create_pr,
  run_completion_gate, etc.) decouples instruction content from framework-
  specific commands

## 2026-03-12

### Add infrastructure primitives package (ops/)

- New `ops/` package with thin, stateless subprocess and filesystem wrappers
  for the four infrastructure domains: git, tmux, gh CLI, and signal files
- `ops/git.py` — 9 functions: worktree, branch, fetch/push, ls-remote
- `ops/tmux.py` — 5 functions: window management, keys, capture, TUI readiness poll
- `ops/gh.py` — 3 functions: PR create, merge, body fetch
- `ops/signals.py` — 5 functions: signal dir management, JSON/text I/O, async poll
- Private implementation detail — not part of public API; protocol implementations
  (PRs L/M) will compose these primitives
- Added shared `test/conftest.py` with git repo fixtures for real-subprocess tests
- 47 new tests (git tests use real temp repos, tmux/gh use subprocess mocks,
  signals use real filesystem)

### Restructure packages into core/ + implementations/ layout

- Split `agent/`, `task_runner/`, and `workstream/` into `core/` (ABCs,
  protocols, state machines) and `implementations/` (concrete environment-
  specific code) subpackages
- Promoted `orchestrator.py` module to `orchestrator/` package
- All external import paths unchanged — package-level `__init__.py` re-exports
  maintain backward compatibility
- Updated PlantUML diagram to reflect new package structure
- 624 tests pass, 0 pyright errors

### Add OrchestratorListener protocol for real-time event observability

- Added `OrchestratorListener` protocol with single `on_event(event)` method
- `Orchestrator` accepts an optional `listener` field (default `None`)
- All 6 event emission sites now notify the listener in addition to accumulating
  events in the result list
- No behavioral change when listener is omitted — existing tests pass unchanged

### Remove _transition_to_failed escape hatch

- Removed silent fallback in `TaskRunner._transition_to_failed` that bypassed the
  transition table when FAILED wasn't a legal target from the current status
- The method now delegates to `_transition()` unconditionally (after idempotency
  check), making `ALLOWED_TASK_TRANSITIONS` the single authoritative source of
  legal state edges

## 2026-03-11

### Remove speculative RemoteWorkspaceRef

- Removed `RemoteWorkspaceRef` (6 optional placeholder fields for a remote execution
  model that doesn't exist yet)
- Removed `kind` discriminator from `LocalWorkspaceRef` (unnecessary without a union
  to dispatch over; `isinstance` suffices)
- `WorkspaceRef` type alias now points to `LocalWorkspaceRef` alone, with docstring
  documenting how to extend it to a union when additional backends are needed

### Wire integration errors into TaskRunner and orchestrator

- Renamed `integration_errors/` → `errors/` (shorter; class names are self-descriptive)
- Removed `WorktreeIntegrationError` (unused alias) and custom `cause` field
  (use standard `raise ... from` and `__cause__` instead)
- Wired `classify_integration_error()` into `TaskRunner._record_io_failure()` —
  IO boundary failures are now classified as expected-task-failure vs internal-error
- Added `failure_class: Optional[IntegrationFailureClass]` to `TaskRunResult`
- Orchestrator now inspects `failure_class` to distinguish internal adapter errors
  (fail-fast, no retry) from expected task failures (retry eligible)

### Add mutation methods to TaskRuntime and WorkstreamRuntime

- Added `prepare_for_attempt`, `mark_failed`, `reset_for_retry`, `mark_pending`
  methods to `TaskRuntime` — encapsulate orchestrator-level state transitions
- Added `activate`, `deactivate`, `mark_failed`, `mark_merged` methods to
  `WorkstreamRuntime`
- Replaced all direct field assignments in `orchestrator.py` with method calls
  (~15 mutation sites), eliminating the dual-writer pattern identified in the
  architecture review (concern #4, part B)

### Add read-only view protocols for task and workstream runtimes

- Added `TaskStateView`, `TaskArtifactsView`, `TaskRuntimeView` protocols to
  `task_runtime/runtime.py` — read-only interfaces structurally satisfied by the
  mutable dataclasses
- Added `WorkstreamStateView`, `WorkstreamArtifactsView`, `WorkstreamRuntimeView`
  protocols to `workstream/runtime.py`
- `concerns` fields exposed as `Sequence[str]` on views (prevents `.append()`
  through the view while `list[str]` still satisfies it structurally)
- Pure additions — no behavioral changes; protocols will be used in a follow-up
  PR to enforce single-writer discipline in the orchestrator

### Remove Agent from TaskRuntime

- Removed live `Agent` field from `TaskRuntime` — agent is now a local variable
  in `TaskRunner.run()`, not stored on the data record
- Added `agent_address: AgentAddress | None` to `TaskArtifacts` as an immutable
  audit trail of where the agent ran
- Changed `TaskKickoff.kickoff()` to accept `agent` as an explicit parameter
  instead of reading it from `runtime.agent`

## 2026-03-10

### Simplify Task.dependencies to store IDs instead of Task objects

- Changed `Task.dependencies` from `tuple[Task, ...]` to `tuple[str, ...]`,
  eliminating the dual representation where the builder converted IDs to objects
  and `TaskGraph` extracted IDs back out
- Removed `validate_task_identity_consistency` (no longer needed — string IDs
  have no object-graph identity to validate)
- Simplified `TaskGraphBuilder` construction loop (no longer requires topological
  order to thread object references)

### Decompose TaskRunnerIO and remove integration_contracts

- Promoted `task_runner.py` to `task_runner/` package with per-step Protocol
  interfaces (`TaskPreparer`, `TaskLauncher`, `TaskKickoff`,
  `TaskCompletionChecker`, `TaskMerger`, `TaskTeardown`) composed into a
  `TaskRunnerIO` frozen dataclass
- Added `WorkstreamRunner` and `WorkstreamRunnerIO` to `workstream/` package
  with per-step Protocols (`WorkstreamPreparer`, `WorkstreamMerger`,
  `WorkstreamTeardown`) for the workstream lifecycle
- Created `workspace.py` module for `LocalWorkspaceRef`, `RemoteWorkspaceRef`,
  and `WorkspaceRef` type alias
- Added `concerns: tuple[str, ...]` field to `TaskCompletionSignal`
- Deleted `integration_contracts/` package — its protocols and data types were
  absorbed into `task_runner/io.py`, `workstream/io.py`, and `workspace.py`
- Updated PlantUML diagram to reflect new package structure

---

### PlantUML diagram infrastructure and conventions cleanup

- Replaced Mermaid class diagram with PlantUML source (`docs/diagram.puml`) +
  rendered SVG (`docs/diagram.svg`), giving full layout control
- Added `plantuml` conda dependency and `pixi run diagram` task
- Added CI freshness check in `docs.yml` to keep SVG in sync with `.puml`
- Renamed `task_graph/indexing.py` → `_indexing.py` and `validation.py` →
  `_validation.py` (underscore prefix for internal-only modules)
- Updated `CLAUDE.md` coding conventions: public API uses classes; private
  submodules may use free functions with `<<module>>` diagram stereotype
- Audited diagram connectors: removed redundant `TaskGraphBuilder → Task`
  and `error_functions → IntegrationError`; added missing
  `TaskRunnerIO ..> TaskRuntime`
- Simplified `DIAGRAM.md` to link-only SVG view with streamlined PR policy
- Fixed mkdocs API docs and nav for renamed modules; added `md_in_html` and
  `attr_list` markdown extensions

---

## 2026-03-08

### Fix Pylance/pyright config for test files — PR #63

Updated `[tool.pyright]` in `pyproject.toml`:

- Removed `test/**` from `exclude` so VS Code/Pylance resolves imports
  in test files (previously excluded files are not analysed interactively)
- Added `extraPaths = ["src"]` for reliable package discovery under the
  `src/` layout regardless of editable-install detection

Also updated `.gitignore`.

---

## 2026-03-07

### Rename archive → prototypes/v01 — PR #58

Renamed `src/agentrelay/archive/` → `src/agentrelay/prototypes/v01/`,
`test/archive/` → `test/prototypes/v01/`, and `docs/archive/v1/` →
`docs/prototypes/v01/`. Updated all Python import paths and documentation
references accordingly. "Prototypes" more accurately describes the role of
this code than "archive".

---

## 2026-03-06

### Architecture Pivot — PR #51

**Promote current architecture to main package, archive prototype, set up mkdocs**

The original prototype proved the concept but lacked clean separation between task specifications (immutable) and runtime state (mutable). A complete architectural redesign was created in parallel with cleaner data models, better testability, and design for future extensibility.

This PR completes the transition by:
- Promoting core modules (`Task`, `TaskRuntime`, `Agent`, `AgentEnvironment`) to root level in `src/agentrelay/`
- Archiving all prototype modules in `src/agentrelay/prototypes/v01/` for reference
- Setting up mkdocs with mkdocstrings for auto-generated API documentation
- Creating comprehensive new documentation structure

**Result:** Current architecture is now the primary implementation. All new development targets it.

**Key files:** All core modules at `src/agentrelay/`. Prototype reference in `src/agentrelay/prototypes/v01/`.

For historical record of prototype development, see `docs/prototypes/v01/HISTORY.md`.

---

### Foundation — PRs #48–#50

**Build current architecture**

Three PRs established the clean data model:

- **PR #48** — Core types: `Task` (frozen spec), `TaskRuntime` (mutable envelope), `TaskState`, `TaskArtifacts`, addressing types
- **PR #49** — `Agent` class and `TmuxAgent` concrete implementation
- **PR #50** — Refine `Agent` as ABC, introduce `AgentEnvironment` type alias and `TmuxEnvironment`

Result: 467 comprehensive tests, clean separation of concerns, foundation ready for workflow implementation.

---

## Historical Note

For a detailed history of prototype development (PRs #36–#46), see `docs/prototypes/v01/HISTORY.md`. The prototype served as a proof-of-concept and informed the design of the current architecture.
