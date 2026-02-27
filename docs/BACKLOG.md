# Backlog

Capture ideas here immediately — don't interrupt the current task to implement them.
One item per bullet. Add a brief note if the idea needs context to make sense later.
Move items to `docs/HISTORY.md` when done (with the PR number).

---

## Features

<!-- Significant new capabilities -->

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

- **GitHub Actions for pre-merge checks** — consider running `pixi run check`
  (format + typecheck + tests) via a GitHub Actions workflow on every PR instead
  of relying on the PR checklist. Pros: automated, can't be forgotten, visible
  as a required status check. Cons: slower feedback loop, needs pixi/conda setup
  in CI, removes Claude Code's ability to catch and fix failures before they hit
  the PR. Worth deciding whether Claude Code running checks locally or CI running
  them remotely is a better fit for this project's workflow.

## Ideas / Maybe

<!-- Not sure yet — worth keeping but not committed to -->
