# Design Diagram

This diagram is a first-class project artifact. It shows all currently implemented
types and their relationships, organized by source module.

The authoritative source is `docs/diagrams/uml/diagram-detailed.d2` (D2 with TALA layout
engine). Every PR that touches `src/agentrelay/` must update the diagram to reflect any
new or changed types and relationships, then re-render via `pixi run diagram`.

## Views

**Module overview** — inter-module dependency graph. One box per module, arrows
showing which modules depend on which.

[View module overview (SVG)](diagrams/uml/diagram-modules.svg){: target="_blank" } — opens in a new tab with native browser pan/zoom (Ctrl+scroll).

**Per-module diagrams** — each module gets a focused diagram showing its full
types plus simplified stubs for external dependencies. Located in
`diagrams/uml/modules/diagram-{module-name}.svg`. These are the primary
reference for understanding individual modules.

Per-module diagrams are auto-generated from `diagram-detailed.d2` by
`tools/generate_module_diagrams.py`. External dependency stubs are shown at
reduced opacity with only the types that have relationships with the focus
module.

**Detailed** — everything in one diagram: all types, all relationships, all
modules. Use this for cross-cutting analysis or when you need to see the full
picture.

[View detailed diagram (SVG)](diagrams/uml/diagram-detailed.svg){: target="_blank" } — opens in a new tab with native browser pan/zoom (Ctrl+scroll).

## Conventions

**Connector lines** represent relationships that are not already obvious from the
class body or visual proximity. Guidelines:

- **Always add connectors** for composition/ownership and inheritance/implementation.
- **Omit connectors** when return types reference types that are already visually
  adjacent and connected via other relationships.
- When in doubt, prefer fewer connectors — the diagram should highlight structural
  relationships, not restate every type signature.
