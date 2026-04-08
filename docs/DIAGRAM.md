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

| Module | Diagram |
|---|---|
| agent/ | [diagram-agent.svg](diagrams/uml/modules/diagram-agent.svg){: target="_blank" } |
| agent_comm_protocol/ | [diagram-agent-comm-protocol.svg](diagrams/uml/modules/diagram-agent-comm-protocol.svg){: target="_blank" } |
| agent_sdk/ | [diagram-agent-sdk.svg](diagrams/uml/modules/diagram-agent-sdk.svg){: target="_blank" } |
| environments.py | [diagram-environments.svg](diagrams/uml/modules/diagram-environments.svg){: target="_blank" } |
| errors/ | [diagram-errors.svg](diagrams/uml/modules/diagram-errors.svg){: target="_blank" } |
| graph_index.py | [diagram-graph-index.svg](diagrams/uml/modules/diagram-graph-index.svg){: target="_blank" } |
| ops/ | [diagram-ops.svg](diagrams/uml/modules/diagram-ops.svg){: target="_blank" } |
| orchestrator/ | [diagram-orchestrator.svg](diagrams/uml/modules/diagram-orchestrator.svg){: target="_blank" } |
| output/ | [diagram-output.svg](diagrams/uml/modules/diagram-output.svg){: target="_blank" } |
| reset_graph.py | [diagram-reset-graph.svg](diagrams/uml/modules/diagram-reset-graph.svg){: target="_blank" } |
| run_graph.py | [diagram-run-graph.svg](diagrams/uml/modules/diagram-run-graph.svg){: target="_blank" } |
| sandbox/ | [diagram-sandbox.svg](diagrams/uml/modules/diagram-sandbox.svg){: target="_blank" } |
| task.py | [diagram-task.svg](diagrams/uml/modules/diagram-task.svg){: target="_blank" } |
| task_graph/ | [diagram-task-graph.svg](diagrams/uml/modules/diagram-task-graph.svg){: target="_blank" } |
| task_runner/ | [diagram-task-runner.svg](diagrams/uml/modules/diagram-task-runner.svg){: target="_blank" } |
| task_runtime/ | [diagram-task-runtime.svg](diagrams/uml/modules/diagram-task-runtime.svg){: target="_blank" } |
| tools.py | [diagram-tools.svg](diagrams/uml/modules/diagram-tools.svg){: target="_blank" } |
| workstream/ | [diagram-workstream.svg](diagrams/uml/modules/diagram-workstream.svg){: target="_blank" } |

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
