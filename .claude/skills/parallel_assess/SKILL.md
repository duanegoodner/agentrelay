---
name: parallel-assess
description: Assess whether sprint PRs can be worked on in parallel across worktrees
disable-model-invocation: true
---

Assess whether remaining PRs in the current sprint can be worked on in
parallel, each in its own git worktree.

$ARGUMENTS optionally names which PRs to assess (e.g., "C D E"). If
omitted, assess all non-merged PRs in the active sprint.

## Analysis steps

1. **Identify target PRs.** Find and read the active sprint doc in
   `docs/sprints/`. Identify the PRs to assess (from $ARGUMENTS or all
   non-merged PRs). Read each PR's spec carefully — the "Changes" section
   lists the files and modifications.

2. **Map the file footprint of each PR.** For each PR, list every source
   file, test file, doc file, and diagram file it is expected to touch.
   Include files implied by conventions (e.g., touching `src/agentrelay/`
   means the D2 diagram and its SVGs). Read the actual current state of
   key files to understand their structure — don't guess from names alone.

3. **Check for dependencies between PRs.** For each PR pair, determine
   whether either PR depends on changes introduced by the other:
   - Does PR X import, call, or reference something PR Y creates?
   - Does PR X modify a signature or data model that PR Y also modifies?
   - Would PR X's implementation be fundamentally different if PR Y were
     already done?

   A dependency is a **hard gate** — if PR X depends on PR Y, they
   cannot run in parallel regardless of file overlap. No exceptions.

4. **Assess file overlap for non-dependent PR pairs.** For each
   independent PR pair that shares files, read the overlapping files and
   classify the overlap:

   | Category | Description | Merge risk |
   |----------|-------------|------------|
   | **Independent** | No shared files, no dependency | None |
   | **Overlapping, parallel-safe** | Shared files but clearly different regions (e.g., one adds a function, the other modifies a different function) | Auto-merge expected |
   | **Overlapping, conflict risk** | Same file regions — both modify the same function, same dict, same data structure | Manageable conflict, needs careful merge-order |
   | **Dependent** | Hard gate — one PR needs the other's changes to exist | Cannot parallelize |

   For "conflict risk" pairs, describe:
   - Which specific lines/regions overlap.
   - How complex the conflict resolution would be (trivial rebase vs.
     requires understanding both changes deeply).
   - Whether a specific merge order would reduce conflict pain.

5. **Check for soft dependencies.** Identify cases where a PR doesn't
   strictly depend on another but would benefit from it (e.g., a constant
   or helper that the other PR introduces). Note these as "nice to have"
   — the agent should use pre-existing patterns rather than waiting.

6. **Produce the recommendation.** Output a structured assessment:

   ### PR pair matrix
   A table showing each PR pair and its classification.

   ### Recommended parallel groups
   Which PRs can safely run in parallel, grouped by compatibility.
   If all PRs are independent, say so. If some must be sequential,
   explain the ordering constraint.

   ### Merge order guidance
   If overlap exists, recommend which PR should land first to minimize
   conflict pain for the others.

   ### Risk summary
   One-paragraph overall assessment: is parallel execution worth it for
   this set of PRs, or would sequential be safer?

7. **Ask the user** if they'd like to proceed with the recommended
   parallel grouping before any worktree setup begins.
