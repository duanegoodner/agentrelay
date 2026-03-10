# agentrelay

`agentrelay` is a Python orchestration system for multi-agent coding workflows.
It models work as a dependency graph of tasks and coordinates execution through
observable artifacts (git branches/worktrees and filesystem signals).

## Project Direction

The project is evolving from a working prototype that implemented a specific
workflow (Claude Code agents running in tmux) toward a pluggable architecture.
Current development is focused on making orchestration easier to extend to
additional coding-agent frameworks and cloud execution environments.

## Current Scope

Implemented today:

- Core architecture types in `src/agentrelay/` (`TaskGraph`, `TaskGraphBuilder`, `TaskRuntimeBuilder`, `WorkstreamRuntimeBuilder`, `TaskRunner`, `Orchestrator`, `WorkstreamSpec`, `Task`, `TaskRuntime`, `WorkstreamRuntime`, `Agent`, `AgentEnvironment`)
- A runnable prototype orchestrator in `src/agentrelay/prototypes/v01/`
- Test coverage for both layers (`516` tests collected)

Not implemented yet in the current architecture layer:

- Non-stub `TmuxAgent.from_config()` and `TmuxAgent.send_kickoff()`

## Quick Links

- **[Architecture](ARCHITECTURE.md)** - Core abstractions and design intent
- **[Workflow](WORKFLOW.md)** - What workflow behavior is implemented today
- **[Guide](GUIDE.md)** - Setup and common development/prototype commands
- **[Testing](TESTING.md)** - Test scope and validation commands
- **[Prototype v01](prototypes/v01/index.md)** - Historical/runnable prototype docs
- **[API Reference](api/index.md)** - Auto-generated from code
- **[Changelog](HISTORY.md)** - Main project history
- **[Backlog](BACKLOG.md)** - Near-term work items
