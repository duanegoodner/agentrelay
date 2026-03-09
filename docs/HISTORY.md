# Changelog

Chronological log of significant changes to the main codebase. For full details see each PR on GitHub.

---

## 2026-03-08

### Fix Pylance/pyright config for test files — PR #63

Updated `[tool.pyright]` in `pyproject.toml`:

- Removed `test/**` from `exclude` so VS Code/Pylance resolves imports
  in test files (previously excluded files are not analysed interactively)
- Added `extraPaths = ["src"]` for reliable package discovery under the
  `src/` layout regardless of editable-install detection

Also updated `.gitignore`.

---

## 2026-03-07

### Rename archive → prototypes/v01 — PR #58

Renamed `src/agentrelay/archive/` → `src/agentrelay/prototypes/v01/`,
`test/archive/` → `test/prototypes/v01/`, and `docs/archive/v1/` →
`docs/prototypes/v01/`. Updated all Python import paths and documentation
references accordingly. "Prototypes" more accurately describes the role of
this code than "archive".

---

## 2026-03-06

### Architecture Pivot — PR #51

**Promote current architecture to main package, archive prototype, set up mkdocs**

The original prototype proved the concept but lacked clean separation between task specifications (immutable) and runtime state (mutable). A complete architectural redesign was created in parallel with cleaner data models, better testability, and design for future extensibility.

This PR completes the transition by:
- Promoting core modules (`Task`, `TaskRuntime`, `Agent`, `AgentEnvironment`) to root level in `src/agentrelay/`
- Archiving all prototype modules in `src/agentrelay/prototypes/v01/` for reference
- Setting up mkdocs with mkdocstrings for auto-generated API documentation
- Creating comprehensive new documentation structure

**Result:** Current architecture is now the primary implementation. All new development targets it.

**Key files:** All core modules at `src/agentrelay/`. Prototype reference in `src/agentrelay/prototypes/v01/`.

For historical record of prototype development, see `docs/prototypes/v01/HISTORY.md`.

---

### Foundation — PRs #48–#50

**Build current architecture**

Three PRs established the clean data model:

- **PR #48** — Core types: `Task` (frozen spec), `TaskRuntime` (mutable envelope), `TaskState`, `TaskArtifacts`, addressing types
- **PR #49** — `Agent` class and `TmuxAgent` concrete implementation
- **PR #50** — Refine `Agent` as ABC, introduce `AgentEnvironment` type alias and `TmuxEnvironment`

Result: 467 comprehensive tests, clean separation of concerns, foundation ready for workflow implementation.

---

## Historical Note

For a detailed history of prototype development (PRs #36–#46), see `docs/prototypes/v01/HISTORY.md`. The prototype served as a proof-of-concept and informed the design of the current architecture.
