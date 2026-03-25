# ADR Tests

Validate that Architecture Decision Record (ADR) instructions are injected into
agent instructions when `adr_verbosity` is set, and that agents produce ADR files.

## Graphs

| Graph | Scenario | What it tests |
|---|---|---|
| `adr_standard.yaml` | Standard verbosity ADR | ADR section in instructions, agent creates `docs/adr/<task_id>.md` |

## Running

```bash
# Preflight check
pixi run e2e-check /path/to/target-repo

# Run
pixi run e2e graphs/adr/adr_standard.yaml /path/to/target-repo

# Reset
pixi run e2e-reset graphs/adr/adr_standard.yaml /path/to/target-repo
```

## What to verify after a run

### adr_standard

- `instructions.md` in the signal directory contains `## Architecture Decision Record`
- ADR section mentions `docs/adr/impl_with_adr.md`
- ADR section lists five expected sections (Title, Status, Context, Decision, Consequences)
- Agent's PR includes a `docs/adr/impl_with_adr.md` file
- Task reaches `PR_MERGED` status
