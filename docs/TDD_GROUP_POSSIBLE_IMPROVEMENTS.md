# TDD Group Execution: Bottlenecks and Possible Improvements

Assessment of current execution overhead for `tdd_groups:` tasks and a catalogue of
potential improvements. None of these are implemented yet; this file documents the
discussion so ideas are not lost.

---

## Current execution model

Each `tdd_groups:` entry expands to three sequentially-dependent tasks:

```
{id}_tests  (TEST_WRITER)   → {id}_review  (TEST_REVIEWER)   → {id}_impl  (IMPLEMENTER)
```

Each step pays the full per-task cost:

| Overhead | Notes |
|----------|-------|
| Git worktree create | New branch off graph integration branch |
| Claude TUI startup | `bypass_delay` (4 s) + polling for "bypass permissions" text (up to 30 s) |
| Agent executes task | Varies by task complexity |
| `gh pr create` + orchestrator merge + `pull_graph_branch` | ~5–15 s |
| Signal file poll latency | 2 s polling interval |

For a single TDD group with no external dependencies this overhead is paid **three times**
sequentially. For `tdd_chained` (two chained groups) that's six sequential steps before
the final integration PR can be created.

The task description is also repeated verbatim in all three prompts, and the
TEST_REVIEWER and IMPLEMENTER prompts share an almost-identical preamble.

---

## Idea 1 — Single Claude instance with subagents

**Description:** Run all three TDD steps inside one Claude Code instance. The outer agent
spawns subagents for each role instead of the orchestrator launching three separate panes.

**Pros:**
- Eliminates two Claude TUI startups per TDD group.
- The outer agent can pass rich, structured context to subagents directly (no need to
  repeat the task description three times or rely on worktree files for hand-off).
- Shared conversation context within the group.

**Cons / open questions:**
- Signal file protocol needs adaptation: subagents don't have their own worktrees or
  `task_context.json`; a different completion-detection mechanism is needed.
- PR-per-step flow may not make sense in this mode (intermediate PRs would be skipped,
  changing the audit trail).
- Cannot easily use a different model per step — unless Claude Code's `Task` tool
  accepts a model parameter.
- Single pane makes per-step debugging harder compared to three separate panes.

**Design note:** Should be opt-in via a YAML flag (e.g. `execution_mode: subagent` vs
`execution_mode: separate`, where `separate` is the current default and preserves
per-role model selection).

---

## Idea 2 — Structured output manifest per task

**Description:** After each task completes, write a `manifest.json` to its signal
directory listing key output artifacts (e.g. test file paths, stub paths, review verdict).
Successor tasks read the manifest so they know exactly what was produced rather than
discovering it by inspecting the worktree.

**Example manifest written by TEST_WRITER:**
```json
{
  "test_files": ["tests/test_square.py"],
  "stub_files": ["src/agentrelaydemos/square.py"]
}
```

**Example manifest written by TEST_REVIEWER:**
```json
{
  "verdict": "APPROVED",
  "review_file": "square_fn_review.md"
}
```

**Pros:**
- Orchestrator can pass concrete file paths to successor prompts, reducing discovery work.
- Machine-readable verdict enables automated gating (see Idea 5).
- Low implementation risk; purely additive.

**Cons:**
- Requires the agent to write structured JSON in addition to its normal artifacts.
  Agents occasionally produce malformed output, so this needs a fallback.

---

## Idea 3 — Shared task-brief file (reduce prompt duplication)

**Description:** Write a `task_brief.md` file (to the signal directory, alongside
`context.md`) containing the task description and any shared preamble once. Each
role's prompt becomes short: "Read your task brief at `<path>`. Your role: IMPLEMENTER.
Steps: …"

**Pros:**
- Eliminates repetition of the task description across all three prompts.
- Single source of truth; easier to maintain prompt logic.
- Naturally supports the subagent mode (Idea 1): the outer agent writes the brief
  once and all roles read it.

**Cons:**
- Prompts are currently self-contained, which makes them easy to debug in isolation.
  Adding a file dependency makes each agent slightly harder to reason about on its own.
- Marginal token saving; unlikely to be the primary bottleneck.

**Alternative (no file change):** Factor the shared preamble out into a Python helper
inside `_build_task_prompt()` — a purely internal cleanup with no user-visible effect.

---

## Idea 4 — Optional review skip (`skip_review: true`)

**Description:** Add a `skip_review: true` flag to a `tdd_groups:` YAML entry. When
set, the group expands to only two tasks (`{id}_tests` → `{id}_impl`) with the
IMPLEMENTER depending directly on the TEST_WRITER.

**Pros:**
- Easy to implement in `AgentTaskGraphBuilder.from_yaml()`.
- Saves one full Claude startup + one PR/merge cycle for simpler features where test
  review adds little value (e.g. trivial utility functions).

**Cons:**
- Loses the review gate; any test quality issues propagate directly to the implementer.

---

## Idea 5 — Machine-readable review verdict and automated gating

**Description:** Define a required structured section in the review file:

```markdown
## Verdict
APPROVED
```

The orchestrator parses this before dispatching the IMPLEMENTER. If the verdict is
`CONCERNS` (or missing/malformed), the orchestrator can fail fast or optionally loop
the TEST_WRITER for revision before retrying.

**Pros:**
- Prevents an expensive IMPLEMENTER run when tests are fundamentally broken.
- Enables a retry loop: TEST_WRITER → TEST_REVIEWER → (CONCERNS? re-write) → TEST_REVIEWER …
- The verdict is already present in review files by convention; this formalises it.

**Cons:**
- Adds orchestrator-side parsing logic.
- Retry loops increase overall graph complexity and make run-time harder to bound.
- Requires robust fallback when the agent produces a non-conforming review file.

---

## Idea 6 — Single worktree + one PR for the whole TDD group

**Description:** Instead of three separate worktrees and three PRs, use a single
long-lived worktree for the entire TDD group. Each role commits to the same branch:

1. TEST_WRITER runs, commits tests + stub, signals readiness.
2. TEST_REVIEWER runs in the same worktree, commits the review file, signals readiness.
3. IMPLEMENTER runs in the same worktree, commits the implementation, creates one PR.

**Pros:**
- Eliminates two worktree creates/deletes.
- Eliminates two intermediate PRs + merges + branch pulls.
- All three commits appear in a single, coherent branch history.

**Cons:**
- Loses step isolation; harder to git-bisect between roles.
- Orchestrator needs a different inter-step signalling mechanism (no PR to merge
  between steps). One option: the orchestrator writes a `.proceed` file to the signal
  directory and each role polls for it before starting — which is structurally similar
  to the subagent model (Idea 1).
- Errors mid-group are harder to recover from cleanly.

---

## Prioritisation (rough)

| Idea | Effort | Risk | Impact |
|------|--------|------|--------|
| 4 — `skip_review` flag | Low | Low | Medium (saves one step for simple tasks) |
| 2 — Structured output manifest | Low | Low | Medium (cleaner context hand-off) |
| 3 — Shared task brief | Low | Low | Low–Medium (token/maintenance saving) |
| 5 — Machine-readable verdict + gating | Medium | Medium | Medium |
| 6 — Single worktree + one PR | High | Medium | High |
| 1 — Subagent mode | High | High | High |

Ideas 4, 2, and 3 are independently useful and low-risk; any of them can be
implemented without committing to the larger architectural changes in Ideas 1 and 6.
