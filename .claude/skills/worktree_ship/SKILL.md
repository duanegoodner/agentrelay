---
name: worktree-ship
description: >
  Ship a PR from a worktree with parallel-batch awareness. Checks actual
  file overlap with sibling worktrees, auto-strips conflicting generated
  artifacts (SVGs, auto-generated .d2), warns about hand-edited overlap,
  then commits, pushes, and opens a PR.
disable-model-invocation: true
---

Ship a feature branch from a worktree, with awareness of other worktrees
in the same parallel batch.

$ARGUMENTS should identify the target PR (e.g., "prC"). If omitted, the
skill infers the PR from the current worktree's branch name and the
active sprint doc.

## Phase 1: Overlap analysis

1. **Detect the repository layout.** This project uses a git-bare layout:
   - Bare repo: find it by reading the `.git` file in the current worktree
     (it contains `gitdir: <path>`) or by checking common locations like
     `../.git-bare`.
   - Worktrees directory: `../worktrees/` relative to the primary worktree.

2. **Identify sibling worktrees.** List all worktrees under the worktrees
   directory (excluding the primary `main/` worktree). These are the
   parallel batch.

3. **Compute actual file overlap.** For each sibling worktree:
   - Run `git diff main --name-only` in this worktree and each sibling.
   - Compute the intersection — files changed by both.

4. **Classify overlapping files.** For each overlapping file:

   **Auto-generated artifacts** (strip from this PR, defer to follow-up):
   - `docs/diagrams/uml/diagram-detailed.svg`
   - `docs/diagrams/uml/diagram-modules.d2`
   - `docs/diagrams/uml/diagram-modules.svg`
   - `docs/diagrams/uml/modules/*.d2`
   - `docs/diagrams/uml/modules/*.svg`

   **Hand-edited source/docs** (warn the user, proceed if they confirm):
   - Any file not in the auto-generated list above.

5. **Report overlap findings** before proceeding:
   - List auto-generated files that will be stripped (unstaged via
     `git checkout main -- <file>` to revert them to the main version).
   - List any hand-edited overlap with a note about which sibling
     worktree also changed that file.
   - If no overlap, say so.

6. **Strip auto-generated artifacts.** For files classified as
   auto-generated, revert them to the `main` version so they are not
   included in the commit:
   ```
   git checkout main -- <file>
   ```
   This removes the diff for those files without affecting anything else.

## Phase 2: Ship (same as /ship, adapted for worktree context)

7. Run `git status` (no -uall flag), `git diff` (staged + unstaged), and
   `git log --oneline -5` to understand the current state.
8. Stage all relevant changed/new files (prefer naming files explicitly
   over `git add -A`). Do NOT stage files that likely contain secrets.
   Do NOT stage files that were stripped in Phase 1.
9. Write a concise commit message (1-2 sentences) focusing on the "why".
   End the message with:
   ```
   Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
   ```
   Use a HEREDOC to pass the commit message.
10. Push the branch to the remote with `-u`.
11. Create a PR with `gh pr create`. The PR body must include:
    - `## Summary` (1-3 bullet points)
    - `## Test plan` (bulleted checklist)
    - If auto-generated artifacts were stripped, add a note:
      "Diagram re-render deferred — will be included after all parallel
      PRs in this batch are merged."
    - Footer: `Generated with [Claude Code](https://claude.com/claude-code)`
    Use a HEREDOC for the body.
12. Print the PR URL when done.

If $ARGUMENTS includes additional context, use it for the commit message.
