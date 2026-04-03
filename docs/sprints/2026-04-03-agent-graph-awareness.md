# Sprint Notes — 2026-04-03: Context Sharing (Phase 1)

> **Status: Active.** Single-PR sprint: graph YAML delivery + artifact
> navigation instructions + OCI mount. Messaging infrastructure
> (agentrelay-note, agentrelay-read, missed notes detection) deferred pending
> e2e observation. Full design in `docs/discussions/CONTEXT_SHARING.md`.

## Goal

Give agents awareness of the full task graph and the ability to find artifacts
produced by any task — not just direct ancestors. Ship the minimal
infrastructure (graph YAML delivery + instructions), then observe via e2e
testing how agents use this awareness before building targeted messaging.

## Context

Sprint 2026-04-01 (agent experience) shipped agent-facing reliability
improvements: retry fix, COMPLETED status, agentrelay-summary CLI, worktree
CWD guidance, and retry artifact archival. With agents now reliably producing
artifacts (summaries, concerns, signal files), the next step is letting agents
*find* each other's artifacts.

The original context-sharing design (`docs/discussions/CONTEXT_SHARING.md`)
defined a five-PR plan: graph YAML delivery, `agentrelay-note` CLI + inbox,
missed notes detection, `agentrelay-read` CLI, and OCI mount tightening. During
sprint planning, we decided to ship only graph YAML delivery first and observe:

1. **Observation before infrastructure**: Agents receiving the graph YAML and
   signal directory navigation rules can already read any completed task's
   `summary.md`, `concerns.log`, etc. via plain file reads. We should observe
   whether agents actually use this capability and how they tailor their
   summaries for downstream tasks before investing in a formal note/inbox
   system.
2. **Unknown value of messaging**: The `agentrelay-note` system adds
   interesting targeted messaging but it's unclear how much performance benefit
   it provides over the summary-tailoring approach. It also requires
   non-trivial instruction changes (checkpoint guidance per role).
3. **Future retrieval options**: Before building more plain-text context-sharing
   infrastructure, we may want to consider whether a vector DB layer for
   semantic retrieval across task artifacts is the better long-term investment —
   especially as the system moves toward mixed-framework agent teams. The
   filesystem conventions established in this PR are compatible with either
   approach.

## Architecture notes

**Graph YAML delivery**: At graph startup, the orchestrator writes a single
copy of the source graph YAML to `.workflow/<graph>/graph.yaml`. One copy,
written once — not per-task. The copy is immutable during the run — it is a
snapshot of "what the graph was at orchestrator launch," even if the source
YAML is later edited. This fits naturally alongside the existing
`run_info.json` write (which already happens at graph-level at startup). The
agent already receives `graph_name` and `task_id` via `manifest.json`, and
can derive the graph YAML path from its signal directory (navigate up two
levels to `.workflow/<graph>/`).

**Signal directory navigation**: With graph YAML + graph name + task ID, an
agent can derive any task's signal directory:
`<repo_path>/.workflow/<graph>/signals/<task-id>/`. Available artifacts per
task: `summary.md`, `concerns.log`, `ops_concerns.log`, `.done` (PR URL on
line 2). No new CLI commands needed — agents read files directly.

**Instruction changes**: A new "Graph Awareness" section in `templates.py`
tells agents:
- Their task ID and role in the graph
- The signal directory path formula
- What artifacts are available per task
- Guidance to read upstream task summaries before starting work
- Guidance to tailor their own `summary.md` for known downstream tasks

This is the "biggest free win" from the design doc: once agents know what
downstream tasks are assigned to do, they can proactively write targeted
information in their summaries without any messaging infrastructure.

**OCI mount**: For containerized agents (Level 2), `OciSandbox` currently
mounts only the task's own worktree, signal directory, and `.git/`. To enable
cross-task artifact reads, add `.workflow/<graph>/` as an additional
**read-only** bind mount. Since the messaging infrastructure (agentrelay-note,
inbox writes) is deferred, agents only need to read peer signal directories
and the graph YAML. The agent's own signal directory is already mounted
read-write separately (and overlays the read-only parent for that subtree).
If the messaging infrastructure is implemented later, the mount can be
changed to read-write or supplemented with targeted writable mounts.

---

## PR plan

### PR A: Graph YAML delivery + artifact navigation instructions + OCI mount

- Branch: `feat/graph-context-delivery`

**Changes:**
- `run_graph.py` (or orchestrator startup) — write `.workflow/<graph>/graph.yaml`
  once at graph start, alongside the existing `run_info.json` write. The source
  YAML path is available via `TaskGraph` (or threaded from `run_graph.py`).
- `agent_comm_protocol/templates.py` — add "Graph Awareness" section to
  instructions: task ID, graph name, graph YAML path (absolute), signal dir
  formula (absolute path), artifact names (`summary.md`, `concerns.log`,
  `ops_concerns.log`, `.done`), guidance on reading upstream artifacts, guidance
  on tailoring `summary.md` for downstream tasks.
- `sandbox/implementations/oci_sandbox.py` — add `.workflow/<graph>/` as an
  additional read-only bind mount so containerized agents can read peer signal
  directories and the graph YAML. The agent's own signal directory remains
  read-write (already mounted separately). The graph name is available via
  `SandboxContext.graph_name`.
- Unit tests: graph YAML written to `.workflow/<graph>/`, contents match source,
  OCI mount list includes `.workflow/<graph>/`.

**Acceptance criteria:**
- [ ] `graph.yaml` present at `.workflow/<graph>/graph.yaml` when graph starts
- [ ] `graph.yaml` content matches the source YAML
- [ ] Instructions include "Graph Awareness" section with signal dir formula,
      artifact names, and downstream-summary guidance
- [ ] OCI containers mount `.workflow/<graph>/` read-only
- [ ] `pixi run check` passes
- [ ] E2E: agent reads upstream task's `summary.md` via derived path
- [ ] E2E (OCI): containerized agent reads peer task signal directory via
      `.workflow/<graph>/` mount

---

## Deferred items

The following items are designed in `docs/discussions/CONTEXT_SHARING.md` and
backlogged in `docs/BACKLOG.md` (Agent Context Sharing section). They will be
evaluated after e2e observation with graph YAML delivery:

- `agentrelay-note` CLI + inbox + late insights (design doc PR B)
- Missed notes detection + surfacing (design doc PR C)
- `agentrelay-read` convenience command (design doc PR D)
- OCI mount tightening (design doc PR E)
- Vector DB for semantic context retrieval (long-term)

## E2E observation plan

After PR A merges, run e2e tests and observe:
- Do agents read the graph YAML? Do they use it to find upstream artifacts?
- Do agents tailor their `summary.md` for downstream tasks?
- Are there cases where an agent clearly needed to send a targeted message to
  a specific task but couldn't? (This would motivate `agentrelay-note`.)
- Do OCI agents access peer signal directories successfully?
