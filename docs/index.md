# agentrelay

Documentation for the current architecture and the v01 prototype.

## Current Scope

Implemented today:

- Core architecture types in `src/agentrelay/` (`Task`, `TaskRuntime`, `Agent`, `AgentEnvironment`)
- A runnable prototype orchestrator in `src/agentrelay/prototypes/v01/`
- Test coverage for both layers (`467` tests collected)

Not implemented yet in the current architecture layer:

- A production orchestrator loop
- Non-stub `TmuxAgent.from_config()` and `TmuxAgent.send_kickoff()`

## Quick Links

- **[Architecture](ARCHITECTURE.md)** - Current module boundaries and design
- **[Workflow](WORKFLOW.md)** - What workflow behavior is implemented today
- **[Guide](GUIDE.md)** - Setup and common development/prototype commands
- **[Prototype v01](prototypes/v01/index.md)** - Historical/runnable prototype docs
- **[API Reference](api/task.md)** - Auto-generated from code
- **[Changelog](HISTORY.md)** - Main project history
- **[Backlog](BACKLOG.md)** - Near-term work items
