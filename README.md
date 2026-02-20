# agentrelay

A lightweight, declarative workflow framework for describing and executing multi-agent Claude Code task pipelines.

## Status

**Planning complete — implementation not yet started.** Project structure, core vocabulary (Tasks, Steps, Gates, Signals, Reviewers), and a detailed experiment roadmap are in place. No functional code has been written yet. See `docs/PROJECT_PLAN.md` for the full plan.

This is an exploratory project studying multi-agent coordination patterns — the mechanics of how coding agents hand off work, verify results, and recover from failures. It is not production software.

## Planned capabilities

agentrelay will provide a vocabulary and YAML-based spec format for defining workflows where multiple Claude Code agents collaborate through a sequence of **Steps** connected by **Gates** (verification checkpoints). Planned features:

- Declarative pipeline definitions (YAML specs)
- Configurable gate evaluation with escalation levels (automated, notify, human)
- Retry context accumulation across failed attempts
- Sentinel-file signaling between agents
- Workflow state tracking and audit logging

## Project structure

```
src/agentrelay/     Python package (the orchestrator framework)
tests/              pytest tests for the framework
experiments/        Incremental experiments (01-manual through 07-agent-orchestrator)
.workflow/specs/    YAML workflow definitions
docs/               Planning and design documents
```

## Development setup

Requires [pixi](https://pixi.sh):

```bash
pixi install
pixi run pytest
```

## Documentation

See `docs/` for detailed planning and design documents:

- `PROJECT_PLAN.md` — project plan, vocabulary, and experiment roadmap
- `AGENT_WORKFLOWS_KNOWLEDGE_CAPTURE.md` — background research on multi-agent patterns
- `WORKFLOW_ORCHESTRATION_PROJECT_PLAN.md` — original project proposal

## License

Not yet specified.
