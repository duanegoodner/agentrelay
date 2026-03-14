# Changelog

Chronological log of significant changes to the main codebase. For full details see each PR on GitHub.

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
