---
name: kickoff_sprint_discussion
description: Review backlog, categorize items, and suggest sprint priorities
disable-model-invocation: true
---

Prepare for a sprint planning discussion when no active sprint exists.

Steps:

1. **Read context**:
   - Read `docs/BACKLOG.md` for all candidate work items.
   - Read `MEMORY.md` for recent changes, architecture state, and user
     preferences.
   - Check `git log --oneline -10` for recent commits.
   - Scan `docs/sprints/complete/` to understand the arc of recent sprints
     (what themes have been in focus, what was deferred).

2. **Categorize backlog items** into groups such as:
   - **Infrastructure / plumbing** — internal improvements, build system,
     CI, container infra, credential management.
   - **Agent behavior / instructions** — how agents receive and interpret
     tasks, concern handling, role-specific issues.
   - **Orchestrator features** — scheduling, retry, gating, multi-graph,
     observability.
   - **Extensibility / future-proofing** — new frameworks, new environments,
     Rust migration, multi-model support.
   - **Documentation / testing gaps** — missing docs, e2e coverage holes.
   - Use your judgment on categories — these are suggestions, not fixed.

3. **Suggest a priority ordering** with rationale:
   - Which items build on recently shipped work (momentum)?
   - Which items unblock other items (dependencies)?
   - Which items reduce risk or friction for ongoing e2e testing?
   - Which items are quick wins vs. multi-PR efforts?
   - Flag any items that seem stale or already addressed.

4. **Present to the user**:
   - A categorized summary of the backlog (not the full text — concise
     descriptions with section references).
   - A suggested "top 3–5 items" for the next sprint, with reasoning.
   - Any items you'd recommend removing or merging with others.
   - Ask the user which direction they want to go before drafting a
     sprint doc.
