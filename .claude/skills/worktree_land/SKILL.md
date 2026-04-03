---
name: worktree-land
description: >
  Merge a worktree PR and clean up. If conflicts arise, offers to rebase
  and resolve. After the last PR in the parallel batch, re-renders
  diagrams and commits the follow-up to main.
disable-model-invocation: true
---

Merge one worktree PR into main and clean up. Handles conflicts via
rebase if needed, and detects when this is the last PR in the batch
to trigger deferred work (diagram re-render).

$ARGUMENTS should identify the target PR (e.g., "prC"). If omitted, the
skill infers the PR from the current worktree's branch name and the
active sprint doc.

## Phase 1: Merge the PR

1. **Find the PR** for the target branch using `gh pr view` or
   `gh pr list --head <branch-name>`.

2. **Attempt to merge** the PR with `gh pr merge <url> --merge`.

3. **If the merge fails due to conflicts:**
   - Switch to the worktree for this branch.
   - Fetch and rebase onto the updated main:
     ```
     git fetch origin main
     git rebase origin/main
     ```
   - If conflicts arise during rebase, resolve them:
     - Read both sides of each conflict.
     - Apply the correct resolution (both changes if additive, or the
       semantically correct merge if they overlap).
     - `git add <resolved-files> && git rebase --continue`
   - Force-push the rebased branch: `git push --force-with-lease`.
   - Retry the merge: `gh pr merge <url> --merge`.
   - If it still fails, report the issue to the user.

## Phase 2: Clean up

4. **Pull main** to get the merged changes:
   ```
   git -C <primary-worktree> pull origin main
   ```

5. **Remove the worktree and branch:**
   ```
   git -C <bare-repo-path> worktree remove <worktree-path>
   git -C <bare-repo-path> branch -d <branch-name>
   ```
   The remote branch is typically deleted by GitHub on merge. If not,
   also run `git push origin --delete <branch-name>`.

## Phase 3: Check for deferred work

6. **Detect if this was the last PR in the batch.** Check:
   - Are there any remaining sibling worktrees in the worktrees directory?
   - Read the active sprint doc — are there other non-merged PRs in the
     current parallel group?

7. **If this was the last PR:**
   - Switch to the primary worktree (`main/`).
   - Re-render diagrams: `pixi run diagram`.
   - If the render produced changes, commit them:
     ```
     git add docs/diagrams/
     git commit -m "docs: re-render diagrams after parallel PR batch"
     ```
   - Push to main (or create a trivial PR if branch protection requires it).
   - Report what was done.

8. **If other PRs remain in the batch:**
   - Note which PRs are still pending.
   - Remind the user to run `/worktree-land` for the remaining PRs.
