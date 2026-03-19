# Workflow

## Architecture Layers

1. Define immutable work with `Task` and `TaskGraph`.
2. Load graph YAML with `TaskGraphBuilder`.
3. Initialize runtime state with `TaskRuntimeBuilder` and `WorkstreamRuntimeBuilder`.
4. Execute one task lifecycle with `TaskRunner` (via `StandardTaskRunner` + `StepDispatch`).
5. Execute workstream lifecycle with `WorkstreamRunner` (via `StandardWorkstreamRunner`).
6. Schedule the graph with `Orchestrator` using dependency + workstream rules.
7. Run from the command line with `python -m agentrelay.run_graph <graph.yaml>`.

The `run_graph` module wires all components together: it loads the YAML, builds the
graph, constructs task and workstream runners via builder factories, creates the
orchestrator, and runs it.

## Practical Usage: Run/Reset Cycle

### 1. Validate the graph

```bash
python -m agentrelay.run_graph graphs/quick_chained.yaml --dry-run
```

Output shows graph name, task count, workstream structure, execution order,
and any conflicts with leftover state from previous runs.

### 2. Run the graph

From the target repository directory:

```bash
python -m agentrelay.run_graph /path/to/graphs/quick_chained.yaml
```

What happens:
- `run_info.json` is written to `.workflow/<graph>/` (records start HEAD for reset).
- A workstream worktree is created at `.worktrees/<graph>/<workstream_id>/`.
- Each task gets a branch, a tmux pane with Claude Code, and a signal directory.
- The orchestrator polls `.workflow/<graph>/signals/<task_id>/` for `.done` or `.failed`.
- On success, the task PR is merged into the integration branch.
- After all tasks complete, the workstream integration branch is merged to main.

### 3. Inspect the result

```
.workflow/<graph>/
  run_info.json              # start HEAD + timestamp
  signals/<task_id>/
    manifest.json            # task facts (Layer 1)
    policies.json            # workflow config (Layer 3)
    instructions.md          # resolved agent instructions (Layer 2)
    .done / .failed          # completion signal (written by agent)
    .merged                  # merge confirmation (written by orchestrator)
    agent.log                # tmux scrollback capture
```

### 4. Reset

```bash
python -m agentrelay.reset_graph /path/to/graphs/quick_chained.yaml --yes
```

This reverses the run: closes open PRs, resets main to the starting HEAD
(with ancestry safety check), deletes graph branches, and removes
`.workflow/<graph>/` and `.worktrees/<graph>/`.

### 5. Iterate

The run/reset cycle is designed to be repeatable. After a reset, the target
repo is back to its pre-run state and ready for another run.

## E2E Testing Workflow

For testing from the agentrelay repo against an external target:

```bash
pixi run e2e-check /path/to/target         # preflight validation
pixi run e2e graphs/quick_parallel.yaml /path/to/target   # run
pixi run e2e-reset graphs/quick_parallel.yaml /path/to/target  # reset
```

## Prototype Reference

The v01 prototype remains as a reference implementation:

- [Prototype workflow description](prototypes/v01/WORKFLOW_DESCRIPTION.md)
- [Prototype operations guide](prototypes/v01/OPERATIONS.md)
