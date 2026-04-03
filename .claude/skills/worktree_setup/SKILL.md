---
name: worktree-setup
description: Create git worktrees for parallel PR development from the current sprint
disable-model-invocation: true
---

Create git worktrees for the specified PRs so they can be developed in
parallel, each in its own isolated working copy.

$ARGUMENTS names which PRs to create worktrees for (e.g., "C D E").

## Steps

1. **Read the active sprint doc** in `docs/sprints/` and extract the
   branch name for each requested PR (from the `- Branch: ...` line in
   each PR spec).

2. **Detect the repository layout.** This project uses a git-bare layout:
   - Bare repo: find it by reading the `.git` file in the current worktree
     (it contains `gitdir: <path>`) or by checking common locations like
     `../.git-bare`.
   - Worktrees directory: `../worktrees/` relative to the primary worktree.
   - Primary worktree: the current working directory (should be `main/`).

3. **Validate preconditions** before creating anything:
   - Confirm the bare repo and worktrees directory exist.
   - For each PR, check that the worktree path doesn't already exist
     (skip if it does, with a note to the user).
   - Check that no branch with the target name already exists locally
     (if it does, offer to reuse it or warn).

4. **Create worktrees.** For each PR, run:
   ```
   git -C <bare-repo-path> worktree add <worktrees-dir>/<branch-name> -b <branch-name> main
   ```
   Use the branch name from the sprint doc (e.g., `feat/agent-summary-command`).
   The worktree directory name should match the branch name with `/` replaced
   by `-` (e.g., `feat-agent-summary-command`).

5. **Report results.** Print a summary table:
   - PR identifier (e.g., "PR C")
   - Branch name
   - Worktree path
   - Status (created / already exists / error)

6. **Print next steps** for the user:
   - How to open a Claude Code session in each worktree
   - Remind that `/kickoff <prX>` can be used in each session
   - Note: the last PR to merge should re-render diagrams with
     `pixi run diagram` to pick up all changes
