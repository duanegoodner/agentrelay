# Multi-Agent Workflow Insights

> Distilled from [a discussion with GPT 5.2](2025-02-22_duane_gpt52.md) on 2026-02-22,
> comparing Claude Code, VS Code Copilot, and Cursor for AI-assisted development.

---

## The Two-Tier Model

The most useful framing that emerged: **separate strategic planning from disciplined execution**, then assign each to the tool best suited for it.

| Tier | Role | Best tool (current) | Why |
|------|------|---------------------|-----|
| **1 — Planning** | Architect / principal engineer | Claude Code (terminal or VS Code ext) | Deep reasoning, repo-wide context, iterative discussion, per-token cost is efficient for text-heavy debate |
| **2 — Execution** | Senior engineer implementing a spec | VS Code Copilot (or other IDE agent) | Transparent terminal output, test-gated loops, per-request pricing makes bulk execution cheap |

The human sits above both tiers as **reviewer and orchestrator** — approving plans, evaluating gates, deciding when to escalate.

### Why this works

Once a plan is clear and validated, execution becomes a discipline problem, not an intelligence problem. All current frontier models (Opus, Sonnet, GPT-5, Gemini Pro) are more than capable of disciplined execution when:

- Scope is constrained
- Verification is automated (tests)
- Drift is prevented (explicit non-goals)
- Feedback loops are tight (small commits, test after each step)

The "genius" (deeper reasoning) matters during planning — identifying edge cases, anticipating failure modes, debating tradeoffs. Once that's encoded in a plan, execution is procedural.

---

## The Plan Packet as Handoff Artifact

The key mechanism enabling cross-tool handoff is a **structured plan file** committed to the repo:

```
docs/plans/2026-02-some-task.md
```

Contents:
- **Goal** (1-2 sentences)
- **Non-goals / do-not-touch list**
- **Assumptions**
- **Step-by-step checklist** (each step: files to touch, exact change, verification command)
- **Rollback strategy**
- **Risks + mitigations**

This artifact:
1. **Reduces context ambiguity** — executor gets a deterministic contract, not a paraphrase of a chat
2. **Makes AI work auditable** — human-readable record of why changes happened, survives chat history
3. **Reduces token/request waste** — no need to re-explain architecture, just reference the plan file
4. **Enables tool switching** — any agent that can read a file and follow instructions can execute

---

## Test Gates as the Key Quality Mechanism

The most important part of this model isn't the plan — it's requiring **tests to pass before proceeding**.

This converts AI execution from generative assistance into a **closed-loop control system**:

1. Implement step N
2. Run tests
3. Fix until green
4. Only then continue to step N+1

When each step is bounded this way:
- Blast radius is limited (small commits)
- Errors are caught early (test feedback)
- Progress is observable (checklist of green steps)
- Reversibility is guaranteed (git revert any step)

### The real limiter becomes test quality

If tests are strong → execution across any tool is reliable.
If tests are weak → you ship plan-compliant but subtly broken code.

This has direct implications for agentrelay: **gate automation (Experiment 4) may deserve higher priority** than originally planned, because it's the mechanism that makes heterogeneous execution safe.

---

## Transparency Preference: "Magic Allowed, but Inspectable"

The preferred operating mode:
- Let the agent work autonomously
- But always have an audit trail: commands run, files changed, test results
- Preview before apply (diffs), command echoing, logs/transcripts

This maps to different tools differently:
- **Copilot in VS Code**: Excellent — runs commands in your terminal, full output visible
- **Claude Code**: Good — shows tool calls and output, but can feel more opaque for complex multi-step sequences
- **Cursor**: Mixed — known issues with terminal output visibility and command lifecycle detection

---

## Escalation Without Blocking Progress

The instruction to the executor:

> "Execute this plan, but be on the lookout for gotchas. Keep working (committing in small increments) unless you find a test-breaking issue. But the team will gladly listen to and discuss your concerns — and be open to well-timed course changes if warranted."

This avoids two failure modes:
- **Blind execution** — missed improvement opportunities, technical debt compounds
- **Constant derailment** — executor keeps redesigning mid-stream, scope creep, planning never stabilizes

The sweet spot: **forward momentum with interrupt capability**.

---

## Cost Architecture

| Tool | Billing model | Best used for |
|------|--------------|---------------|
| Claude Code | Per-token | Discussion-heavy planning, iterative design, spec writing |
| VS Code Copilot ($40/mo) | Per-request (1500 strong / 500 Opus) | Bulk execution, test-fix loops, file edits |
| Cursor Pro+ ($60/mo) | ~$70 API credit pool | Similar to Copilot but less predictable cost |

The optimization: **spend tokens on thinking, spend flat-rate requests on doing.**

With Copilot's per-request model, the amount of work done per request doesn't affect cost. So large-scope requests are economically efficient — as long as quality holds.

---

## How This Relates to agentrelay

agentrelay is already studying multi-agent coordination with explicit verification gates. The GPT discussion validates the core model and adds nuance:

### What the discussion confirms
- The Step → Gate → Step pattern is the right core abstraction
- Test-based gates are the primary quality mechanism (not just human review)
- Structured plan artifacts are essential for cross-agent handoff
- The human's role is orchestrator/reviewer, not line-by-line supervisor

### What the discussion adds
- **Heterogeneous runners**: The runner abstraction should support different agents, not just `claude -p`. The spec shouldn't assume a single execution tool.
- **Plan Packet > bare prompt**: Step prompts may need richer context (non-goals, assumptions, "context capsule") for reliable cross-tool handoff.
- **Cost-aware routing**: In a real workflow, you might want cheaper/faster agents for routine steps and deeper agents for complex ones. The spec could support this.
- **Escalation semantics**: The current spec has `escalation: human` but the GPT discussion suggests a richer model — "flag but continue" vs "stop and escalate."

### What to test next (Experiment 1b)

Before building the Python interpreter, run the same trivial workflow with different tool combinations to understand what the runner abstraction actually needs. See the [approved plan](/home/duane/.claude/plans/humming-juggling-popcorn.md) for details.

---

## Key Takeaways (Ranked)

1. **Separate planning from execution** — use the right tool for each tier
2. **Test gates are the linchpin** — they make any executor safe, regardless of "intelligence"
3. **The plan file is the contract** — deterministic, auditable, tool-agnostic
4. **Forward momentum with interrupts** — don't block on concerns, but surface them
5. **Cost model shapes strategy** — per-token for thinking, flat-rate for doing
6. **Heterogeneous agents are the norm** — the framework should support them, not assume homogeneity
