---
name: land
description: Merge a PR and clean up the feature branch
disable-model-invocation: true
---

Merge a PR and clean up its feature branch.

$ARGUMENTS optionally specifies a GitHub PR number (e.g., "166"). If
omitted, infer the PR from the current branch using `gh pr view`.

Steps:

1. **Find the PR.**
   - If $ARGUMENTS contains a PR number: use `gh pr view <number>` to
     get the PR's branch name, URL, and state.
   - If $ARGUMENTS is empty: use `gh pr view` (infers from current
     branch).
   - If the PR is not open, report the issue and stop.

2. **Check out the PR's branch** if not already on it:
   `git checkout <branch-name>`.

3. **Merge the PR** with `gh pr merge <url> --merge`.

4. **Switch to main**: `git checkout main`.

5. **Pull remote main**: `git pull origin main`.

6. **Delete the feature branch** (local and remote):
   - `git branch -d <branch-name>`
   - `git push origin --delete <branch-name>` (skip if GitHub already
     deleted it on merge).

7. **Confirm cleanup** with `git branch` and `git status`.
