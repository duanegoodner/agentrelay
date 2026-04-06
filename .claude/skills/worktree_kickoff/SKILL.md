---
name: worktree-kickoff
description: Kick off PR development inside an existing worktree with parallel-awareness
disable-model-invocation: true
---

Kick off development for a single PR inside the current worktree, with
awareness of other PRs being worked on concurrently. This skill assumes
the worktree already exists (created via `/worktree_setup`) and that
Claude Code was launched with this worktree as its workspace root.

$ARGUMENTS should identify the target PR and optionally which PRs are
being worked on in parallel. Examples:

- `prA --parallel-with B, C`
- `prB --parallel-with A, C`
- `prC` (no parallel context)

## Steps

1. **Identify the target PR.** Use $ARGUMENTS to determine which PR this
   worktree is for. Confirm by checking the current branch name
   (`git branch --show-current`) — it should match the sprint doc's
   branch for this PR.

2. **Find and read the active sprint doc** in `docs/sprints/`. Read the
   target PR's full spec. Also read the specs of any `--parallel-with`
   PRs to understand what they're changing.

3. **Review the project and recent work:**
   - Read `MEMORY.md` for architecture notes, recent changes, and user
     preferences.
   - Check `git log --oneline -10` for recent commits.
   - Read key source files that the PR will touch or depend on — not just
     files named in the spec, but the surrounding architecture (protocols,
     implementations, orchestrator dispatch pipeline, wiring, tests) to
     understand the current state and patterns established by recent PRs.

4. **Parallel awareness.** If `--parallel-with` was provided:
   - Read each parallel PR's spec and note which files it will modify.
   - For any file your PR also touches, flag it as a **shared file**.
     Note the specific regions each PR is expected to modify.
   - If a parallel PR introduces something your PR could benefit from
     (e.g., a new constant or helper), note it as a **soft dependency**
     but do NOT depend on it — implement your PR against the current
     codebase as-is.
   - Do NOT wait for or assume any parallel PR's changes exist.

5. **Propose a mid-level overview** of how to tackle the PR:
   - Which layers/files are involved and what changes each needs.
   - Key design decisions or trade-offs to consider.
   - Anything that depends on or interacts with recently shipped work.
   - If there are shared files with parallel PRs, note them and explain
     how your changes avoid or minimize conflict.
   - Do NOT produce a full step-by-step implementation plan yet — just
     enough for the user to align on the approach before planning begins.

6. **Ask the user** if the approach looks right before proceeding further.
