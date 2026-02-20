# Workflow Orchestration for Multi-Agent Claude Code Pipelines
## Project Plan

> **Note:** This document is the seed for a separate exploratory project.
> It currently lives in `chatcat/docs/` for convenience and should be moved
> to the new project repo when that repo is created.
>
> Background context: `docs/AGENT_WORKFLOWS_KNOWLEDGE_CAPTURE.md`

---

## 1. Project Overview

### Motivation

While planning multi-agent workflows for chatcat, a recurring pattern emerged:
coordinating multiple Claude Code agents involves the same structural elements
regardless of what the agents are actually doing — a unit of work, a handoff,
a review, a decision to proceed or retry. These mechanics are worth studying on
their own terms, separated from any particular task domain.

### Goal

Design and prototype a **lightweight, declarative workflow framework** for
describing and executing multi-agent Claude Code task pipelines. The framework
should be:

- **Human-readable** — a developer can glance at a workflow spec and understand
  what agents do what and in what order
- **Agent-parseable** — a Claude Code agent can read the spec and know what step
  it is on, what comes next, and what a successful outcome looks like
- **Parameterized** — the same vocabulary describes any workflow regardless of
  what the steps actually do
- **Incrementally automatable** — start with manual execution, progressively
  automate signals, gates, and retries

### Scope

This is deliberately a **toy / exploratory project**. Success is understanding
and a working prototype, not production software. The tasks chosen for
experiments should be trivial and interchangeable — the point is the workflow
mechanics, not the work itself.

---

## 2. Core Vocabulary

### Task

The top-level unit of work. A Task has a name, a linear or branching sequence
of Steps, and a terminal state (complete or aborted). Maps to a feature, a
phase, or any bounded goal.

### Step

A discrete work chunk executed by a **single agent**. A Step has:

| Property | Description |
|----------|-------------|
| `id` | Unique identifier within the Task (e.g., `X-1`, `X-2`) |
| `name` | Human-readable label |
| `agent` | Who executes it (type, launch method, worktree, context) |
| `inputs` | Files, docs, or artifacts the agent reads |
| `outputs` | Files or artifacts the agent produces |
| `success_criterion` | How to know the step is done (tests pass, file exists, etc.) |

A Step does not decide what happens next — that is the Gate's job.

### Gate

A verification procedure that sits between two Steps. A Gate has:

| Property | Description |
|----------|-------------|
| `id` | Unique identifier (e.g., `XG-1-2` — between steps X-1 and X-2) |
| `reviewer` | Who evaluates the gate (see Escalation Levels below) |
| `on_pass` | Which Step to proceed to |
| `on_fail` | Which Step to return to (with retry context) |
| `max_retries` | Maximum failures before forced human escalation |

### Signal

The mechanism by which a Step announces completion and triggers its downstream
Gate. Options:

| Signal type | Mechanism | Notes |
|-------------|-----------|-------|
| `sentinel_file` | Agent writes a JSON file to `.workflow/signals/` | Machine-readable; easy to watch with inotifywait |
| `git_commit` | Agent commits with a structured message (e.g., `[GATE:XG-1-2]`) | Auditable; works without extra infrastructure |
| `pr_creation` | Agent creates a GitHub PR | Pulls in GitHub notification infrastructure |
| `stdout_exit` | Headless agent exits 0 or non-zero | Simplest; useful for scripted pipelines |

### Reviewer

The entity that evaluates a Gate. Determined by **escalation level**:

| Level | Symbol | Who reviews | Auto-proceed? | Human notified? | Human required? |
|-------|--------|------------|---------------|-----------------|-----------------|
| Automated | `auto` | Agent | Yes | No (records kept) | No |
| Notify | `notify` | Agent | Yes | Yes (can veto) | No |
| Human | `human` | Human | No | Yes | Yes |

Escalation level is set **per Gate**, not globally. A workflow can have some
gates that auto-approve and others that require human sign-off.

### Retry Context

When a Gate fails, the reviewer writes structured feedback to a known location
before routing back to the Step. The re-run Step reads this as part of its
context — it does not need to "know" it is retrying, it just has richer input.

```
.workflow/
  retry-context/
    XG-1-2-attempt-1.md    ← feedback from failed gate, consumed by Step X-1 re-run
    XG-1-2-attempt-2.md    ← feedback from second failure (if any)
```

Multiple retry rounds accumulate context files. The agent sees the full
failure history without needing any special retry logic.

**Escalation on max retries:** If a Gate has failed `max_retries` times, the
workflow automatically escalates to level `human` regardless of the configured
level. A human must intervene before the workflow can proceed.

---

## 3. Workflow Spec Format

A workflow is described in a YAML file. The format is designed to be writable
by a human or a planning agent, and readable by a reviewing or executing agent.

### Schema

```yaml
workflow:
  id: <unique-id>
  name: <human-readable name>
  description: <brief description>
  context_files:           # files all agents in this workflow should read
    - CLAUDE.md
    - docs/plans/<plan>.md

steps:
  - id: <step-id>
    name: <label>
    agent:
      type: <role>         # e.g. test-writer, implementor, reviewer, planner
      launch: <method>     # interactive | headless | subagent
      worktree: <path>     # relative to repo root
      context:             # additional files this agent reads
        - <path>
    inputs:
      - <file or artifact>
    outputs:
      - <file or artifact>
    success_criterion: <command or description>
    signal:
      type: <sentinel_file | git_commit | pr_creation | stdout_exit>
      value: <filename, commit prefix, etc.>
    gate: <gate-id>        # gate triggered after this step

gates:
  - id: <gate-id>
    name: <label>
    reviewer:
      level: <auto | notify | human>
      agent_type: <role>   # if level is auto or notify
    on_pass:
      next_step: <step-id>
    on_fail:
      next_step: <step-id>
      retry_context_path: .workflow/retry-context/<gate-id>-attempt-{n}.md
    max_retries: <integer>
```

### Annotated Example

The following spec describes a test-write → review → implement → review
pipeline for a hypothetical search index module. The task content is
illustrative; the mechanics are the focus.

```yaml
workflow:
  id: phase-4-search-index
  name: "Implement search index module"
  description: >
    Write tests for the search index interface, review them, implement the
    module, then verify the implementation passes all tests.
  context_files:
    - phase-4/CLAUDE.md
    - docs/plans/phase-4-plan.md

steps:
  - id: X-1
    name: write-tests
    agent:
      type: test-writer
      launch: headless
      worktree: phase-4/
    inputs:
      - docs/plans/phase-4-plan.md
      - phase-4/CLAUDE.md
      - .workflow/retry-context/XG-1-2-*.md   # empty on first run
    outputs:
      - test/test_index.py
    success_criterion: "file test/test_index.py exists and is non-empty"
    signal:
      type: sentinel_file
      value: .workflow/signals/X-1-done.json
    gate: XG-1-2

  - id: X-2
    name: implement
    agent:
      type: implementor
      launch: headless
      worktree: phase-4/            # same branch, handoff from X-1
    inputs:
      - test/test_index.py
      - phase-4/CLAUDE.md
      - .workflow/retry-context/XG-2-end-*.md  # empty on first run
    outputs:
      - src/chatcat/index.py
      - src/chatcat/search.py
    success_criterion: "pixi run test exits 0"
    signal:
      type: sentinel_file
      value: .workflow/signals/X-2-done.json
    gate: XG-2-end

gates:
  - id: XG-1-2
    name: review-tests
    reviewer:
      level: notify           # agent auto-approves; human is notified and can veto
      agent_type: reviewer
    on_pass:
      next_step: X-2
    on_fail:
      next_step: X-1
      retry_context_path: .workflow/retry-context/XG-1-2-attempt-{n}.md
    max_retries: 2

  - id: XG-2-end
    name: review-implementation
    reviewer:
      level: human            # human must sign off before merge
    on_pass:
      next_step: DONE         # merge PR, close worktree
    on_fail:
      next_step: X-2
      retry_context_path: .workflow/retry-context/XG-2-end-attempt-{n}.md
    max_retries: 3
```

---

## 4. Workflow Directory Layout

```
<repo-root>/
├── .workflow/
│   ├── specs/
│   │   └── <workflow-id>.yaml      # one file per workflow
│   ├── signals/
│   │   └── <step-id>-done.json     # written by steps, read by gates
│   ├── retry-context/
│   │   └── <gate-id>-attempt-N.md  # written by gates on failure
│   └── audit/
│       └── <workflow-id>.log       # append-only record of all gate outcomes
└── CLAUDE.md                       # root-level project context
```

The `.workflow/` directory is the shared state space for the pipeline. Any
agent or human can inspect it to understand the current state of any workflow.

---

## 5. Key Design Questions

These are the open questions the project should answer through experimentation:

1. **Minimal parseable format:** What is the simplest spec format that both a
   human developer and a Claude Code agent can read without ambiguity? Is YAML
   the right choice, or is structured Markdown easier for agents?

2. **Interpreter model:** Should the spec be interpreted by:
   - A shell script that drives `claude -p` calls
   - An orchestrating Claude agent that reads the spec and manages execution
   - Both (script for signals/triggers, agent for gate evaluation)

3. **Retry depth:** How many gate failures before forced human escalation,
   regardless of configured escalation level? Is `max_retries` enough, or do
   we need a global circuit breaker?

4. **Cross-task dependencies:** How are dependencies between Tasks expressed?
   (e.g., Task Y Step Y-1 cannot start until Task X Step X-2 output is stable.)
   Is a DAG overlay on top of the linear-chain spec sufficient?

5. **Audit log format:** What does a useful audit record look like? Enough
   detail for a human to understand what happened and why, without being so
   verbose that it becomes noise.

6. **CLAUDE.md integration:** Can a per-worktree CLAUDE.md carry the workflow
   spec inline, or does it need to remain a separate file? Trade-off: inline is
   fewer files; separate is easier to parse programmatically.

7. **Gate failure routing:** Is "go back to the previous step" always right, or
   do some failures need to route further back (e.g., bad plan doc needs fixing
   before tests can meaningfully be re-written)?

---

## 6. Suggested Experiments

Ordered by increasing complexity. Each experiment builds on the previous one.
The actual task content for each experiment should be trivial (e.g., "write
a function that adds two numbers") so attention stays on the mechanics.

### Experiment 1: Hand-authored spec, manual execution
- Write a workflow spec for a 2-step task (X-1 → Gate → X-2)
- Execute each step manually: launch agents by hand, evaluate the gate yourself
- Goal: validate that the vocabulary is expressive enough to describe what happens

### Experiment 2: Headless agent execution from spec
- Write a shell script that reads a workflow spec and launches `claude -p` for
  each step in sequence
- No signals yet — steps run in order, gates are skipped (always pass)
- Goal: confirm `claude -p` + CLAUDE.md is a workable execution model

### Experiment 3: Sentinel + inotifywait signals
- Add signal writing to step agents (write sentinel file on completion)
- Add inotifywait watcher script that detects signals and triggers next step
- Goal: steps now trigger gates without manual intervention

### Experiment 4: Gate evaluation and retry context
- Implement gate as a `claude -p` invocation that reads step outputs and
  writes either a pass signal or a retry context file
- On failure: re-run the previous step with retry context in its inputs
- Goal: the fail → feedback → retry loop works end-to-end

### Experiment 5: Escalation levels
- Add escalation level enforcement to the gate runner
- `auto`: gate agent decides and pipeline continues
- `notify`: gate agent decides, desktop notification sent, pipeline pauses briefly
- `human`: pipeline blocks until a human writes a pass/fail file to `.workflow/signals/`
- Goal: human checkpoints work without blocking the rest of the pipeline

### Experiment 6: Cross-step dependency
- Define two Tasks where Task Y Step Y-1 depends on Task X Step X-2 output
- Implement a dependency check: Y-1 does not launch until X-2's output exists
- Goal: understand what DAG support actually requires

### Experiment 7 (stretch): Orchestrating agent reads and drives the spec
- Replace the shell script interpreter with a Claude Code agent that reads the
  workflow spec and manages execution by launching subagents via the Task tool
- Compare: shell-script-driven vs. agent-driven orchestration in terms of
  flexibility, token cost, and failure handling
- Goal: understand when an agent orchestrator adds value over a dumb script

---

## 7. References

- `docs/AGENT_WORKFLOWS_KNOWLEDGE_CAPTURE.md` — background discussion notes
  covering the direct/indirect orchestrator distinction, token cost comparisons,
  CLAUDE.md as frozen coordination, and the two-instance TDD pattern
- Claude Code docs: `claude -p` / `--print` headless mode
- Claude Code docs: Task tool subagents (for Experiment 7)
- GitHub Actions @claude integration (optional signal mechanism for Experiment 3+)
