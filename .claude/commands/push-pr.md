Commit staged/unstaged changes to a new feature branch, push to remote, and open a pull request into main.

Follow these steps in order:

1. **Verify starting point**: Run `git status` and `git branch` to understand the current state. If already on a feature branch (not `main`), confirm with the user whether to continue on this branch or create a new one.

2. **Create a feature branch**: If on `main`, propose a branch name derived from the changes (e.g. `feat/short-description` or `docs/short-description`). Use $ARGUMENTS as the branch name if provided. Create and switch to it with `git checkout -b <branch-name>`.

3. **Commit**: Stage and commit the changes. Ask the user for a commit message if one isn't obvious from context, or derive one from the changes. Stage specific files by name rather than `git add -A` or `git add .`. Follow the repo's commit message conventions (short imperative title, optional body, Co-Authored-By trailer).

4. **Push**: Push the branch to remote with `git push -u origin <branch-name>`.

5. **Open PR**: Use `gh pr create` targeting `main` as the base branch. Derive the PR title and body from the commit(s) on this branch. Use a HEREDOC to pass the body. PR body format:

```
## Summary
<bullet points summarising the changes>

## Test plan
<checklist of things to verify>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

6. **Report**: Print the PR URL when done.
