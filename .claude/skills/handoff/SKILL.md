---
name: handoff
description: Prepare for a session transition — update sprint doc, check memory, identify gaps
disable-model-invocation: true
---

Prepare for handing off to a new Claude Code session. The goal is to leave
a clear trail so the next session can pick up the sprint without re-discovery.

Steps:

1. Read the current sprint doc (`docs/sprints/` — find the active one).
2. Update the sprint doc to reflect completed work:
   - Mark finished PRs with their PR number and "Merged" status.
   - Check acceptance criteria boxes.
   - Add an observations section if e2e testing revealed anything notable.
   - Leave upcoming PR specs unchanged (the next session will use them).
3. Read `MEMORY.md` and check whether it reflects the current state:
   - Sprint status (which PRs are done, which are next).
   - Any new architecture notes from this session's work.
   - Test count if it changed significantly.
   - Update if stale; skip if already current.
4. Check whether any other memory files need updating or creation:
   - New feedback memories (user corrections during this session).
   - New project memories (decisions, constraints discovered).
   - Remove or update memories that are now outdated.
5. Summarize for the user:
   - What was updated.
   - What the next session should start with (next PR from sprint doc).
   - Any open questions or decisions deferred to the next session.

If $ARGUMENTS is provided, treat it as context about what was just completed.
