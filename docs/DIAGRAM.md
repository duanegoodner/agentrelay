# Design Diagram

This diagram is a first-class project artifact. It shows all currently implemented
types and their relationships, organized by source module.

The authoritative source is `docs/diagrams/uml/diagram-detailed.d2` (D2 with TALA layout
engine). Every PR that touches `src/agentrelay/` must update the diagram to reflect any
new or changed types and relationships, then re-render via `pixi run diagram`.

## Views

**Standard** — public API types with collapsed `implementations/` packages. This is
the default view for understanding the architecture.

[View standard diagram (SVG)](diagrams/uml/diagram-standard.svg){: target="_blank" } — opens in a new tab with native browser pan/zoom (Ctrl+scroll).

**Detailed** — everything: private types, implementation classes, and all relationships.
Use this for deep dives into specific packages.

[View detailed diagram (SVG)](diagrams/uml/diagram-detailed.svg){: target="_blank" } — opens in a new tab with native browser pan/zoom (Ctrl+scroll).

Two intermediate variants are also generated for reference:

- `diagrams/uml/diagram-no-private.svg` — public types with full implementation detail
- `diagrams/uml/diagram-no-impl.svg` — all types with collapsed implementations

## Filtering conventions

Diagram variants are auto-generated from `diagrams/uml/diagram-detailed.d2` by `tools/generate_diagrams.py`
using composable filters from `tools/d2_filters.py`:

- **Private filter**: strips nodes whose D2 identifier starts with `_` (matching the
  Python private naming convention) and any relationship arrows referencing them.
- **Impl filter**: collapses `*_impl_pkg` containers to a `"(N classes hidden)"`
  placeholder and strips relationship arrows referencing nodes inside them.

## Conventions

**Connector lines** represent relationships that are not already obvious from the
class body or visual proximity. Guidelines:

- **Always add connectors** for composition/ownership and inheritance/implementation.
- **Omit connectors** when return types reference types that are already visually
  adjacent and connected via other relationships.
- When in doubt, prefer fewer connectors — the diagram should highlight structural
  relationships, not restate every type signature.
