# Backlog

Capture ideas here immediately — don't interrupt the current task to implement them.
One item per bullet. Add a brief note if the idea needs context to make sense later.
Move items to `docs/HISTORY.md` when done (with the PR number).

---

## Features

<!-- Significant new capabilities -->

## Improvements

<!-- Enhancements to existing behaviour, UX, error handling, etc. -->

- **GitHub Actions for pre-merge checks** — consider running `pixi run check`
  (format + typecheck + tests) via a GitHub Actions workflow on every PR instead
  of relying on the PR checklist. Pros: automated, can't be forgotten, visible
  as a required status check. Cons: slower feedback loop, needs pixi/conda setup
  in CI, removes Claude Code's ability to catch and fix failures before they hit
  the PR. Worth deciding whether Claude Code running checks locally or CI running
  them remotely is a better fit for this project's workflow.

## Ideas / Maybe

<!-- Not sure yet — worth keeping but not committed to -->
