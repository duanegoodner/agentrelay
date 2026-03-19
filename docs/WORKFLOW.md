# Workflow

## Current Architecture Layer (`src/agentrelay/`)

Implemented workflow behavior in the current architecture:

1. Define immutable work with `Task` and `TaskGraph`.
2. Load graph YAML with `TaskGraphBuilder`.
3. Initialize runtime state with `TaskRuntimeBuilder` and `WorkstreamRuntimeBuilder`.
4. Execute one task lifecycle with `TaskRunner` (via `StandardTaskRunner` + `StepDispatch`).
5. Execute workstream lifecycle with `WorkstreamRunner` (via `StandardWorkstreamRunner`).
6. Schedule the graph with `Orchestrator` using dependency + workstream rules.
7. Run from the command line with `python -m agentrelay.run_graph <graph.yaml>`.

The `run_graph` module wires all components together: it loads the YAML, builds the
graph, constructs task and workstream runners via builder factories, creates the
orchestrator, and runs it. `--dry-run` validates the graph and prints the execution
plan without running.

## Prototype Reference

The v01 prototype remains as a reference implementation:

- [Prototype workflow description](prototypes/v01/WORKFLOW_DESCRIPTION.md)
- [Prototype operations guide](prototypes/v01/OPERATIONS.md)
