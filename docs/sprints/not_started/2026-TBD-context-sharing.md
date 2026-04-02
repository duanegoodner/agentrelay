# Sprint Notes — Agent Context Sharing

> **Status: Design complete. Draft PR plan at end — not yet scheduled.**
> Originated as a design discussion; promoted to sprint plan.

## Goal

Give agents rich, scalable access to graph-wide context: the full task graph
structure, results from any completed task (not just direct ancestors), and a
mechanism for an agent to send a targeted message to a specific task when it
discovers information that is especially relevant there.

## Core design principle

> **Hard dependencies belong in the graph; `agentrelay-note` is best-effort.**
>
> If task B genuinely cannot produce correct output without task A's results,
> that is a graph dependency — model it as one. The note system is for
> opportunistic, advisory information: "I noticed something you might find
> useful." Notes that are missed (concurrent timing) or late (sent after the
> target completed) are acceptable because they are, by design, not critical
> path. This principle governs every downstream decision: auto-merge is not
> blocked by missed notes, late insights are logged but not acted on
> automatically, and the checkpoint model tolerates races.

## Why this replaces the simple "wire context.md" approach

The original plan (from sprint 2026-04-01-agent-experience.md PR C) would have
assembled a flat summary of upstream task results at dispatch time and written it
to the agent's `context.md`. That approach has three problems at scale:

1. **Context grows unboundedly**: a task late in a large graph accumulates every
   upstream result in one file, most of which is irrelevant to its specific job.
2. **DAG-limited reachability**: agents only see results from their direct
   ancestors. Tasks in parallel branches of the graph are invisible even when
   their output is highly relevant.
3. **Upstream blind spots**: an agent writing a summary has no awareness of
   what downstream tasks will be doing. It cannot tailor or highlight
   information for specific consumers, and those consumers may not even be
   its direct descendants.

## Design space

### Dimension 1: Push vs. pull

| | Push (original context.md) | Pull (proposed) |
|---|---|---|
| Who assembles context | Orchestrator, at dispatch time | Agent, on demand during the task |
| What the agent receives | Pre-assembled summary of upstream results | Access to the full graph artifact store |
| Size | Grows with graph depth | Agent fetches only what it needs |
| Reachability | Direct ancestors only | Any task in the graph |
| Freshness | Snapshot at launch | Live — agent can check back during a long task |

Pull is clearly the right model at scale. The remaining questions are about
what graph knowledge to give agents upfront, and what the query API looks like.

### Dimension 2: Graph YAML exposure

If an agent has the graph YAML and its own task ID, it knows:
- Every task that exists, with its description and role
- Who depends on whom (which tasks produce outputs it might want)
- Who it feeds into (which downstream tasks might benefit from what it discovers)
- The signal directory path for any task (derivable from graph name + task ID)

The graph YAML is already a public artifact — it initiated the run. Sharing it
with agents costs almost nothing and gives them genuine situational awareness
instead of a narrow keyhole view.

**What agents need to navigate the artifact store:**
- Graph name — already in `manifest.json` at `execution.graph_name`
- Task ID — already in `manifest.json` at `task.id`
- Derivation rule: `signal_dir = <repo_path>/.workflow/<graph>/signals/<task-id>/`
- Artifact names: `summary.md`, `concerns.log`, `ops_concerns.log`,
  `.done` (PR URL on line 2), `inbox/`

With just this, an agent can browse any completed task's artifacts with standard
file system reads.

**Biggest free win:** Once agents have the full graph YAML, they can tailor
their summaries for downstream consumers without any new command. An agent
writing its `summary.md` can look at the graph YAML, see what downstream tasks
are assigned to do, and write proactively: "Note for downstream tasks: the cache
module is the bottleneck — task `perf_audit` should look there first." This is
a major quality improvement that costs zero infrastructure beyond graph YAML
delivery. It is a design goal, not just a side effect.

Note: for PR-less tasks, the `agentrelay-summary` CLI command (from the
agent-experience sprint PR C) provides the mechanism for writing `summary.md`.
Without it, PR-less task artifacts in the pull-based model would be empty.

### Dimension 3: Targeted cross-task messaging

Agents sometimes discover something specifically actionable for a particular task
(including tasks in parallel branches). The general summary written to `summary.md`
may not surface this clearly enough for the target.

**Options considered:**

**a) Per-task inbox directory** — each task's signal directory gets an `inbox/`
subdirectory. Any agent writes a targeted note there: `inbox/<source-task-id>.md`.
Inbox is written before the target task launches; late-arriving concurrent notes
could be missed if checked only at launch.

**b) `agentrelay-note --to <task-id> --message "..."` CLI** — formalizes (a).
Writes to `.workflow/<graph>/signals/<task-id>/inbox/<source>.md`.
Sender looks up target task ID from graph YAML. Notes are markdown files —
easy to inspect, no schema required.

**c) Graph-level broadcast log** — a single append-only `.workflow/<graph>/broadcast.log`
with `[for: task_y] ...` entries. Downstream agents scan the log on launch
and filter for their task ID. Handles late-arriving concurrent messages on
re-check. Messier to parse.

**d) No formal mechanism** — rely on graph YAML awareness; upstream agents write
hints in `summary.md` knowing downstream agents can find and read it.

**Decision: option (b)**, with (d) as a natural complement. Explicit, auditable,
minimal infrastructure. Option (d) remains available for loose hints; (b) is for
when prominence matters.

### Dimension 4: Inbox timing for concurrent tasks

LLM agents are sequential, not event-driven. Expecting them to "detect" an
arriving note requires either polling or push.

**Options considered:**

**Structured checkpoints** — instructions define 2–3 natural pause points where
the agent re-checks the inbox (e.g., after initial analysis before writing code;
before PR creation / final signal write). No new infrastructure. Checkpoints
align with moments where the agent is naturally reconsidering before a major
action. Role-specific variants can target the most meaningful pauses for each
role.

**Filesystem watch sidecar** — background process watches inbox and signals the
agent. Too complex; requires a sidecar alongside Claude Code and injecting text
into the tmux pane.

**Accept the race condition** — if truly concurrent tasks A and B are running and
A sends B a note after B has passed its last checkpoint, B misses it. This is
acceptable per the core design principle: hard dependencies belong in the graph.

**Decision: structured checkpoints**, with the final checkpoint at PR creation /
signal file write being the most important. The final checkpoint is a natural
loop: "check inbox, incorporate any changes, then re-check once more before
submitting." This terminates after two passes (new material notes are unlikely
to arrive in that window).

**Looping at earlier checkpoints:** explicit looping instructions ("return to
checkpoint B") are not needed at earlier checkpoints. The agent's general
reasoning handles revision: "if this message significantly changes your approach,
revise your work accordingly." The agent understands what "revise" means — it
edits what it already wrote. Formal loop instructions would be brittle and hard
to follow for an LLM agent.

---

## Decisions

| # | Question | Decision |
|---|---|---|
| 1 | Graph YAML delivery method | Write a copy to the agent's signal directory. The copy is immutable during the run and serves as a record of "what the graph was at orchestrator launch," even if the source YAML is later edited. |
| 2 | Inbox timing for concurrent tasks | Structured checkpoints in instructions (2–3 natural pause points per role). Final checkpoint (pre-PR / pre-signal) has a bounded re-check loop. Concurrent notes that arrive after all checkpoints are accepted as a known limitation — hard dependencies belong in the graph. |
| 3 | Read access scope | Agents have read access to all task signal directories. Per-task visibility restrictions (e.g., only ancestors) are a backlog item for large graphs where unproductive exploration is a concern. |
| 4 | `agentrelay-read` convenience command | Yes — implement it. Protects against future signal dir path changes and gives agents a clean interface. |
| 5 | `agentrelay-note` for tasks not yet launched | Supported. The note command creates the inbox directory lazily; the target agent checks at launch regardless of when the note was written. |
| 6 | OCI isolation mount requirements | Mount `.workflow/<graph>/` read-write as one additional bind mount. Same trust model as the existing `.git` mount. Optional follow-up PR to tighten to read-only signals + specific write paths. |
| 7 | Note entry timestamps | Every `agentrelay-note` write (new file or append to existing) is timestamped. SDK handles this mechanically; agents just provide `--message`. |

---

## Proposed architecture

### SDK path derivation

The `agentrelay-note` and `agentrelay-read` commands need to resolve paths to
other tasks' signal directories. The derivation:

1. Agent has `$AGENTRELAY_SIGNAL_DIR` (e.g., `/data/git/repo/.workflow/mygraph/signals/task_a/`)
2. Navigate up two levels to get the graph signals base: `.../signals/`
3. Append `<target-task-id>/` to reach any task's signal directory

The SDK can compute this from the env var — no additional env var needed. If
we later restructure signal directory paths, `agentrelay-read`/`agentrelay-note`
abstract over it.

For the late insights directory (graph-level), navigate up three levels from the
signal dir to `.workflow/<graph>/`.

### What agents receive at launch

- `graph.yaml` — a copy of the full graph YAML, written to the agent's signal
  directory at task preparation time. Immutable during the run.
- `manifest.json` — already present; already includes `graph_name` (at
  `execution.graph_name`) and `task_id` (at `task.id`).
- Instructions — include a "Graph awareness" section explaining:
  - Your task ID and role in this graph
  - Signal directory formula (absolute path)
  - Artifacts available per task: `summary.md`, `concerns.log`,
    `ops_concerns.log`, `.done` (PR URL line 2), `inbox/`
  - Inbox check guidance (at launch and at structured checkpoints)
  - Guidance to tailor `summary.md` content for known downstream tasks

### What agents can query on demand

Via `agentrelay-read`:
```
agentrelay-read --task <task-id>                   # list available artifacts
agentrelay-read --task <task-id> summary           # print summary.md
agentrelay-read --task <task-id> concerns          # print concerns.log
agentrelay-read --task <task-id> ops-concerns      # print ops_concerns.log
agentrelay-read --task <task-id> done              # print PR URL (line 2 of .done)
agentrelay-read --task <task-id> notes             # list/print all inbox notes
agentrelay-read inbox                              # read own inbox (shorthand)
```

Validates that `<task-id>` exists in the graph YAML. The `inbox` shorthand
(no `--task`) reads the calling agent's own inbox — the most common use case
at each checkpoint.

### Targeted messaging (`agentrelay-note`)

```
agentrelay-note --to <task-id> --message "Found that module X is tightly
coupled to Y — this will affect the refactor you're assigned to. See PR #42
for details."
```

Routing is transparent based on target completion state:
- Target not yet done → writes to target's `inbox/<source-task-id>.md`
- Target already done → writes to `.workflow/<graph>/late_insights/<target-task-id>/<source-task-id>.md`

Creates directories lazily as needed. Validates `--to` against `graph.yaml`.
Inbox directory is cleared on task retry.

### Note and inbox file format

Each `agentrelay-note` invocation writes a timestamped entry. When the target
file does not exist, it is created with the entry. When the file already exists
(same source sending a second note to the same target), the new entry is
appended. This is safe because only one agent (the source) ever writes to a
given `<source-task-id>.md` file — no concurrent append risk.

Entry format (HTML comment timestamps — readable by humans and agents, won't
render as visible noise in markdown viewers, trivially parseable):

```markdown
<!-- 2026-04-01T14:23:07Z -->
Found that module X is tightly coupled to Y — this will affect the refactor
you're assigned to. See PR #42 for details.

<!-- 2026-04-01T15:01:33Z -->
Follow-up: the coupling is worse than I thought — Y re-exports X's internal
types. You'll need to break that before refactoring either side.
```

The SDK handles timestamping mechanically — the agent just provides `--message`.

### Late insights directory structure

Late insights are organized by target task, mirroring the inbox structure:

```
.workflow/<graph>/late_insights/
  <target-task-id>/
    <source-task-id>.md       # timestamped entries, same format as inbox notes
```

Example:
```
.workflow/mygraph/late_insights/
  task_q/
    task_h.md       # H realized something relevant to Q after Q completed
    task_j.md       # J also had a late insight for Q
  task_r/
    task_h.md       # H also had something for R
```

**Why by-target:** the primary access pattern is "what did task Q miss?" — a
human reviewing Q's output, or a future orchestrator deciding whether to re-run
Q. Grouping by target makes that a directory listing. The secondary question
("what did H discover after the fact?") is answered with a glob across target
directories.

**No concurrent write risk:** each file is uniquely identified by the
(target, source) pair, and only one agent (the source) ever writes that file.
Two agents can write to the same target's directory concurrently but they write
to different files.

**Multiple insights from the same source:** handled by appending within the
per-source file (each entry timestamped), same as the inbox model.

### Inbox checkpoint pattern (in instructions)

Instructions per role will define role-appropriate checkpoints. General pattern:

1. **At task launch**: read `inbox/` immediately. Incorporate any notes into
   your initial understanding before doing any analysis.
2. **Before committing to an approach** (role-specific — e.g., after analysis
   but before writing code): re-check inbox. If a significant note arrived,
   revise your approach accordingly before proceeding.
3. **Before creating PR / writing final signal** (all roles): re-check inbox.
   Incorporate any changes. Then re-check once more before submitting (bounded
   re-check loop — if nothing new, proceed).

The final checkpoint loop is the critical one: it catches virtually any note
sent by a concurrent task that completes before the agent finishes its work.

---

## Note lifecycle and failure modes

A note sent via `agentrelay-note` can end up in one of four states:

| State | When | Where it lands | Detection |
|---|---|---|---|
| **Delivered** | Target reads it at a checkpoint | `signals/<target>/inbox/<source>.md` | Normal operation |
| **Concurrent miss** | Target was running but past final checkpoint when note was written | `signals/<target>/inbox/<source>.md` (mtime > `.done` mtime) | Orchestrator scans inbox at task completion |
| **Late insight** | Target already completed (`.done` exists at write time) | `late_insights/<target>/<source>.md` | SDK routes at write time |
| **Delivered late** | Target hadn't completed yet, but reads it at a later checkpoint after initial miss | `signals/<target>/inbox/<source>.md` | Normal operation (the checkpoint loop caught it) |

### Concurrent miss detection

Entirely orchestrator-side, no agent changes needed. At task completion the
orchestrator already processes the signal directory. It scans `inbox/` and
compares each note's modification time against the `.done` write time. Notes
newer than `.done` are definitionally missed.

**Surfacing:**
- `missed_notes.log` written to the signal directory alongside `summary.md` and
  `agent.log` — lists missed note filenames and their content. Durable artifact,
  auditable after the fact.
- `ConsoleListener` event — surfaces missed notes in the terminal immediately,
  similar to how concerns are reported today. Visible to anyone monitoring the
  run.
- Integration PR body — if any task has missed notes, include a warning section
  ("Task X completed but missed N note(s) from concurrent tasks") so it is
  visible in the GitHub review interface without digging into signal directories.

**Auto-merge behavior:** missed notes are warnings, not blockers by default
(per the core design principle). A human monitoring the run can review missed
notes and, if the missed information is serious enough, trigger a partial re-run
of the affected tasks (see backlog: "Human-triggered partial graph re-run").

### Late insights

When an agent sends a note to a task that has already completed, the SDK
detects this (`.done` exists) and routes to the late insights directory.

- Written to `.workflow/<graph>/late_insights/<target-task-id>/<source-task-id>.md`
  with timestamped entries (same format as inbox notes).
- Orchestrator logs a terminal message each time a late insight is written
  (via `ConsoleListener` event).
- Late insights are **not** incorporated into integration PR bodies at this
  time. They are available for human review in
  `.workflow/<graph>/late_insights/` after the run.

**Future:** when the orchestrator gains the ability to commit files to the repo
(see backlog), the `late_insights/` directory becomes a natural candidate for
auto-committed graph artifacts.

### Future options (in backlog)

- `strict_notes` policy — opt-in flag (with per-workstream/task/agent scoping)
  that causes missed notes to block auto-merge. Default remains permissive.
- Orchestrator-driven re-run judgment — orchestrator consults an LLM planning
  agent to evaluate whether a missed note justifies re-running part of the graph
  automatically. High complexity; requires human-triggered re-run to exist first.

---

## OCI isolation and the pull model

The pull-based model assumes agents can read other tasks' signal directories
and write to their inboxes and the late insights directory. At Level 0 (no OCI
isolation) this works — all paths are on the host filesystem. At Level 2 (OCI
containers), the current `OciSandbox` mounts only three paths:

1. The task's own worktree (read-write)
2. The task's own signal directory (read-write)
3. The main `.git/` directory (read-write)

Other tasks' signal directories, `late_insights/`, and the `graph.yaml` copies
in peer signal directories are not mounted.

**Decision: mount `.workflow/<graph>/` read-write** as one additional bind mount
in `OciSandbox.wrap_command()`. This gives agents read access to all task
signal directories and write access to inboxes and `late_insights/`.

**Trade-off:** an agent could write to another task's `.done` or corrupt its
signal files. This is the same trust level as the `.git` mount (already
read-write, allows destructive git operations). Pragmatic for now; the per-task
visibility restrictions backlog item addresses tighter scoping later.

**Optional tightening (PR D):** replace the single `.workflow/<graph>/` read-write
mount with more granular mounts:
- `.workflow/<graph>/signals/` → read-only (all task artifacts readable)
- `.workflow/<graph>/signals/<own-task-id>/` → read-write (own signal dir,
  already mounted today — supersedes the read-only parent for this subtree)
- `.workflow/<graph>/late_insights/` → read-write (late insight writes)
- Individual `inbox/` directories for target tasks could be mounted read-write,
  but enumerating all possible targets at container launch time adds complexity.
  The simpler approach is to rely on the read-only signals mount plus a
  convention that `inbox/` directories are created under `late_insights/` or
  in the agent's own writable area — but this conflicts with the inbox design
  (which writes to the target's signal dir). Alternatively, use the outbox-relay
  pattern: agent writes to its own `outbox/`, orchestrator relays to target
  inboxes. This is cleaner but adds orchestrator complexity and relay latency.

**Decision: implement PR D only if e2e testing shows the broad mount is
problematic.** The tightened mount is available as a backlog item if needed.

---

## Backlog items generated by this discussion

- **Human-triggered partial graph re-run**: allow a human to re-run a subset of
  tasks after reviewing missed notes or other post-completion signals. See
  `docs/BACKLOG.md` (Core Execution section).

- **Orchestrator-driven partial re-run via LLM judgment**: orchestrator consults
  an LLM planning agent to decide whether missed notes justify an automatic
  partial re-run. Prerequisite: human-triggered re-run. See `docs/BACKLOG.md`
  (Core Execution section).

- **`strict_notes` policy**: opt-in flag to make missed notes block auto-merge,
  with granular scoping (graph → workstream → task → agent inheritance). See
  `docs/BACKLOG.md` (Agent Context Sharing section).

- **Per-task signal dir visibility restrictions**: for very large graphs, restrict
  what sections of the graph signal store each agent can see (via filesystem ACLs
  or container bind mount scoping). Implement after basic infrastructure is
  stable. See `docs/BACKLOG.md` (Agent Context Sharing section).

- **Concurrent note delivery via orchestrator injection**: if e2e observation
  shows structured checkpoints miss too many concurrent notes, a future option
  is having the orchestrator watch inbox directories and inject a brief
  notification into the target tmux pane. Very unlikely to be needed.
  See `docs/BACKLOG.md` (Agent Context Sharing section).

---

## PR plan (draft — not yet finalized)

### PR A: Graph YAML delivery + signal dir navigation rules + OCI mount

- Branch: `feat/graph-context-delivery`

**Changes:**
- `task_runner/implementations/task_preparer.py` — write `graph.yaml` (a copy
  of the source YAML content) to the agent's signal directory at prepare time.
- `agent_comm_protocol/templates.py` — add "Graph awareness" section to
  instructions: task ID, graph name, signal dir formula (absolute path),
  artifact names (`summary.md`, `concerns.log`, `ops_concerns.log`, `.done`,
  `inbox/`), inbox check guidance, guidance on tailoring `summary.md` for
  downstream tasks.
- `sandbox/implementations/oci_sandbox.py` — add `.workflow/<graph>/` as an
  additional read-write bind mount so containerized agents can access peer
  signal directories, inboxes, and the late insights directory. The graph name
  is available via `SandboxContext.graph_name`.
- Unit tests: graph YAML written to signal dir, contents match source,
  OCI mount list includes `.workflow/<graph>/`.

**Acceptance criteria:**
- [ ] `graph.yaml` present in signal directory when task launches
- [ ] Instructions include signal dir formula, artifact names, inbox guidance
- [ ] OCI containers mount `.workflow/<graph>/` read-write
- [ ] `pixi run check` passes
- [ ] E2E: agent reads upstream task's `summary.md` via derived path
- [ ] E2E (OCI): containerized agent successfully reads peer task's signal
      directory via the `.workflow/<graph>/` mount

---

### PR B: `agentrelay-note` CLI + inbox + late insights infrastructure

- Branch: `feat/agent-note-command`

**Changes:**
- `src/agentrelay/agent_sdk/` — `agentrelay-note --to <task-id> --message "..."`
  CLI entry point. Path derivation: navigate up two levels from
  `$AGENTRELAY_SIGNAL_DIR` to reach the graph signals base, then append
  `<target-task-id>/inbox/`. At write time, checks whether the target task's
  `.done` file exists:
  - Target not yet done → write/append to `inbox/<source-task-id>.md`
  - Target already done → write/append to
    `late_insights/<target-task-id>/<source-task-id>.md` and emit a terminal
    warning
- Every entry is timestamped by the SDK (HTML comment format). Multiple notes
  from the same source to the same target append to the same file (safe —
  only one agent writes each file).
- Validates `--to` against `graph.yaml` in the agent's signal directory.
- Creates `inbox/` and `late_insights/<target>/` directories lazily as needed.
- `ops/signals.py` (or equivalent) — `inbox/` listed in signal dir spec;
  cleared on task retry.
- Unit tests: note written correctly, timestamp format, append behavior,
  directory created lazily, invalid task ID rejected cleanly, routing based on
  `.done` state, late insight directory structure.

**Acceptance criteria:**
- [ ] `agentrelay-note --to <task-id>` routes correctly based on target
      completion state (inbox vs. `late_insights/`)
- [ ] Every entry has an HTML comment timestamp
- [ ] Multiple notes from same source to same target append correctly
- [ ] Invalid `--to` task IDs rejected with clear error
- [ ] Inbox cleared on task retry
- [ ] Late insights written to `late_insights/<target>/<source>.md`
- [ ] Terminal warning emitted for late insights
- [ ] `pixi run check` passes
- [ ] E2E: upstream agent sends note, downstream agent reads it at launch

---

### PR C: Missed notes detection + surfacing

- Branch: `feat/missed-notes-detection`

**Orchestrator-side changes:**
- At task completion, scan `inbox/` and compare each note's mtime against the
  `.done` write time. Notes newer than `.done` are concurrent misses.
- Write `missed_notes.log` to the signal directory if any concurrent misses
  exist (lists note filenames and content).
- Emit a `missed_notes` `ConsoleListener` event (parallel to how concerns are
  surfaced today).
- Integration PR body builder: if a task has concurrent missed notes, include a
  warning section in the integration PR body.
- Neither concurrent misses nor late insights block auto-merge by default.
- Note: late insight terminal warnings are already handled by the SDK at write
  time (PR B). The orchestrator does not need to duplicate this — its role is
  concurrent miss detection only, which has a natural trigger (task completion).
- Unit tests: concurrent miss detection (mtime comparison), `missed_notes.log`
  written/not written, console event emission.

**Acceptance criteria:**
- [ ] Concurrent missed notes detected at task completion, written to
      `missed_notes.log`, surfaced via `ConsoleListener`
- [ ] Integration PR body includes concurrent missed notes warning where
      applicable
- [ ] Neither miss category blocks auto-merge
- [ ] `pixi run check` passes
- [ ] E2E: concurrent note arrives late → `missed_notes.log`

---

### PR D: `agentrelay-read` convenience command

- Branch: `feat/agent-read-command`

**Changes:**
- `src/agentrelay/agent_sdk/` — `agentrelay-read --task <task-id> [artifact]`
  CLI entry point. Validates task ID against `graph.yaml`. Path derivation same
  as `agentrelay-note` (navigate up from `$AGENTRELAY_SIGNAL_DIR`). Supports:
  - `summary` → `summary.md`
  - `concerns` → `concerns.log`
  - `ops-concerns` → `ops_concerns.log`
  - `done` → PR URL (line 2 of `.done`)
  - `notes` → list/print all `inbox/*.md` files
  - Bare invocation → list available artifacts
- `agentrelay-read inbox` (no `--task`) — shorthand for reading the calling
  agent's own inbox. This is the most common use case (at each checkpoint).
- Unit tests: each artifact type, task ID validation, missing artifact handling,
  `inbox` shorthand.

**Acceptance criteria:**
- [ ] All artifact types readable via `agentrelay-read`
- [ ] `agentrelay-read inbox` reads own inbox without `--task`
- [ ] Invalid task IDs rejected with clear error
- [ ] `pixi run check` passes

---

### PR E: Tighten OCI mounts (optional — implement or push to backlog)

- Branch: `feat/oci-mount-tighten`

Replace the broad `.workflow/<graph>/` read-write mount from PR A with more
granular mounts for tighter isolation:

**Options to evaluate at implementation time:**
- `.workflow/<graph>/signals/` read-only + own signal dir read-write + `inbox/`
  write targets + `late_insights/` read-write
- Outbox-relay pattern: agent writes to own `outbox/`, orchestrator relays to
  target inboxes (eliminates cross-task writes entirely, adds relay latency)

**Decision point:** implement if e2e testing with the broad mount (PR A) shows
agents writing to inappropriate signal files. Otherwise push to backlog.

**Acceptance criteria:**
- [ ] Agents can read all signal directories
- [ ] Agents can only write to their own signal dir, target inboxes, and
      late insights
- [ ] `pixi run check` passes
- [ ] E2E: same test suite as PR A passes with tightened mounts
