# Persistent Agents — Design Discussion

> **Status: Design discussion.** Not yet scheduled. Captures the design space
> for long-lived agents that span multiple tasks, including agent pools,
> routing, and agent forking. No implementation decisions are final — this
> document explores approaches and indicates current leanings.
> See `docs/BACKLOG.md` (Persistent Agents section) for backlog items.

## Motivation

Today, agentrelay instantiates a new agent (Claude Code session in a fresh tmux
pane) for every task. Each agent starts cold — no memory of prior tasks, no
accumulated context. The only state that survives across tasks within a
workstream is on-disk: the worktree contents, the integration branch, and signal
directory artifacts (`summary.md`, `concerns.log`, etc.).

This makes task execution predictable, but it discards something valuable:
**unserialized context**. When an agent works on a task, it builds up internal
state that never makes it into any artifact — dead ends it explored, implicit
understanding of why a particular abstraction was chosen, "I noticed the error
handling in module X is inconsistent but it wasn't relevant to my task"
observations, half-formed hypotheses about code quality. This context is lost
when the agent's session ends.

File-based context sharing (graph YAML delivery, `agentrelay-note`,
`agentrelay-read`) addresses the *serializable* subset: summaries, concerns,
targeted notes. But the richest context — the agent's working memory — can't
survive a `summary.md` round-trip. A downstream agent reading a summary gets
the conclusions but not the reasoning chain that produced them.

Persistent agents close this gap by keeping the LLM session alive across
multiple tasks. The agent carries its full conversation history — every
observation, every failed approach, every implicit pattern — from one task
into the next.

## Relationship to existing context-sharing infrastructure

Persistent agents are a **third axis** of context sharing, not a replacement
for the first two:

| Axis | Mechanism | What survives |
|---|---|---|
| File-based pull | Graph YAML + signal dir reads (shipped, #155) | Structured artifacts: summaries, concerns, PR URLs |
| File-based push | `agentrelay-note` / inbox (designed, deferred) | Targeted messages between specific tasks |
| In-context | Persistent agent sessions | Full reasoning chain, implicit observations, unserialized working memory |

Each axis has different strengths. File-based sharing is auditable, selective
(agents read only what they need), and scales to large graphs. In-context
sharing is richer but bounded by the context window and scoped to what one
agent experienced directly. The three axes compose: a persistent agent that
also has file-based access to other agents' artifacts gets the best of both.

## Core mechanisms

Three distinct mechanisms address different parts of the design space.
Each is independently useful; together they cover the full range of
persistent-agent scenarios.

### 1. Persistent agents (sequential context carryover)

One agent handles multiple tasks sequentially within a workstream, carrying
its conversation history from task to task. After completing Task A, the
agent receives Task B's instructions in the same session rather than being
torn down.

**What changes:**
- `TmuxAgent` lifecycle: instead of create → run → tear down per task, the
  agent stays alive across tasks. Teardown happens when the agent's last
  task completes (or at workstream completion).
- `StandardTaskRunner`: instead of spawning a new agent, it sends the next
  task's instructions to the existing agent's tmux pane.
- Agent identity: today agents are anonymous pane handles. Persistent agents
  need identity — "this is agent `planner` in workstream `ws_auth`, and it
  has handled tasks A and D."

**Value:** Direct context carryover between related sequential tasks. A spec
writer's full reasoning is available when the same agent later writes
integration tests.

### 2. Agent pools (heterogeneous capability within a workstream)

A workstream has multiple agents of different capabilities/costs. Not every
task needs the same model — a spec-writing task may need Opus, while a
boilerplate implementation task works fine with Haiku.

**What changes:**
- The workstream declares an agent pool (named agent slots with model tiers)
  rather than assuming one anonymous agent per task.
- The orchestrator (or assignment logic) picks which agent in the pool gets
  each task, based on model fit, prior context, or both.

**Value:** Preserves cost optimization (expensive models only where needed)
while enabling selective context sharing (related tasks assigned to the same
agent). The graph author controls which tasks share context and which
get independent agents.

**Key design question:** This creates a new concept — the **agent slot** —
which sits between the workstream and the task in the hierarchy. Today the
hierarchy is graph → workstream → task. With pools it becomes graph →
workstream → agent → task (where each agent handles one or more tasks).

### 3. Agent forking (DAG-aware context cloning)

When the task DAG branches, an agent's conversation state is cloned so
both branches inherit the parent's context. This is `fork()` for LLM agents.

**Scenario:** Agent α completes Task A. Task A has two downstream branches:
A → B → C and A → D → E. The context from A is valuable for both C and E,
but they may run in parallel (or even in different workstreams).

```
Agent α works on A
    ├── fork → Agent α₁ works on B → C
    └── fork → Agent α₂ works on D → E
```

**Technical mechanism:** A Claude Code session's state is fundamentally a
conversation history — a sequence of messages. Forking means serializing
the conversation at the fork point and starting two new sessions, each
initialized with the same prefix. Each fork diverges from there.

**Claude Code session storage (empirically verified):** Session state is
stored as a single JSONL file at
`~/.claude/projects/<project-dir>/<session-id>.jsonl`. Each line is a
typed JSON object. The message types observed in real sessions:

| Type | What it is |
|---|---|
| `user` | User/orchestrator messages (includes cwd, git branch, version) |
| `assistant` | Claude's responses (includes tool calls and results) |
| `attachment` | File contents or images attached to messages |
| `file-history-snapshot` | Checkpoints for undo — maps message IDs to tracked file backups |
| `permission-mode` | Permission state changes (e.g., `bypassPermissions`) |
| `pr-link` | PR URLs created during the session |
| `system` | Session metadata (duration, message count) |
| `last-prompt` | The initial prompt that started the session |

Sessions that spawn subagents also get a directory at
`<session-id>/subagents/agent-<id>.jsonl` alongside the parent JSONL.

File-history snapshots (for undo) are stored separately at
`~/.claude/file-history/<session-id>/` as raw file content keyed by
content hash. These are per-session and would not carry over to a fork
(the fork starts a new undo timeline in a potentially different worktree).

Session sizes observed in real agentrelay usage: ~60KB for a short agent
task (single e2e task) up to ~12MB for a long interactive session. These
are trivially cheap to copy — the CoW filesystem optimization (BTRFS/ZFS)
discussed below is unnecessary at these sizes; a plain file copy is fast
enough.

**Claude Code already supports forking.** The CLI flag
`claude --resume <session-id> --fork-session` creates a new session with
a new ID, initialized from the conversation history of the source session.
The forked session picks up fresh environment state (CLAUDE.md, git
branch, etc.) at startup — only the conversation history carries over.
This is exactly what our forking design needs: the fork gets the full
reasoning chain from prior tasks but sees the current worktree state.

The orchestrator's fork operation would be:
1. Record the source session ID (this *is* the snapshot)
2. Launch `claude --resume <session-id> --fork-session`
3. Send the new task's instructions to the forked session

This is much simpler than full conversation serialization — Claude Code
handles the mechanics. The snapshot is just a session ID reference.

**Forking does not require a live process (empirically verified).**
Session JSONLs persist on disk indefinitely after the Claude Code process
exits. `--fork-session` reads the JSONL, copies the conversation prefix
into a new session, and runs from there — no running pane needed.
Verified by successfully forking a session from weeks prior whose
process had long since terminated.

This simplifies the workflow significantly: the orchestrator can let an
agent complete a task, tear down the pane, and fork the dead session
hours or days later on demand. No need to keep panes alive just to
preserve fork-ability. The session JSONL on disk *is* the durable
snapshot — we don't need a separate fork-and-label step at task
boundaries. Just record the session ID after each task completes.

**Project-directory scoping caveat:** Claude Code resolves session IDs
relative to `~/.claude/projects/<project-dir>/`. Attempting to resume a
session from a different project directory fails with "No conversation
found." For cross-workstream forking where workstreams map to different
project directories (e.g., different worktree paths), the orchestrator
would need to handle path mapping or ensure sessions are stored under a
common project directory. Within a single workstream (the primary use
case), this is a non-issue.

**Rollback asymmetry in forked sessions.** Claude Code's undo mechanism
rolls back two things in lockstep: the conversation (JSONL truncation)
and the filesystem (restoring file backups from
`~/.claude/file-history/<session-id>/`). In a normal single-session
workflow, these stay in sync because the file-history covers the full
session.

In a forked session, they diverge. The fork inherits the full
conversation history (back through all prior tasks), but starts a fresh
file-history (new session ID = new, empty backup directory). File backups
only begin accumulating when the fork makes its first edit. This means:

- **Conversation** can be rolled back to any point — including deep into
  a prior task's history.
- **Files** can only be rolled back to the start of the fork's own work,
  since that's the earliest point the fork has backups for.

Rolling the conversation back into a prior task's history without
matching file rollback creates an inconsistency: the LLM sees a
conversation state from "I just finished analyzing the spec" while the
filesystem reflects all subsequent commits. The LLM might reference
files that have changed, attempt to redo committed work, or be confused
by code that "shouldn't exist yet" from its conversational perspective.

**For agentrelay agents, this is a non-issue** — the orchestrator
controls the session lifecycle and would never roll back into a prior
task's conversation. Agents don't have access to undo/rollback tooling.

**For general Claude Code usage, it's worth awareness.** The mismatch
only appears when `--fork-session` is used, because the fork inherits
conversation history but starts a fresh file-history. In the typical
`--fork-session` use case (branching to explore a different approach),
users naturally work forward from the fork point rather than rolling
back past it — but this isn't enforced. A user who forks a session and
then undoes past the fork point will get the conversation/filesystem
desync described above.

**Prompt caching synergy:** The Anthropic API's prompt caching means the
shared prefix (everything through Task A) is cached. Both forks hit that
cache — you get two agents with rich context for barely more than the cost
of one. The cost model actually rewards this pattern.

**Merging forked agents:** If the DAG converges (Task F depends on both
C and E), can the two forks' contexts be recombined? Two divergent
conversation histories don't concatenate cleanly. A practical approach:
one fork continues into F with full in-context continuity; the other
fork's final artifacts are injected as file-based context. A hybrid —
in-context from one parent, file-based from the other. Which fork
continues is itself a routing decision.

### Fork-point snapshots

When we want to fork a busy agent, the valuable context is usually what
the agent learned *before* its current task — not the in-progress work on
the current task. If Agent α gained expert-level context from Task A and
is now partway through Task B, a fork for Task C wants the post-A state,
not the mid-B state. Mid-B context could even be harmful — partially
formed hypotheses, dead-end explorations specific to B, or implementation
details that create unwanted context bleed into C.

This means we need **pre-task snapshots**: a saved reference to the
agent's conversation state captured immediately before the agent begins
each new task.

**What a snapshot actually is (for Claude Code):** Since
`--fork-session` works on terminated sessions (see "Forking does not
require a live process" above), a snapshot at a task boundary doesn't
require an explicit operation at all for non-persistent agents. Each
task's session ID is inherently a frozen snapshot — the JSONL persists
on disk and can be forked at any time.

For **persistent agents** (same session across multiple tasks), the
session JSONL grows as tasks are added. To fork from a specific task
boundary rather than the full history, we need to capture the pre-task
state. Two approaches:

- **Fork-and-label:** Before sending the next task's instructions,
  fork the session (creating a new session ID that preserves the
  pre-task state), then continue the original session with the new
  task. The fork is the snapshot — it's a session JSONL frozen at
  the task boundary, available for future forks.
- **JSONL truncation:** Copy the session JSONL up to the last message
  before the new task begins. This is a file operation, not a Claude
  Code operation — just copy N lines of the JSONL. Simpler than
  fork-and-label but relies on JSONL internals rather than the CLI API.

**Current leaning:** Fork-and-label for persistent agents. It uses the
supported CLI mechanism and produces a valid session ID that can itself
be forked later. The cost is one extra `--fork-session` call per task
boundary per persistent agent — lightweight given the observed JSONL
sizes (60KB–12MB, trivial to copy). For non-persistent agents (the
current model where each task gets its own session), no snapshot
operation is needed — the session ID *is* the snapshot.

**Snapshot strategies:**

**(a) Snapshot every agent before every task.** Every persistent agent
gets a fork-and-label checkpoint before each new task. Any checkpoint
is available as a fork source. This is the most flexible approach —
the router can choose which checkpoint is the best fork point.

**(b) Snapshot only high-value agents.** The graph author marks certain
agent slots (or certain tasks) as snapshot-worthy. Only those
checkpoints are persisted. Lower overhead but requires the graph author
to predict which agents will be fork-worthy — which may not be known
in advance.

**(c) Snapshot all, prune eagerly.** Take snapshots universally (like
approach a), but discard them once a task completes and no remaining DAG
path would benefit from forking at that point. The orchestrator can
determine this from the graph topology: if all downstream tasks that
could benefit from this agent's pre-Task-B state have already been
dispatched or completed, the pre-B snapshot is safe to discard.

**Current leaning:** Approach (a) with optional pruning. Given the
observed session file sizes (60KB–12MB), the storage cost of keeping
all snapshots is negligible — a graph with 20 tasks and 5 persistent
agents might accumulate ~200MB of snapshot JSONLs total. Pruning is
an optimization, not a necessity. This simplifies the implementation:
always snapshot, never worry about whether a snapshot exists.

**Filesystem-level snapshots:** For non-Claude-Code agent frameworks
where session state may be larger (e.g., local LLM KV caches at
hundreds of MB), copy-on-write filesystems (BTRFS, ZFS) or LVM
snapshots could make checkpointing nearly free in both time and space.
A BTRFS snapshot takes microseconds and consumes no additional space
until the data diverges. This is an implementation detail for the
framework adapter layer — Claude Code's small JSONLs don't need it,
but a local LLM adapter might benefit significantly.

## Framework-agnostic design

Agent forking is most naturally expressed today through Anthropic-specific
mechanisms (conversation history serialization, prompt caching for shared
prefixes). However, agentrelay's architecture is intentionally pluggable
— `Agent` is an ABC, `AgentFrameworkAdapter` is a protocol, and the
orchestrator depends on abstractions rather than concrete implementations.

**Forking must follow the same pattern.** The core orchestrator logic
should express forking as a protocol-level operation — "clone this
agent's state and produce a new agent initialized from it" — without
assuming how the underlying framework implements it. Different frameworks
will have different capabilities:

| Framework | Forking mechanism | Fidelity |
|---|---|---|
| Claude Code (Anthropic API) | Serialize conversation JSON, start new session with same prefix | Full conversation history |
| Local LLM (llama.cpp, vLLM, etc.) | Copy KV cache state, or replay conversation prefix | Full (KV cache) or near-full (replay) |
| Other hosted APIs | Replay conversation prefix (if API supports seeding) | Depends on API |
| Frameworks without fork support | Not available — fall back to fresh agent + file-based context | Degraded but functional |

**The critical design constraint:** agentrelay must not *require* forking
support from an agent framework. Forking is an optimization — it
preserves richer context than file-based sharing, but file-based sharing
is the baseline. If a framework doesn't support forking, the routing
decision simply never chooses option (b) "fork a busy agent" — it falls
back to (a) "assign to an idle agent" or (c) "start fresh with
file-based context." The orchestrator's routing logic treats fork
capability as a **capability advertisement** from the framework adapter,
not a hard requirement.

**Protocol sketch:**

```python
class AgentFrameworkAdapter(Protocol):
    def supports_fork(self) -> bool: ...
    def snapshot(self, agent: Agent) -> AgentSnapshot | None: ...
    def fork_from(self, snapshot: AgentSnapshot) -> Agent: ...
```

The `snapshot()` / `fork_from()` methods are only called when
`supports_fork()` returns True. The routing layer checks this before
considering fork as a dispatch option.

## Local LLM agents and forking

Eventually, agentrelay should support local LLM-based agents for tasks
where a cloud model is unnecessary — simple implementations, boilerplate,
straightforward test writing. The original motivation is cost: a local
7B or 13B model handling a trivial task is dramatically cheaper than
Opus.

But local models also offer a **unique advantage for forking research.**
With a local model, we have direct access to the inference engine's
internal state — KV cache, tokenized conversation history, sampling
state. Forking at the KV cache level is both faster and more faithful
than conversation replay: the forked agent starts with the exact same
internal state, not a re-encoding of the same text (which can produce
subtly different hidden states due to attention pattern differences on
re-processing).

**Why this matters for the project:**

- **Prototyping fork mechanics:** Working out the details of snapshot
  timing, storage, pruning, and routing is easier when you can inspect
  and manipulate the low-level state directly. A local model provides
  a transparent sandbox for these experiments.
- **Validating the concept cheaply:** Running persistent-agent
  experiments with local models costs nothing per token. We can run
  many graph executions with different fork strategies and measure
  output quality differences without API costs.
- **Understanding fidelity trade-offs:** Comparing KV-cache forking
  (local) vs. conversation-replay forking (hosted API) reveals whether
  the re-encoding difference matters in practice. If it doesn't,
  conversation replay is sufficient everywhere; if it does, frameworks
  that expose KV cache state have a meaningful advantage.
- **Informing the Rust design:** The Rust implementation will need to
  support both local and hosted models. Understanding the forking
  mechanics of each informs the abstraction layer design — what the
  `AgentFrameworkAdapter` protocol needs to express, and what the
  snapshot format should contain.

**Current leaning:** Local LLM support is not in scope for the minimal
Python prototype, but the framework-agnostic protocol design should
accommodate it from the start. When local model support is implemented
(likely in the Rust era), forking should be one of the first capabilities
validated — both as a cost-effective testing ground and as a way to
build intuition about snapshot mechanics before applying them to
hosted-API agents.

## Agent selection and routing

### Who decides which agent gets which task?

**Approach 1: Static declaration in graph YAML.** The graph author
explicitly assigns tasks to named agent slots:

```yaml
workstream:
  id: ws_auth
  agents:
    - id: planner
      model: claude-opus-4-6
      tasks: [spec_auth, test_auth_integration]
    - id: builder_x
      model: claude-haiku-4-5-20251001
      tasks: [impl_auth_handler]
    - id: builder_y
      model: claude-haiku-4-5-20251001
      tasks: [impl_auth_middleware]
```

**Pro:** Simple, predictable, no runtime routing logic. The graph author
knows their problem and can make good assignments. Produces the most
learning per unit of effort.
**Con:** Rigid — the "right" assignment might depend on runtime state (e.g.,
how hard Task B actually turns out to be, or what A discovered).

**Approach 2: LLM-assisted routing.** The graph YAML declares the pool
(agent slots + model tiers) but doesn't assign tasks. At dispatch time, an
LLM (either the orchestrator with a planning prompt, or a lightweight
meta-agent) sees the available agents, their task histories, and the new
task description, and picks the best fit.

**Pro:** Can reason about semantic relevance, not just graph topology. Can
make nuanced judgments about whether an agent's prior context helps or
hurts for a given task.
**Con:** Adds latency and cost to every dispatch decision. Premature until
static assignment has produced evidence that better routing would help.

**Approach 3: Heuristic routing.** Rule-based assignment without LLM
involvement — prefer an agent that worked on a dependency, prefer a model
tier that matches the task's complexity, prefer idle agents.

**Pro:** No LLM cost at dispatch time.
**Con:** Hard to get right. The relevant "fitness" signal is often semantic
(does this agent's prior experience help with this specific task?) which
is exactly what heuristics struggle with.

**Current leaning:** Start with static (Approach 1) to validate the
concept and gather data. Move to LLM-assisted routing (Approach 2) when
we have evidence that dynamic assignment would improve outcomes. A useful
intermediate step: run with LLM routing and have the LLM explain its
reasoning. Over time, those explanations may reveal patterns that could
be encoded as heuristics (Approach 3) — cheaper routing informed by
LLM-observed patterns. But LLM routing may remain the best long-term
approach; the problem is inherently about semantic judgment.

### Agent selection + forking: a unified routing model

Agent selection and forking compose naturally. Without forking, agent
selection faces a tension: "the best-fit agent is busy on another task."
The options are to serialize (wait for the agent to finish) or settle for
a second-best agent. With forking, this tension dissolves — fork the
best-fit agent and run both tasks in parallel, each with the ideal context.

This means the routing decision becomes a **three-way choice** per task:

| Option | When to use |
|---|---|
| **(a) Assign to idle agent** | An existing agent has relevant context and is available |
| **(b) Fork a busy agent** | The best-fit agent is busy, but its context is valuable enough to clone |
| **(c) Start fresh** | No existing agent has context worth carrying; a cold start is fine |

An LLM router is well-positioned to evaluate all three options. A static
declaration can express (a) and (c) directly, and (b) as "fork from task
X's agent."

## Agent lifecycle management

### Retirement policy

Persistent agents and forking can cause the agent count to grow. Without
bounds, a heavily-branching DAG could produce many live agents consuming
resources (tmux panes, context window memory, API session state).

An agent should be retired when:
- It has no remaining tasks assigned (or likely to be assigned via routing)
- No future fork point in the DAG would benefit from its context
- Its context window is approaching capacity with diminishing returns

The orchestrator already tracks which tasks remain in the DAG. Extending
this to track "which agents have useful context for remaining tasks" is
the natural next step.

### Fork budget

A constraint on total live agents — either a hard cap (like
`max_concurrency` for tasks, but for agent instances) or a soft heuristic
guided by the router. The LLM router could evaluate: "is forking Agent α
worth it for Task E, or is E different enough that a fresh agent would
do just as well?"

### Teardown semantics

Today, `teardown_mode` (always / never / on_success) applies per task.
With persistent agents, teardown applies per agent lifetime — which spans
multiple tasks within a workstream (or across workstreams if
cross-workstream release is enabled). The pane stays alive between tasks;
teardown happens when the agent is retired.

## Workstream and worktree constraints

### The worktree constraint

Today: one agent ↔ one task ↔ one worktree. A persistent agent that
handles multiple tasks must deal with worktrees. Three options:

**(a) Scope agents to one workstream.** Tasks within a workstream share a
worktree and integration branch. A persistent agent stays in that worktree
throughout — no confusion about "which branch am I on." This is the
simplest approach and composes cleanly with everything else.

**(b) Switch worktrees between tasks.** The agent `cd`s to a different
worktree when switching workstreams. Risk: the agent gets confused about
branch state, leaves uncommitted changes in the old worktree, or carries
stale filesystem assumptions.

**(c) Neutral home directory.** The agent has a workspace outside any
worktree and `cd`s into the relevant one per task. Cleaner than (b) but
still requires context-switching.

**Current leaning:** Start with (a) — agents scoped to one workstream.
It's the smallest change and produces the biggest single win (sequential
tasks within a workstream are the most context-related). Cross-workstream
agents are a phase 2 concern.

### Cross-workstream agent release

An agent that finishes all its tasks in Workstream X could be "released"
to Workstream Y — carrying cross-workstream context. The constraint:

> **An agent can only be released to a downstream workstream that has a
> dependency-order relationship with the agent's current workstream.**

This means:
- The agent's current workstream must be fully complete (all tasks done,
  integration PR merged).
- The target workstream must not have started yet, or must be waiting on
  the current workstream.
- The agent "moves" — it leaves Workstream X's pool and joins Workstream
  Y's pool.

The agent switches worktrees at the workstream boundary (between
workstreams, not between tasks). The context it carries is exactly the
kind that's most valuable: "I built the thing that Workstream Y depends
on."

### Forking relaxes the worktree constraint

With forking, an agent doesn't need to *move* across workstreams. Instead,
it forks at the workstream boundary. Each fork enters a different
downstream workstream's worktree. The "one workstream at a time" rule is
satisfied per-fork, while both forks carry the parent's full context.

This is agent migration along the workstream dependency graph — but
implemented as cloning rather than movement, so the source workstream
retains an agent if needed.

## Context window management

### When does the context window fill up?

For workstream-scoped agents handling 2–5 tasks (typical for this
project's graphs), context pressure is unlikely to be a problem. But a
workstream with many tasks, or an agent that migrates across workstreams,
could accumulate significant history.

### Mitigation strategies

| Strategy | Mechanism | Trade-off |
|---|---|---|
| **Compaction** | Claude Code's `/compact` summarizes history | Loses raw detail but preserves key observations; mechanical, no new infrastructure |
| **Selective history** | Only inject relevant prior-task history, not the full conversation | Requires deciding what's "relevant" — essentially re-serializing, which undermines the value proposition |
| **Fork and retire** | When context pressure is high, fork the agent (preserving useful prefix), then the fork starts with a compacted history | Natural fit with the forking mechanism |
| **Agent-maintained scratchpad** | Agent writes key observations to a persistent file between tasks | Hybrid: critical observations survive even if context is compacted |

**Current leaning:** Rely on Claude Code's built-in compaction. It's
already designed for this problem, and for the graph sizes we're working
with, it's likely sufficient. Monitor context utilization during the
static-assignment phase and design more sophisticated strategies only if
compaction proves inadequate.

## Failure modes

### Bug poisoning across tasks

If an agent makes a flawed assumption during Task A and carries it into
Task B, the flaw propagates. With independent agents, Task B starts fresh
and might avoid the same mistake. Persistent context is a double-edged
sword — it carries both insights and errors.

**Mitigation:** File-based artifacts (summaries, concerns) serve as a
cross-check. If Agent α's summary for Task A says X, but the code review
or gate check reveals Y, the discrepancy surfaces. This is not a new
problem — it's the same as a human developer carrying a wrong assumption
across tasks.

### Context bleed and role isolation tension

A persistent `implementer` carrying context across three implementation
tasks is obviously valuable. But a `test_writer` that previously worked
as an `implementer` on the same code has seen the implementation — which
is exactly what role isolation is meant to prevent (tests should verify
behavior, not implementation details).

**This means persistent agents and role isolation are in tension.** The
graph author needs to consider: does assigning tasks of different roles
to the same agent compromise the independence that role separation
provides? In some cases the answer is clearly no (spec → integration
test). In others it's clearly yes (implementer → unit test for the same
module).

**Current leaning:** Document the tension; let the graph author decide.
Static assignment makes this explicit — if you assign both `implementer`
and `test_writer` tasks to the same agent, you're opting into the
trade-off knowingly.

### Reproducibility

Running the same graph twice may produce different results because agent
state varies with conversation history. With independent agents, each
task starts from a deterministic input (instructions + worktree state).
With persistent agents, each task also depends on the conversation history
from prior tasks.

**Mitigation:** This is inherent to the value proposition — you can't
have context carryover and perfect reproducibility. Accept it as a
trade-off and focus on observability: log which agent handled which task,
what context it carried, and what routing decisions were made. The signal
directory already captures per-task artifacts; agent identity and lineage
become additional metadata.

### Debugging difficulty

When a task fails with a persistent agent, the relevant context may span
multiple prior tasks' worth of conversation. Debugging requires
understanding not just the current task but the agent's full history.

**Mitigation:** The existing `agent.log` (tmux scrollback capture)
already captures the full session. With persistent agents, this log grows
to cover all tasks the agent handled — which is more to read, but also
more complete. Agent identity metadata helps: "this failure occurred in
agent `planner` after it handled tasks A, C, and F."

## Pre-Rust scope

### What to build now (minimal Python version)

The goal of the Python implementation is to **validate the concept and
generate evidence** that informs the Rust design — not to be the
production implementation.

**Minimal scope:**
- Static assignment in graph YAML only (Approach 1)
- Agents scoped to a single workstream (no cross-workstream release)
- No forking (single instance per agent slot)
- No runtime routing logic
- Agent lifecycle: spawn once at first assigned task, stay alive through
  subsequent tasks, tear down at workstream completion

This is the smallest change that produces real data on whether persistent
context improves task output quality. It requires modifications to
`TmuxAgent` (lifecycle), `StandardTaskRunner` (send next instructions to
existing pane vs. spawn new), and the graph YAML schema (agent slot
declarations).

**Estimated scope:** 1–2 sprints.

### What to defer to Rust

- LLM-assisted routing
- Agent forking (CLI support exists via `--fork-session`; deferral is a
  scope decision, not a technical blocker)
- Cross-workstream agent release
- Fork budgets and retirement policies
- Context window management beyond built-in compaction

These features change the orchestrator's lifecycle assumptions
fundamentally — every assumption that "task = session" becomes false.
Implementing the full version in Python while Rust is also being built
means two architectures drifting. The Rust state machine should encode
agent identity, lineage, and lifecycle as first-class types.

### Why build anything pre-Rust

The agentic orchestration field is advancing rapidly. A minimal
implementation with a writeup of observed results — "here's what happened
when agents carried context across tasks" — is more valuable to the
broader conversation than a feature-complete v1 released later. The
Python prototype's job is to generate evidence: does persistent context
produce noticeably better output? What failure modes appear? What routing
patterns emerge? That evidence shapes the Rust design from day one rather
than being retrofitted.

## OCI isolation considerations

### The problem

Today, each OCI container is per-task, per-attempt
(`agentrelay-{graph}-{task}-{attempt}`), created with `--rm`
(auto-cleanup on exit). Claude Code runs inside the container, and its
session state lives at `/home/agent/.claude/` on the container's
ephemeral filesystem. When the container is torn down, the session JSONL
is lost.

This breaks both persistent agents (session must survive across tasks)
and forking (session JSONL from container A must be accessible to
container B).

### What Claude Code loads at session startup

Understanding what gets loaded and from where is essential for designing
the mount structure.

**From the working directory (worktree — already mounted):**
- `CLAUDE.md` — project instructions (repo root)
- `.claude/settings.json` — project-level settings
- `.claude/settings.local.json` — local overrides

**From `~/.claude/` (inside the container):**
- `settings.json` — global settings (generated by `setup-credentials.py`)
- `.credentials.json` — auth credentials (generated at startup)
- `projects/<project-dir>/memory/MEMORY.md` — auto-memory index
  (first 200 lines, loaded at startup)
- `projects/<project-dir>/memory/*.md` — individual memory files
  (loaded on demand when referenced)
- `projects/<project-dir>/<session-id>.jsonl` — conversation history
  (loaded on `--resume` or `--fork-session`)

**Project-directory derivation:** Claude Code derives `<project-dir>`
from the cwd by encoding the path (slashes → dashes). Different cwds
produce different project dirs. Within a workstream, all tasks share the
same worktree cwd, so they share the same project dir. Across
workstreams, worktree paths differ, so project dirs differ — this is the
same cross-workstream session resolution caveat noted in the forking
section.

### Memory carries over between sessions (not just conversation)

Memory (`MEMORY.md` + individual memory files) is **per-project-dir,
not per-session**. All sessions in the same project directory share the
same memory. This has implications for persistent agents and forking:

**Without OCI (NullSandbox):** All agents working in the same worktree
share the same project dir on the host, so they share memory. If
Agent α writes a memory during Task A, Agent β in Task B (same
worktree) sees it at startup. This is true today even without persistent
agents — it's inherent to how Claude Code scopes memory.

**With OCI:** Each container has its own `/home/agent/.claude/`, so
memory is isolated per container by default. If we mount a shared
session store, memory comes along for the ride — agents in the same
workstream would share memory.

**Is shared agent memory desirable?** It's a form of persistent
context — but unlike conversation history, memory is explicit and
curated (the agent decides what to save). It could be valuable: an
agent that writes "module X has a subtle coupling to Y" as a memory
during Task A gives all subsequent agents in the workstream that
knowledge for free. It could also be problematic: agent memories
follow Claude Code's own conventions, not our structured
`summary.md`/`concerns.log` artifacts, making them harder to audit.

**Current leaning:** For the minimal Python prototype (NullSandbox
only), memory sharing is a fact of the current architecture — observe
whether agents use it and whether it helps. For OCI, the mount
structure design determines whether memory is shared — design for it
to be shared within a workstream (consistent with the NullSandbox
behavior) but note it as an observation target.

### Mount structure options

**Option 1: Mount the host user's `~/.claude/` into the container.**
Simple but unacceptable — exposes the host user's OAuth tokens, API
key helpers, and personal session history to the container. This is
the opposite of what OCI isolation provides.

**Option 2: Mount a purpose-built session store at `/home/agent/.claude/`.**
Create a per-graph (or per-workstream) directory on the host that
serves as the shared `~/.claude/` for all containers in that scope.
Claude Code's native session resolution works unmodified — sessions
and memory are read from and written to the mount.

**Option 3: Orchestrator-managed JSONL extraction.** After each task,
copy the session JSONL out of the container (via `docker cp`) to a
host location. Before a forked task, copy the source JSONL in. No
shared mount needed.

**Recommendation: Option 2** (purpose-built session store). Option 1
is ruled out on security grounds. Option 3 adds orchestrator complexity
and requires the container to still be running at extraction time
(before teardown). Option 2 lets Claude Code's native session and
memory resolution work without fighting path conventions.

### Mount structure details (Option 2)

The challenge with mounting all of `/home/agent/.claude/` from a shared
store is that `setup-credentials.py` writes credential files
(`settings.json`, `.credentials.json`) into `~/.claude/` at container
startup. With a shared mount, concurrent containers would overwrite
each other's credential files.

**Approach A: Mount only `~/.claude/projects/<project-dir>/`.**
This is the subdirectory that contains session JSONLs and memory.
Credentials, settings, cache, and other files remain on the container's
ephemeral filesystem (generated per container as today). Requires
knowing the project-dir path at container launch time — derivable
from the worktree path.

**Approach B: Mount all of `~/.claude/` but use per-container
credential files.** Move credential generation to a per-container
subdirectory or use environment variables instead of files. More
invasive change to `setup-credentials.py`.

**Approach C: Per-agent subdirectories within the shared store.**
Each agent gets its own subdirectory in the shared store. Credentials
don't collide. But Claude Code doesn't support relocating
`~/.claude/` — it's hardcoded to the home directory. Would require
symlinks or `HOME` env var manipulation per container.

**Current leaning: Approach A.** Mount only the `projects/<project-dir>/`
subdirectory. This is the narrowest mount that achieves session and
memory persistence. Credential files stay ephemeral and per-container.
The orchestrator computes the project-dir path from the worktree path
(same encoding Claude Code uses) and creates the host directory before
launching the first container.

### Experimental validation (Approach A)

Approach A was validated with live Docker containers using the
`agentrelay-agent-claude-code-python` image. All three critical
behaviors were confirmed:

**1. Session JSONL persistence.** Claude Code wrote its session JSONL
to the mounted `projects/<cwd-project-dir>/` directory. The file
survived container teardown and was visible on the host.

**2. Memory visibility.** MEMORY.md and individual memory files placed
in the mounted `projects/<git-root-project-dir>/memory/` directory were
loaded by Claude Code at startup. The agent correctly referenced memory
content during conversation.

**3. Cross-container forking.** A second container successfully forked
a session from the first container using
`claude --resume <session-id> --fork-session`. The forked JSONL
contained the original's full conversation history plus the new
exchange, with a new session ID.

**Key finding: two mounts required.** Claude Code uses two different
project directories for different purposes:

| Purpose | Derived from | Example |
|---|---|---|
| Session JSONLs | cwd (worktree path) | `-data-git-agentrelaydemos-main` |
| Memory files | git repo root (bare repo path) | `-data-git-agentrelaydemos--git-bare` |

Within a workstream, all tasks share the same worktree (cwd) and repo
(git root), so both project dirs are consistent across tasks. The
orchestrator needs to mount both:

```
Host: .workflow/<graph>/agent-sessions/<cwd-project-dir>/
  → Container: /home/agent/.claude/projects/<cwd-project-dir>/
     (session JSONLs live here)

Host: .workflow/<graph>/agent-sessions/<git-root-project-dir>/
  → Container: /home/agent/.claude/projects/<git-root-project-dir>/
     (memory/ lives here)
```

**Project-dir encoding algorithm (verified):** Replace `/` with `-`,
replace `.` with `-`. Confirmed identical between host and container.
Example: `/data/git/repo/.git-bare` → `-data-git-repo--git-bare`.

**Credential isolation confirmed.** `setup-credentials.py` writes to
`~/.claude/settings.json` and `~/.claude/.credentials.json`, which are
outside the `projects/` subtree. These remain on the container's
ephemeral filesystem — no credential leakage through the mount.

### Complete startup file inventory

All files Claude Code loads at startup, categorized by whether the two
`projects/` mounts cover them:

**From the working directory (worktree) — already mounted via existing
OCI bind mount, no additional mount needed:**
- `CLAUDE.md` — project instructions at repo root
- `.claude/settings.json` — project-level settings (permissions, hooks)
- `.claude/settings.local.json` — local overrides
- `.claude/commands/` — custom slash commands
- `.claude/skills/` — custom skill definitions

**From `~/.claude/` — container-ephemeral, generated at startup.
No mount needed or wanted (contains credentials):**
- `~/.claude/settings.json` — global settings (generated by
  `setup-credentials.py`)
- `~/.claude/.credentials.json` — auth credentials (generated at
  startup from injected env var or mounted OAuth token)
- `~/.claude.json` — onboarding state, folder trust (generated by
  `trust-workdir.py`)
- `~/.claude/statsig.json` — baked into Docker image at build time

**From `~/.claude/projects/` — covered by the two mounts:**
- `projects/<cwd-project-dir>/<session-id>.jsonl` — conversation
  history (mount 1)
- `projects/<git-root-project-dir>/memory/MEMORY.md` — memory index
  (mount 2)
- `projects/<git-root-project-dir>/memory/*.md` — individual memory
  files (mount 2)

**Not covered by mounts (gap analysis):**
- `~/.claude/CLAUDE.md` — user-level instructions. Not present in our
  agent setup (not in the Docker image, agents don't have user-level
  instructions). If ever needed, straightforward to add via any of:
  bake into the Docker image (simplest for a universal agent CLAUDE.md),
  mount a shared file as a third bind mount, put the instructions in
  the repo's CLAUDE.md (already mounted via worktree), or generate at
  container startup alongside credentials.

**Not loaded at startup (runtime only, no mount needed):**
- `~/.claude/file-history/` — undo backups (per-session)
- `~/.claude/history.jsonl` — session index
- `~/.claude/plans/`, `~/.claude/todos/` — created during sessions
- `~/.claude/sessions/` — lightweight PID/session-ID index
- `~/.claude/session-env/`, `~/.claude/shell-snapshots/` — per-session
  environment state

**Conclusion:** The two `projects/` mounts cover all startup files that
matter for session persistence, memory sharing, and forking. The only
gap (`~/.claude/CLAUDE.md`) is not currently used and is trivially
addressable if needed.

### Remaining concerns

- **Project-dir encoding stability:** We rely on Claude Code's
  path-to-project-dir encoding remaining stable across versions.
  If the encoding changes, the mount point breaks. Mitigable by
  having the orchestrator verify the encoding at startup (run a
  short Claude Code session and check which project dir it creates).
- **Cross-workstream forking with OCI:** Different workstreams have
  different worktree paths → different cwd project dirs → different
  mount points. Forking across workstreams requires the orchestrator
  to copy the source JSONL from one mount to the other (a one-time
  `cp`, not a persistent mount change). The git-root project dir
  (memory) is shared across all workstreams in the same repo.
- **Memory cleanup between runs:** If the shared store persists
  across graph runs, agent memories from a previous run could leak
  into a new run. The orchestrator should clear or namespace the
  store per run.
- **File-history (undo) backups:** These live at
  `~/.claude/file-history/<session-id>/` — outside the `projects/`
  subtree. With Approach A, they remain on the container's ephemeral
  filesystem. This is fine: forked sessions start a fresh undo
  timeline anyway, and undo within a single task doesn't need
  cross-container persistence.

## Open questions

- **Claude Code session cloning: RESOLVED.** `claude --resume <id>
  --fork-session` creates a new session from an existing session's
  conversation history. This is the forking primitive we need. The
  framework-agnostic protocol should still degrade gracefully for
  frameworks without an equivalent mechanism.

- **Agent identity in signal files:** How should agent identity be
  recorded? Candidate: `manifest.json` gains an `agent.id` field; the
  run-level `run_config.json` gains an agent roster. Agent lineage
  (fork-of relationships) may warrant its own artifact.

- **Interaction with `max_task_attempts`:** If a task fails and is retried,
  does the retry go to the same persistent agent? The agent has context
  about the failure (valuable), but also may be in a confused state
  (harmful). The graph author might want to configure this per task.

- **Interaction with OCI isolation: PARTIALLY RESOLVED.** See the
  "OCI isolation considerations" section. Approach A (mount only the
  `projects/<project-dir>/` subdirectory) addresses session and memory
  persistence across containers. Remaining open: project-dir encoding
  stability, cross-workstream JSONL copying, memory cleanup between
  runs, and whether shared agent memory is desirable or needs controls.

- **Optimal pool sizing:** How many agents should a workstream have? Too
  few and context windows fill up; too many and context isn't shared.
  The answer likely depends on graph size, task complexity, and model
  context window capacity. Empirical data from the static-assignment
  phase will inform this.

- **Fork-merge at DAG convergence:** When two forks' downstream paths
  converge, how is the converging task handled? Current thinking: one
  fork continues with in-context carryover; the other fork's artifacts
  are injected as file-based context. Which fork continues is a routing
  decision. Is there a better approach?

- **Snapshot storage and format: PARTIALLY RESOLVED for Claude Code.**
  For Claude Code, a snapshot is just a forked session ID (via
  fork-and-label). The JSONL file (~60KB–12MB) is small enough that
  keeping all snapshots is negligible storage. For non-Claude-Code
  frameworks (especially local LLMs with KV cache state at hundreds of
  MB), the snapshot format is framework-specific — the adapter layer
  defines its own serialization. A common envelope with framework-specific
  payloads is worth considering but not required for the Python prototype.

- **Snapshot pruning: LOW PRIORITY for Claude Code.** Given observed
  session sizes, a graph with 20 tasks produces at most ~200MB of
  snapshot JSONLs — pruning is an optimization, not a necessity. For
  local LLM KV caches, pruning (or CoW filesystem snapshots) becomes
  more important. Topology-aware pruning interacts with dynamic routing:
  the router may need to declare which snapshots it considers valuable.

- **Copy-on-write filesystem availability:** BTRFS/ZFS snapshots are
  unnecessary for Claude Code's small JSONLs but potentially valuable for
  local LLM KV cache snapshots. In OCI containers the filesystem is
  typically overlayfs. This is a deployment-level concern for the adapter
  layer, not a core orchestrator design question.

- **Local LLM framework selection:** Which local inference engine to
  target first for the `AgentFrameworkAdapter` implementation? Candidates
  include llama.cpp (widest model support, C++ with Python bindings),
  vLLM (production-grade, good KV cache management), and Ollama (easiest
  setup, less low-level access). The choice affects what forking
  mechanisms are available.

---

*This document captures the design space as of 2026-04-16. It is not a
final decision — it explores approaches and indicates current leanings.
Implementation decisions will be made in sprint planning, informed by
this discussion and by evidence from the minimal Python prototype.*
