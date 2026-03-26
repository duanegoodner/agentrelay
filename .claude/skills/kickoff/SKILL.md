---
name: kickoff
description: Start work on a new PR — review context and propose a mid-level approach
disable-model-invocation: true
---

Begin work on a new PR from the current sprint plan.

$ARGUMENTS should identify which PR to work on (e.g., "PR B" or
"PR B from docs/sprints/2026-03-25.md").

Steps:

1. Find and read the active sprint doc in `docs/sprints/`.
2. Identify the target PR from $ARGUMENTS and read its spec in the sprint doc.
3. Review the project and recent work:
   - Read `MEMORY.md` for architecture notes, recent changes, and user
     preferences.
   - Check `git log --oneline -10` for recent commits.
   - Read key source files that the PR will touch or depend on — not just
     files named in the spec, but the surrounding architecture (protocols,
     implementations, orchestrator dispatch pipeline, wiring, tests) to
     understand the current state and patterns established by recent PRs.
4. Propose a **mid-level overview** of how to tackle the PR:
   - Which layers/files are involved and what changes each needs.
   - Key design decisions or trade-offs to consider.
   - Anything that depends on or interacts with recently shipped work.
   - Do NOT produce a full step-by-step implementation plan yet — just
     enough for the user to align on the approach before planning begins.
5. Ask the user if the approach looks right before proceeding further.
