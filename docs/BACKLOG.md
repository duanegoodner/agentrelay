# Backlog

Capture ideas here immediately — don't interrupt the current task to implement them.
One item per bullet. Add a brief note if the idea needs context to make sense later.
Move items to `docs/HISTORY.md` when done (with the PR number).

---

## Features

<!-- Significant new capabilities -->

- **Retry-with-context loops for TDD groups** — when TEST_REVIEWER returns a CONCERNS
  verdict, write a structured retry-context file to the signal directory and re-run
  TEST_WRITER with accumulated failure history. The agent sees all previous failure
  reasons without any special retry logic inside agents — just files. Cap with a
  `max_retries` YAML field to bound run time. This is the natural complement to
  machine-readable verdicts (Idea 5 in `TDD_GROUP_POSSIBLE_IMPROVEMENTS.md`) and
  converts a hard stop into a repair cycle. Implementation touches: orchestrator loop
  in `run_graph.py`, TDD prompt builders, and optionally `AgentTask` / YAML schema
  for the retry cap.

- **Human escalation checkpoints** — add an optional `escalation: human` flag to
  `tdd_groups:` entries (and potentially plain `tasks:`). When set, the orchestrator
  pauses after the review step (or after `max_retries` auto-escalation) and polls for
  a human-written `human_approval.txt` in the signal directory before proceeding. A
  lighter `escalation: notify` level could log a desktop-style message and continue
  automatically. Default is `auto` (current behavior). This adds a human-in-the-loop
  capability with no impact on existing graphs. Implementation touches: YAML schema,
  `AgentTask` / `TDDTaskGroup` data models, orchestrator dispatch loop.

- **Multi-agent backend support** — allow tasks to be dispatched to coding assistants
  other than Claude Code (e.g. OpenAI Codex CLI, a Copilot-based agent, Gemini Code
  Assist CLI). The main change points are `launch_agent()` and `send_prompt()` in
  `task_launcher.py`, which currently hardcode `claude --dangerously-skip-permissions`
  and the Claude-specific bypass-dialog key sequence. A natural approach:
  - Add an `AgentBackend` enum or dataclass (e.g. `CLAUDE`, `CODEX`, `GEMINI`, …)
    with per-backend launch command, startup flags, and any interactive-dialog handling
  - Add an optional `backend` field to `AgentTask` (defaults to `CLAUDE` for
    backwards compat); expose it in the graph YAML too
  - Factor `launch_agent` / `send_prompt` into a small `AgentBackend` protocol so
    each backend can own its own launch + prompt-delivery logic
  - Consider whether `worktree_task_runner.py` (the agent-side API for writing signal
    files) needs to be backend-agnostic, or if each backend simply calls the same
    sentinel-file convention

- **Reasoning-model task analysis and assistant routing** — before dispatching any
  tasks, run a planning step in which a strong reasoning model (e.g. Claude Sonnet or
  Opus via the Anthropic API) inspects each `AgentTask` and produces structured
  estimates: rough complexity tier (trivial / moderate / complex), expected output
  size / context pressure, and a recommended backend. Inputs to the analysis: task
  description, `AgentRole`, position in the dependency graph (leaf vs. fan-in), and
  any available codebase context. The recommendation can then be written back to
  `AgentTask.backend` (once that field exists — see item above) before the
  orchestrator loop starts.
  Optional extension: pair the complexity estimate with a simple cost model (estimated
  tokens × per-token price for each candidate backend) so the orchestrator can weight
  task difficulty, model capability, and cost together when making routing decisions —
  e.g. route trivial tasks to a cheaper model and reserve Opus-class agents for
  complex fan-in tasks. Results could be logged to a `routing_plan.json` alongside
  `run_info.json` for auditability.

## Improvements

<!-- Enhancements to existing behaviour, UX, error handling, etc. -->

- **Live run_state.json** — a mutable per-run document at
  `.workflow/<graph>/run_state.json` that tracks each task's status, attempt count, and
  timestamps in real time. Currently agentrelaysmall reconstructs state from scattered
  signal files on restart (hydration); an explicit state document would make that logic
  simpler and more robust (missing signal file = wrong state today). Would also serve
  as the natural place to record retry attempt counts for the retry-with-context loop
  feature. Richer than the existing `run_info.json` (which is a one-time snapshot of
  start HEAD + timestamp, not a live state document).

- **Structured audit log** — an append-only `.workflow/<graph>/audit.jsonl` where each
  line is a timestamped JSON event: task dispatched, signal received, verdict parsed,
  retry attempted, merge completed, escalation triggered, etc. Currently
  agentrelaysmall writes `agent.log` (raw tmux scrollback) and `summary.md` (PR body),
  which are human-readable but not machine-queryable. An audit log would enable
  grep/jq analysis across runs, per-task duration statistics, and retry rate tracking.
  Most useful once retry loops and escalation are in place — those add many new event
  types worth logging.

- **GitHub Actions for pre-merge checks** — consider running `pixi run check`
  (format + typecheck + tests) via a GitHub Actions workflow on every PR instead
  of relying on the PR checklist. Pros: automated, can't be forgotten, visible
  as a required status check. Cons: slower feedback loop, needs pixi/conda setup
  in CI, removes Claude Code's ability to catch and fix failures before they hit
  the PR. Worth deciding whether Claude Code running checks locally or CI running
  them remotely is a better fit for this project's workflow.

## Ideas / Maybe

<!-- Not sure yet — worth keeping but not committed to -->

- **Agent-generated graph specs** — a pre-run planning step (Claude Opus/Sonnet via
  the Anthropic API, not an interactive session) reads a natural-language project
  description and produces a valid `graph.yaml` that drives agentrelaysmall's normal
  execution. This would lower the barrier to adopting the system for large or complex
  projects where authoring the task graph is itself a design problem. Pairs naturally
  with the reasoning-model routing item under Features above (the routing analysis and
  spec generation could be a single planning step). Speculative: requires significant
  prompt engineering and validation that the agent reliably produces valid YAML.
