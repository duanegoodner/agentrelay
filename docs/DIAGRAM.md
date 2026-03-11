# Design Diagram

This diagram is a first-class project artifact. It shows all currently implemented
types and their relationships, organized by source module. Archive types are excluded.

The authoritative source is `docs/diagram.puml` (PlantUML). Every PR that touches
`src/agentrelay/` must update the diagram to reflect any new or changed types and
relationships, then re-render `docs/diagram.svg` via `pixi run diagram`.

[View full diagram (SVG)](diagram.svg){: target="_blank" } — opens in a new tab with native browser pan/zoom (Ctrl+scroll).

## Conventions

**Connector lines** represent relationships that are not already obvious from the
class body or visual proximity. Guidelines:

- **Always add connectors** for composition/ownership (e.g. `TaskRuntime --> TaskState : state`)
  and inheritance/implementation (e.g. `TaskState ..|> TaskStateView : satisfies`).
- **Omit connectors** when a Protocol's property return types reference other protocols
  or types that are already visually adjacent and connected via other relationships.
  For example, `TaskRuntimeView` has properties returning `TaskStateView` and
  `TaskArtifactsView`, but connectors for these are omitted because the "satisfies"
  arrows from the concrete dataclasses already establish the grouping, and the return
  types are readable in the protocol's class body.
- When in doubt, prefer fewer connectors — the diagram should highlight structural
  relationships, not restate every type signature.
