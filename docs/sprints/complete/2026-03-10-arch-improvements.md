# Sprint Notes — 2026-03-10: Architecture Improvements

Paused the phase 2 adapter work (sprint 2026-03-09) to address findings from an
architecture review of the non-prototype codebase. The review was conducted by
Opus 4.6 and documented in `docs/reviews/2026-03-10-Opus-46.md`.

---

## Review findings and resolutions

### Strengths identified (no action needed)

1. **Immutable spec / mutable runtime split** — `Task`, `TaskGraph`,
   `WorkstreamSpec` are frozen; `TaskRuntime`, `WorkstreamRuntime` are mutable
   envelopes. Clean data flow.

2. **TaskRunner state machine** — linear lifecycle with explicit transition table.
   Repetitive try/except around each IO call is correct.

3. **TaskGraph eager validation** — no invalid graph can exist. Cycle detection,
   hierarchy checks, dependency existence all enforced at construction.

4. **Clean protocol boundaries** — `TaskRunnerIO` and adapter protocols map to real
   operational boundaries.

### Concerns addressed

| # | Concern | Resolution | PR |
|---|---------|------------|----|
| 1 | Two parallel protocol layers (`TaskRunnerIO` vs `integration_contracts`) | Decomposed `TaskRunnerIO` into per-step protocols (`TaskPreparer`, `TaskLauncher`, etc.), added `WorkstreamRunner`/`WorkstreamRunnerIO`, deleted `integration_contracts/` | #78 |
| 2 | `Task.dependencies` stores `Task` objects, not IDs | Changed to `tuple[str, ...]`, removed redundant validation, simplified builder | #79 |
| 3 | `Agent` on `TaskRuntime` is an odd fit | Removed live `Agent` field, added `agent_address: AgentAddress` to `TaskArtifacts` as audit trail | #80 |
| 4 | Orchestrator does a lot of direct state mutation | Added read-only view protocols (part A), then added mutation methods to runtimes and replaced ~15 direct field assignments in orchestrator (part B) | #81, #82 |
| 5 | `integration_errors` elaborate but not consumed | Renamed to `errors/`, wired `classify_integration_error()` into `TaskRunner._record_io_failure()`, added `failure_class` to `TaskRunResult`, orchestrator now distinguishes internal vs expected failures | #83 |
| 6 | `RemoteWorkspaceRef` is speculative | Removed `RemoteWorkspaceRef` and `kind` discriminator from `LocalWorkspaceRef` | #84 |
| 7 | Workstream hierarchy depth — is it needed? | Kept as-is. The hierarchy validation and orchestrator ancestor-chain logic will be used when we create nested workstreams. No code change. | — |
| 8 | `_transition_to_failed` escape hatch | Removed silent fallback that bypassed transition table; method now delegates to `_transition()` unconditionally after idempotency check | #85 |
| 9 | No logging or observability hooks | Added `OrchestratorListener` protocol with `on_event()` callback; orchestrator accepts optional listener, notifies at all 6 event emission sites | #86 |

### Supporting PRs (pre-review, same sprint)

| PR | Description |
|----|-------------|
| #76 | PlantUML diagram infrastructure and conventions cleanup |
| #77 | Fix docs deploy: regenerate SVG instead of staleness check |

---

## Summary

- 9 review concerns addressed across PRs #78–#86
- Test count grew from ~600 to 624
- All changes backward-compatible (no public API removals that affect callers)
- Codebase is now ready to resume adapter/runner implementation work
