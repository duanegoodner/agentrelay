# Design Diagram

This diagram is a first-class project artifact. It shows all currently implemented
types and their relationships, organized by source module. Archive types are excluded.

The authoritative source is `docs/diagram.puml` (PlantUML). Every PR that touches
`src/agentrelay/` must update the diagram to reflect any new or changed types and
relationships, then re-render `docs/diagram.svg` via `pixi run diagram`.

[View full diagram (SVG)](diagram.svg){: target="_blank" } — opens in a new tab with native browser pan/zoom (Ctrl+scroll).
