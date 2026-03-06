# agentrelay — Design Decisions

Decisions made during early design discussions, with rationale. Ordered roughly from highest-level to most specific.

---

## No orchestration frameworks

**Decision:** Build directly on the Anthropic API, `subprocess`, and `asyncio`. Do not use LangChain, LangGraph, CrewAI, or similar.

**Rationale:** Frameworks add abstraction that obscures what's actually happening and makes debugging harder. The operations here (subprocess calls, file I/O, async polling) are straightforward enough that the framework overhead isn't justified. Staying close to the metal keeps the system debuggable and easy to reason about.

---

## Tmux for agent visibility

**Decision:** Launch worktree agents as interactive `claude` sessions in tmux panes, not as headless `claude -p` calls.

**Rationale:** Visibility matters during early development and for human-in-the-loop operation. A human orchestrator (or a curious developer) can watch any agent pane in real time, intervene if needed, and understand what's happening. Headless invocations are harder to observe and debug.

---

## Git worktrees for task isolation

**Decision:** Each task gets its own git worktree on its own branch. No shared working directory between concurrent tasks.

**Rationale:** Worktrees prevent filesystem race conditions between parallel agents and allow each agent to maintain its own state without interference. They also make it natural to create a PR per task: the agent works on a branch, creates the PR, and the orchestrator merges it.

---

## Sentinel files for all inter-agent signaling

**Decision:** All communication between agents and the orchestrator — and between orchestrator phases — happens through files written to `.workflow/<graph-name>/signals/<task-id>/`.

**Rationale:** File-based signaling is simple, debuggable, and works across process boundaries. Signal files can be inspected directly, don't require a running service, and persist across crashes. They also serve as a natural audit log. The alternative (message queues, HTTP APIs) would add infrastructure complexity without meaningful benefit at this scale.

---

## Signal file ownership: one writer per signal

**Decision:** Each signal file is written by exactly one role — either an agent (worktree) or the orchestrator — never both. Agents write work-product signals (`.tests-written`, `.done`, `.failed`); the orchestrator writes decision signals (`.tests-approved`, `.merged`, `.needs-human`).

**Rationale:** Unambiguous ownership makes the audit trail readable and prevents races. A signal file is either reporting an outcome or recording a decision — keeping these separate makes the log self-explanatory.

---

## Signal directories scoped to graph name, not run ID

**Decision:** Signal paths are `.workflow/<graph-name>/signals/<task-id>/`, shared across all runs of the same named graph.

**Rationale:** Scoping to graph name (not a per-run UUID) enables natural resume: a restarted orchestrator reads the existing signals and picks up where it left off. A "fresh run" is an explicit act (`rm -rf .workflow/<graph-name>/`). The alternative (per-run scoping) would require explicit run tracking and make resume harder.

---

## `.merged` is the authoritative completion signal

**Decision:** A task is considered truly `DONE` only when the orchestrator has written `.merged` — not when the agent writes `.done`.

**Rationale:** `.done` means the agent finished its work and created a PR. But the work isn't in `main` yet. The orchestrator writes `.merged` only after a successful merge, making it the durable, trustworthy signal that downstream tasks can depend on. On resume, the orchestrator hydrates task status from `.merged`, not `.done`.

---

## Stable task IDs + cleanup-based branch management

**Decision:** Task IDs (e.g., `task_001`) are stable within a graph definition and reused across runs. Git branches (`task/<graph-name>/<task-id>`) are deleted after merge. The orchestrator treats "branch already exists" as an explicit error, not a silent override.

**Rationale:** Stable IDs keep branch names readable and predictable. Deleting branches after merge avoids conflicts on re-run. Using `-B` (force-recreate) would silently destroy prior work on crash; explicit error detection is safer. A per-run ID in branch names would avoid conflicts but make history harder to read and defeat resume.

---

## Three agents per TDD feature (test-writer → reviewer → implementer)

**Decision:** A TDD feature is expressed as three sequential `AgentTask` nodes with
explicit roles: `TEST_WRITER`, `TEST_REVIEWER`, `IMPLEMENTER`. Each creates its own PR,
merged before the next agent is dispatched.

**Rationale:** Three short-lived single-purpose agents are easier to reason about than one
long-lived agent that switches modes mid-run. Separating test-writing, review, and
implementation into distinct PRs creates a clean audit trail in git history. The reviewer
agent (not the orchestrator) performs test quality assessment, keeping the orchestrator loop
simple and uniform — it treats all tasks identically regardless of role. The worktree for
each task is independent, which is consistent with the project's one-worktree-per-task
model.

The three tasks are declared explicitly in the YAML `tasks:` list with explicit `role:`
and `dependencies:` fields. There is no auto-expansion shorthand.

---

## TDD workflow: tests define task completion

**Decision:** The test-writer agent writes tests *and* a stub module (signatures only,
bodies `raise NotImplementedError`) before any real implementation. The reviewer agent reads
the tests and stub, writes a review file (`{task_id}.md`), and signals done or
failed. The implementer agent reads the review file, implements the code in the stub module,
and runs `pytest` until all tests pass. Tests and implementation are merged to `main` as
separate PRs.

**Rationale:** Tests serve as a precise, machine-verifiable definition of "done." Writing
them first forces a clear contract before implementation begins. The stub module ensures the
test-writer PR compiles and tests can be collected (`--collect-only`) without any real
implementation existing yet. The review step catches fundamentally broken tests before any
implementation effort is spent on them.

---

## Pre-dispatch verification using tests

**Decision:** Before creating a worktree or launching any agent, the orchestrator checks whether the task's tests already exist in `main` and whether they pass. If tests pass, the task is marked complete without dispatching any agent.

**Rationale:** This makes the system robust to signal directory resets (e.g., `rm -rf .workflow/`). If a task's work is already in `main`, the tests prove it — no signals required. The test suite is a durable, git-tracked record of completion that outlives any runtime state.

---

## `AgentTaskGraph` owns all path computation

**Decision:** All paths — worktree directories, branch names, signal directories — are computed as methods on `AgentTaskGraph` from `graph.name` and `task.id`. `TaskState` may cache computed paths but is not the source of truth.

**Rationale:** Centralising path logic in one place prevents inconsistencies. If the naming scheme changes, there's one place to update it. Individual tasks don't need to know the global naming convention — they just receive paths from the graph.

---

## `WorktreeTaskRunner` as thin scaffolding

**Decision:** `WorktreeTaskRunner` provides only infrastructure to worktree agents: signal writing, path resolution, and context reading. It contains no business logic or LLM calls.

**Rationale:** The runner's job is to give agents a consistent, correct API for interacting with the coordination layer, so agents don't need to hard-code paths or reinvent signal-writing logic. Keeping it thin means the runner is easy to understand, test, and trust. The agent provides reasoning; the runner provides plumbing.

---

## `task_context.json` for runner initialization

**Decision:** The orchestrator writes a `task_context.json` into the worktree root before launching any agent. `WorktreeTaskRunner.from_config()` reads this file to initialize itself.

**Rationale:** File-based initialization is consistent with the project's overall communication model (everything through files). It also means the runner doesn't need environment variables, command-line arguments, or any other channel — the worktree directory is fully self-describing when the agent starts.

---

## Orchestrator-mediated signaling (no peer-to-peer between agents)

**Decision:** Worktree agents only write to their own task's signal directory. They do not read other tasks' signal directories. All cross-task coordination goes through the orchestrator.

**Rationale:** Direct agent-to-agent signaling would create tight coupling between tasks and make the orchestrator less central. The latency benefit of peer signaling isn't worth the architectural complexity at this stage.
