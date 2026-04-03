# Output-Driven Task Composition — Design Reference

> **Status: Design discussion.** Not yet scheduled. Depends on e2e observation
> from sprint 2026-04-03 (agent graph awareness) to validate that agents use
> graph YAML and upstream artifacts effectively. This design extends that
> foundation with structured output declarations and runtime input discovery.

## Problem

Today, the graph YAML is **input-driven**: the graph author specifies exact
file paths (`paths.src`, `paths.test`) for each task. Every agent in the
pipeline — spec writer, test writer, implementer — receives the same hardcoded
paths. This has several problems:

1. **Brittleness**: The graph author must know the correct file paths at
   authoring time. If task A creates a file at an unexpected path (e.g., splits
   a module into two files), task B won't know about it.
2. **Duplication**: The same path list is repeated across spec, test, and impl
   tasks. A rename requires updating every task that references it.
3. **Implicit contracts**: The graph YAML doesn't express *what kind* of output
   a task produces (stubs? tests? implementations?). The role templates assume
   this based on role name, but there's no formal declaration or validation.
4. **Rigid roles**: Role-specific templates contain a lot of mechanical
   guidance that could be derived from structured output contracts. If a
   task's inputs and expected outputs were formally declared, the instruction
   template could be simpler and more generic.

## Core idea

**Tasks declare what they produce. Downstream tasks discover what to work on
at runtime, rather than having paths hardcoded in the graph YAML.**

The graph author writes:
- **Task A**: "write stubs for a bounded queue" (no paths needed)
- **Task B**: "write tests for stubs produced by task A" (references A's
  outputs, not specific files)
- **Task C**: "implement stubs produced by task A" (same reference)

Task A runs and produces an **output manifest** declaring what files it
created or modified and what category of output they represent. Tasks B and C
read A's output manifest at launch to discover their input files.

## Design principles

1. **Explicit paths and abstract references coexist.** The current `paths`
   field remains valid and useful for simple graphs or when the author wants
   direct control. `inputs_from` is an alternative for cases where runtime
   discovery is better. Both can be used in the same graph — even on the same
   task (explicit paths supplemented by discovered inputs).

2. **Structured output categories prevent drift.** If the graph author says
   "task A should produce stubs," and task A actually produces something else,
   that's detectable. Output categories (not just file paths) let gates and
   the orchestrator validate that agents produced the *type* of work expected,
   not just *some* files.

3. **Agents can push back via concerns.** If an agent believes a different
   file structure would be better than what the graph implies, it raises a
   concern explaining why. The graph's structural expectations are guidance,
   not a straitjacket — but deviations are surfaced, not silent.

4. **Backward compatible.** Graphs without `inputs_from` or output manifests
   work exactly as they do today. No existing graph YAML breaks.

---

## Proposed architecture

### Output manifest

When a task completes, it writes an **output manifest** to its signal
directory: `signal_dir/outputs.json`. This is a new signal file, written by
the agent SDK before (or as part of) the `.done` signal.

```json
{
  "schema_version": "1",
  "files": [
    {
      "path": "src/agentrelaydemos/bounded_queue.py",
      "action": "created",
      "category": "stubs"
    },
    {
      "path": "src/agentrelaydemos/queue_utils.py",
      "action": "created",
      "category": "stubs"
    },
    {
      "path": "specs/bounded_queue.md",
      "action": "created",
      "category": "spec"
    }
  ]
}
```

**Fields per file entry:**
- `path` — relative to repo root. The actual file the agent created or
  modified.
- `action` — `created` or `modified`. Distinguishes new files from changes
  to existing ones.
- `category` — a tag describing the type of output. See "Output categories"
  below.

**Who writes it:** The agent, via a new SDK command (see below). The agent
knows what files it touched — it just needs a structured way to declare them.

**When it's written:** Before (or alongside) the `.done` signal. The output
manifest must exist before the orchestrator processes the completion, so that
downstream tasks can read it at prepare time.

### Output categories

Categories are short string tags that describe the *purpose* of a file in the
context of the task pipeline. They are not file types (`.py`, `.md`) — they
are semantic labels.

**Initial set (extensible):**

| Category | Meaning | Typical producer |
|---|---|---|
| `stubs` | Function/class stubs with signatures and docstrings | spec_writer |
| `spec` | Supplementary specification document | spec_writer |
| `tests` | Test files | test_writer |
| `implementation` | Implemented source code | implementer |
| `config` | Configuration files | any |
| `docs` | Documentation files | any |
| `other` | Catch-all for uncategorized files | any |

**Categories are free-form strings, not an enum.** The initial set above is
guidance and convention. The graph YAML can reference any category string, and
the agent can declare any category string in its output manifest. Validation
(if desired) happens at the gate level, not at the schema level. This avoids
the need to update the schema every time a new category is useful.

**Categories are about the role a file plays in the pipeline, not its format.**
A `.py` file could be `stubs`, `tests`, or `implementation` depending on the
task that produced it.

### SDK command: `agentrelay-declare`

New CLI command for agents to declare their outputs:

```
agentrelay-declare --path src/bounded_queue.py --action created --category stubs
agentrelay-declare --path src/queue_utils.py --action created --category stubs
agentrelay-declare --path specs/bounded_queue.md --action created --category spec
```

Each invocation appends to `outputs.json` (creates it on first call).
Analogous to how `agentrelay-concern` appends to `concerns.log`.

**Alternative: single call with multiple files.** Could accept a JSON blob
or repeated flags. Start with the simple append-per-call model (matches
existing SDK patterns) and add batch support if needed.

**Alternative: auto-detection from git diff.** The SDK could infer outputs
from `git diff --name-status` against the base branch. This would capture
paths and created/modified status automatically. The agent would only need
to add categories. Trade-off: simpler for agents but less explicit, and the
agent might commit files that aren't meaningful outputs (e.g., formatting
changes to unrelated files). Consider as an enhancement after the explicit
model is validated.

**Integration with completion flow:** `agentrelay-complete` could
automatically run `git diff --name-status` and prompt the agent to categorize
any files not yet declared. Or it could simply warn if no output manifest
exists. Design detail to resolve at implementation time.

### Graph YAML schema extension

#### `inputs_from` on tasks

A new optional field on tasks that specifies which upstream task's outputs
to use as input files:

```yaml
tasks:
  - id: spec_queue
    description: "Write stubs and docstrings for a bounded queue module"
    dependencies: []

  - id: test_queue
    description: "Write tests for all stubs"
    inputs_from:
      task: spec_queue
      category: stubs
    dependencies: [spec_queue]

  - id: impl_queue
    description: "Implement all stubs"
    inputs_from:
      task: spec_queue
      category: stubs
    completion_gate: "pixi run pytest tests/test_bounded_queue.py -q"
    dependencies: [spec_queue, test_queue]
```

**Semantics of `inputs_from`:**
- `task` — the upstream task whose output manifest to read. Must be in the
  task's `dependencies` (transitively).
- `category` — optional filter. If specified, only files matching this
  category are included. If omitted, all files from the upstream task's
  output manifest are included.

**Multiple inputs:**
```yaml
inputs_from:
  - task: spec_queue
    category: stubs
  - task: test_queue
    category: tests
```

**Coexistence with `paths`:** If both `paths` and `inputs_from` are present,
the resolved input set is the union. `paths` provides explicit files the graph
author knows about; `inputs_from` adds files discovered at runtime.

#### `expected_outputs` on tasks

An optional field declaring what the graph author expects this task to produce.
This is not enforced by default — it's guidance for agents and optionally
validated by gates.

```yaml
tasks:
  - id: spec_queue
    description: "Write stubs for a bounded queue"
    expected_outputs:
      - category: stubs
        min_count: 1
      - category: spec
        min_count: 1
    dependencies: []
```

**Fields:**
- `category` — the expected output category.
- `min_count` — minimum number of files expected in this category. Optional;
  defaults to 1 if omitted.
- `max_count` — maximum number of files expected. Optional; no limit if
  omitted.

**Purpose:** Provides structured expectations without rigidity. If the graph
author expects "at least 1 stub file and exactly 1 spec file," and the agent
produces 3 stub files and 1 spec, that's fine. If it produces 0 stub files,
that's a gate-checkable failure.

**Agent concern on deviation:** If an agent believes a different file
structure would be better (e.g., splitting a single module into three), it
can still do so — but the output manifest will show a different structure
than `expected_outputs` anticipated. Instructions should tell agents to raise
a concern when their output structure deviates significantly from
expectations, explaining why the deviation is better.

### Input resolution at prepare time

When the orchestrator prepares a task that has `inputs_from`:

1. Read the upstream task's `outputs.json` from its signal directory.
2. Filter by `category` if specified.
3. Merge with any explicit `paths` on the task.
4. Write the resolved input file list to the task's `manifest.json` (extending
   the existing `paths` section).

The agent sees a single resolved set of input files — it doesn't need to know
whether they came from `paths` or `inputs_from`. The manifest is the source of
truth for what the agent should work on.

**Failure mode:** If the upstream task's `outputs.json` doesn't exist (e.g.,
the upstream task completed but the agent didn't write an output manifest),
the orchestrator should treat this as a preparation error. The task cannot
proceed without knowing its inputs. This is analogous to a dependency failing.

### Gate extensions for output validation

Completion gates currently run arbitrary shell commands. Output validation
can integrate in two ways:

**Option A: Built-in output validation step.** The orchestrator validates
`outputs.json` against `expected_outputs` *before* running the gate command.
If counts are wrong, the task fails without running the gate. Simple and
mechanical.

**Option B: Gate-accessible output manifest.** The gate command has access to
`outputs.json` (it already runs in the worktree with access to the signal
directory). A gate script can validate output structure as part of its checks.
More flexible but requires gate authors to write validation logic.

**Recommendation: Option A for structural validation (count checks), Option B
for semantic validation (content quality).** The orchestrator handles the
mechanical "did the agent produce enough files?" check; the gate handles
"are the files correct?"

### Instruction template changes

With output-driven composition, instruction templates can become more generic:

**Current approach (role-specific):**
```
## What to Do
You are a spec_writer. Write stubs and docstrings for: $src_paths
```

**Output-driven approach:**
```
## What to Do
$description

## Input Files
The following files are your inputs (from upstream tasks):
$resolved_input_files

## Expected Outputs
$expected_output_guidance
```

The `$description` carries the intent ("write tests for the stubs"), and the
resolved input files tell the agent what to work on. The role template becomes
less important — the combination of description + inputs + expected outputs
conveys the same information more flexibly.

**Role simplification timeline:** Roles don't disappear immediately. The
current role templates contain useful guidance beyond just file paths (concern
qualification, review patterns, etc.). But as output contracts become richer,
more of the role-specific guidance can be derived from the structured data.
Observe which role template sections remain genuinely role-specific vs. which
are just compensating for the lack of structured I/O contracts.

---

## How this reduces role complexity

### Today: four roles for a spec-test-impl pipeline

```yaml
- id: spec_queue
  role: spec_writer         # template: "write stubs at $src_paths"
  paths:
    src: [src/bounded_queue.py]
    spec: specs/bounded_queue.md

- id: test_queue
  role: test_writer          # template: "write tests at $test_paths for $src_paths"
  paths:
    src: [src/bounded_queue.py]
    test: [tests/test_bounded_queue.py]

- id: impl_queue
  role: implementer          # template: "implement stubs at $src_paths, run $test_paths"
  paths:
    src: [src/bounded_queue.py]
    test: [tests/test_bounded_queue.py]
```

Paths are duplicated. Role templates do the heavy lifting of explaining what
"spec_writer" vs. "test_writer" vs. "implementer" means.

### Future: same pipeline with output-driven composition

```yaml
- id: spec_queue
  description: >
    Write Python module stubs with full signatures and docstrings for a
    bounded queue data structure. Also write a supplementary spec document.
  expected_outputs:
    - category: stubs
      min_count: 1
    - category: spec
      min_count: 1

- id: test_queue
  description: >
    Write comprehensive tests for all stubs produced by spec_queue.
  inputs_from:
    task: spec_queue
    category: stubs
  expected_outputs:
    - category: tests
      min_count: 1

- id: impl_queue
  description: >
    Implement all stubs produced by spec_queue. All tests from test_queue
    must pass.
  inputs_from:
    - task: spec_queue
      category: stubs
    - task: test_queue
      category: tests
  completion_gate: "pixi run pytest tests/ -q"
```

No explicit `paths`. No `role` (defaults to `generic`). The description +
inputs + expected outputs tell each agent exactly what to do. File paths are
discovered at runtime from upstream output manifests.

**The role field becomes optional sugar**, not a structural requirement. A
graph author who wants the spec_writer template's concern guidance can still
set `role: spec_writer`. But a graph author who prefers to express everything
via descriptions and I/O contracts can use `role: generic` (or omit `role`
entirely) and get equivalent behavior.

---

## Preventing structural drift

A key concern: if agents choose their own file paths, the resulting repo
structure could diverge from what the team expects. Three mechanisms prevent
this:

### 1. Expected output counts in the graph YAML

```yaml
expected_outputs:
  - category: stubs
    min_count: 1
    max_count: 2
```

If the agent creates 5 stub files when the graph expected at most 2, the
orchestrator-level validation (pre-gate) catches this. The task retries or
fails with a clear reason.

### 2. Completion gates with structural assertions

Gates can check not just test passage but file structure:

```yaml
completion_gate: |
  test -f src/agentrelaydemos/bounded_queue.py &&
  pixi run pytest tests/test_bounded_queue.py -q
```

Or with a dedicated validation script:

```yaml
completion_gate: "python tools/validate_outputs.py --task $AGENTRELAY_TASK_ID"
```

Gates are the enforcement point for "did the agent produce what we wanted?"
— both structurally and semantically.

### 3. Agent concerns for structural deviations

Instructions tell agents: "If you believe a different file structure than
what is expected would be significantly better, raise a concern explaining
your reasoning before proceeding with the alternative structure." This
surfaces deviations for human review without blocking the agent from making
a judgment call.

---

## Interaction with graph YAML delivery (sprint 2026-04-03)

Graph YAML delivery gives agents the full graph structure — they can see
what upstream and downstream tasks exist and what they're supposed to do.
Output-driven composition builds on this by:

1. **Adding structure to what agents produce** (output manifests with
   categories and actions).
2. **Adding structure to what agents consume** (`inputs_from` references
   that resolve at runtime).
3. **Connecting the two** via the signal directory artifact store that
   graph YAML delivery already makes navigable.

The observation plan for sprint 2026-04-03 will reveal how agents use graph
awareness. If agents naturally discover and use upstream artifacts via file
reads, the output manifest adds formal structure to what they're already
doing informally. If agents don't use upstream artifacts effectively, the
output manifest may not help — the problem is elsewhere.

---

## Open questions

1. **Should `agentrelay-declare` be required or optional?** If optional,
   graphs without output manifests work as before. If required (for tasks
   with downstream `inputs_from` consumers), the orchestrator validates at
   completion time. Recommendation: required only when a downstream task
   references this task via `inputs_from`. Otherwise optional.

2. **Auto-detection vs. explicit declaration.** Should the SDK infer outputs
   from `git diff` and ask the agent to categorize, or should the agent
   explicitly declare each file? Start explicit; add auto-detection as an
   enhancement. Explicit is more auditable and less error-prone.

3. **Category vocabulary.** Should categories be free-form strings or a
   controlled vocabulary? Free-form is more flexible but risks inconsistency
   ("stubs" vs. "stub" vs. "skeleton"). Start free-form; add validation or
   normalization if inconsistency becomes a problem in practice.

4. **Multiple upstream sources.** When `inputs_from` references multiple
   tasks, should the resolved files be presented as a flat list or grouped
   by source? Flat is simpler for the agent; grouped preserves provenance.
   Consider a `source_task` field in the resolved manifest to preserve
   provenance without complicating the file list.

5. **Interaction with OCI isolation.** Containerized agents currently have
   their worktree mounted read-write. Output manifests are written to the
   signal directory (also read-write). No additional mounts needed — the
   existing signal directory mount handles it. But the orchestrator-side
   input resolution (reading upstream `outputs.json`) happens on the host
   before the container launches, so no container mount changes are needed
   for `inputs_from` resolution.

6. **Gate command environment.** Should `$AGENTRELAY_TASK_ID` and other
   manifest values be available as environment variables in gate commands?
   Currently gates run in the worktree with no special env vars. Adding
   `$AGENTRELAY_TASK_ID` would let generic gate scripts (like
   `validate_outputs.py`) work without hardcoded task IDs.

---

## Implementation sequence (tentative)

This is a multi-PR effort. Sequencing depends on e2e observations from sprint
2026-04-03 and the messaging infrastructure decisions.

1. **Output manifest + `agentrelay-declare` SDK command.** New signal file
   format, new CLI command, agent instruction guidance. No graph YAML changes
   yet — agents can declare outputs voluntarily.
2. **`inputs_from` graph YAML extension.** Schema change, parser update,
   input resolution at prepare time, manifest extension. Requires output
   manifests from upstream tasks.
3. **`expected_outputs` + orchestrator validation.** Schema change, pre-gate
   validation step, agent instruction guidance for deviation concerns.
4. **Gate environment variables.** `$AGENTRELAY_TASK_ID` and related vars
   available in gate commands.
5. **Role template simplification.** Refactor role templates to derive more
   guidance from structured I/O contracts. Preserve role-specific concern
   guidance. Observe which roles become redundant.

---

## Backlog items generated by this discussion

- **Output manifest and `agentrelay-declare`**: New signal file + SDK command
  for agents to declare their outputs with paths, actions, and categories.
  Foundation for `inputs_from` and `expected_outputs`.
- **`inputs_from` graph YAML extension**: Downstream tasks reference upstream
  outputs by task ID and category instead of hardcoded paths.
- **`expected_outputs` graph YAML extension**: Structural expectations
  (category + count bounds) validated pre-gate by the orchestrator.
- **Role template simplification**: Reduce role-specific template content as
  structured I/O contracts make it derivable from data.
