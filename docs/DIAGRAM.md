# Design Diagram

This diagram is a first-class project artifact. It shows all currently implemented
types and their relationships, organized by source module.

The authoritative source is `docs/diagrams/uml/diagram-detailed.d2` (D2 format).
Per-module diagrams and the module overview are auto-generated from this source
and rendered with the ELK layout engine (bundled with D2). Every PR that touches
`src/agentrelay/` must update the diagram to reflect any new or changed types
and relationships, then re-render via `pixi run diagram`.

## Views

**Module overview** — inter-module dependency graph. One box per module, arrows
showing which modules depend on which. This is the best starting point for
understanding the architecture.

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
| reset_ops.py | [diagram-reset-ops.svg](diagrams/uml/modules/diagram-reset-ops.svg){: target="_blank" } |
| reset_pr.py | [diagram-reset-pr.svg](diagrams/uml/modules/diagram-reset-pr.svg){: target="_blank" } |
| reset_repo.py | [diagram-reset-repo.svg](diagrams/uml/modules/diagram-reset-repo.svg){: target="_blank" } |
| reset_task.py | [diagram-reset-task.svg](diagrams/uml/modules/diagram-reset-task.svg){: target="_blank" } |
| reset_to.py | [diagram-reset-to.svg](diagrams/uml/modules/diagram-reset-to.svg){: target="_blank" } |
| reset_workstream.py | [diagram-reset-workstream.svg](diagrams/uml/modules/diagram-reset-workstream.svg){: target="_blank" } |
| run_graph.py | [diagram-run-graph.svg](diagrams/uml/modules/diagram-run-graph.svg){: target="_blank" } |
| run_repo.py | [diagram-run-repo.svg](diagrams/uml/modules/diagram-run-repo.svg){: target="_blank" } |
| sandbox/ | [diagram-sandbox.svg](diagrams/uml/modules/diagram-sandbox.svg){: target="_blank" } |
| session.py | [diagram-session.svg](diagrams/uml/modules/diagram-session.svg){: target="_blank" } |
| task.py | [diagram-task.svg](diagrams/uml/modules/diagram-task.svg){: target="_blank" } |
| task_graph/ | [diagram-task-graph.svg](diagrams/uml/modules/diagram-task-graph.svg){: target="_blank" } |
| task_runner/ | [diagram-task-runner.svg](diagrams/uml/modules/diagram-task-runner.svg){: target="_blank" } |
| task_runtime/ | [diagram-task-runtime.svg](diagrams/uml/modules/diagram-task-runtime.svg){: target="_blank" } |
| tools.py | [diagram-tools.svg](diagrams/uml/modules/diagram-tools.svg){: target="_blank" } |
| workstream/ | [diagram-workstream.svg](diagrams/uml/modules/diagram-workstream.svg){: target="_blank" } |

## Conventions

**Connector lines** represent relationships that are not already obvious from the
class body or visual proximity. Guidelines:

- **Always add connectors** for composition/ownership and inheritance/implementation.
- **Omit connectors** when return types reference types that are already visually
  adjacent and connected via other relationships.
- When in doubt, prefer fewer connectors — the diagram should highlight structural
  relationships, not restate every type signature.
