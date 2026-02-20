# Design Decisions

Key choices made during project setup, with rationale.

## Project name: agentrelay

**Chosen over:** agentorch, stepgate, gatework, agentpipe

"agentorch" was the original name but reads as "agent + torch," causing confusion with PyTorch. "agentrelay" captures the core pattern — agents handing off work like a relay baton.

## Spec format: YAML

**Chosen over:** structured Markdown

YAML is unambiguous to parse programmatically, maps naturally to the structured data in workflow specs (nested properties, typed fields), and Claude handles it well. Markdown would require convention-based parsing that's fragile.

## Interpreter language: Python

**Chosen over:** shell scripts

The orchestrator needs YAML parsing, state management, file watching, and eventually gate evaluation logic. Python handles all of these naturally. Starting with shell and rewriting later would be wasted effort.

## Package layout: src/

**Chosen over:** flat layout (package at repo root)

The `src/` layout is the recommended Python packaging convention. It prevents accidental imports of the development version from the project root directory — you must install the package (even editable) to import it.

Experiments stay at the top level (`experiments/`), separate from the installable package. They import agentrelay via the pixi editable install.

## Environment manager: pixi

**Chosen over:** uv, plain venv

Consistent with tooling used in other projects. Manages both conda and PyPI dependencies, handles Python version, and provides task runners.

## Repository visibility: public

**Chosen over:** private

Enables free GitHub branch protection rules (require PRs, enforce for admins). Also aligns with open-source preference and motivates keeping the project clean and well-documented from the start.

## Branch protection: server-side + local hook

**Chosen over:** either alone

GitHub branch protection enforces the "no direct push to main" rule server-side (can't be bypassed). A local pre-push hook (`scripts/hooks/pre-push`) provides immediate feedback before the push even reaches GitHub. Belt and suspenders.

## Branching strategy: feature branches by default, worktrees for parallel work

**Chosen over:** always-worktree

Most work is sequential — create a feature branch in `main/`, work, PR, merge, pull. New worktrees are only created when multiple tasks are genuinely in progress simultaneously, a branch is being handed off to a dedicated Claude instance, or a long-running task shouldn't block `main/` from staying on the main branch.

## Merge strategy: squash merge

Keeps the main branch history clean — one commit per PR instead of a trail of WIP commits.
