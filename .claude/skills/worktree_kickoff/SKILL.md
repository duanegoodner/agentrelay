---
name: worktree-kickoff
description: Create a worktree for a PR and kick off development with parallel-awareness
disable-model-invocation: true
---

Create a git worktree for a single PR and begin development, with
awareness of other PRs being worked on concurrently.

$ARGUMENTS should identify the target PR and optionally which PRs are
being worked on in parallel. Examples:

- `prC --parallel-with D, E`
- `prD --parallel-with C, E`
- `prE` (no parallel context)

## Phase 1: Worktree creation

1. **Find and read the active sprint doc** in `docs/sprints/`. Identify
   the target PR from $ARGUMENTS and extract its branch name (from the
   `- Branch: ...` line in the PR spec).

2. **Detect the repository layout.** This project uses a git-bare layout:
   - Bare repo: find it by reading the `.git` file in the current worktree
     (it contains `gitdir: <path>`) or by checking common locations like
     `../.git-bare`.
   - Worktrees directory: `../worktrees/` relative to the primary worktree.

3. **Validate preconditions:**
   - Confirm the bare repo and worktrees directory exist.
   - Check that the worktree path doesn't already exist. If it does,
     ask the user whether to reuse it or recreate it.
   - Check that the branch doesn't already exist locally. If it does,
     offer to reuse it.

4. **Create the worktree:**
   ```
   git -C <bare-repo-path> worktree add <worktrees-dir>/<dir-name> -b <branch-name> main
   ```
   The worktree directory name is the branch name with `/` replaced by `-`.

5. **Switch working directory** to the new worktree. All subsequent work
   happens there.

## Phase 2: Kickoff (runs inside the new worktree)

6. **Read the target PR's full spec** in the sprint doc (already opened
   in Phase 1). Also read the specs of any `--parallel-with` PRs to
   understand what they're changing.

7. **Review the project and recent work:**
   - Read `MEMORY.md` for architecture notes, recent changes, and user
     preferences.
   - Check `git log --oneline -10` for recent commits.
   - Read key source files that the PR will touch or depend on — not just
     files named in the spec, but the surrounding architecture (protocols,
     implementations, orchestrator dispatch pipeline, wiring, tests) to
     understand the current state and patterns established by recent PRs.

8. **Parallel awareness.** If `--parallel-with` was provided:
   - Read each parallel PR's spec and note which files it will modify.
   - For any file your PR also touches, flag it as a **shared file**.
     Note the specific regions each PR is expected to modify.
   - If a parallel PR introduces something your PR could benefit from
     (e.g., a new constant or helper), note it as a **soft dependency**
     but do NOT depend on it — implement your PR against the current
     codebase as-is.
   - Do NOT wait for or assume any parallel PR's changes exist.

9. **Propose a mid-level overview** of how to tackle the PR:
   - Which layers/files are involved and what changes each needs.
   - Key design decisions or trade-offs to consider.
   - Anything that depends on or interacts with recently shipped work.
   - If there are shared files with parallel PRs, note them and explain
     how your changes avoid or minimize conflict.
   - Do NOT produce a full step-by-step implementation plan yet — just
     enough for the user to align on the approach before planning begins.

10. **Ask the user** if the approach looks right before proceeding further.
