# Roles Tests

Tests for role-specific templates and multi-role pipeline handoff. Validates
that spec_writer, test_writer, test_reviewer, and implementer roles produce
expected artifacts and propagate work through the dependency chain.

## Graphs

| Graph | What it tests |
|---|---|
| `pipeline.yaml` | Four-role pipeline (spec_writer -> test_writer -> test_reviewer -> implementer) building a BoundedQueue class. Includes a deliberate spec inconsistency to test organic concern discovery. |

## Running

```bash
pixi run e2e graphs/roles/pipeline.yaml /path/to/target-repo -v
pixi run e2e-reset graphs/roles/pipeline.yaml /path/to/target-repo
```

## What to verify

- spec_writer creates `src/agentrelaydemos/bounded_queue.py` (stubs with
  docstrings, bodies raise NotImplementedError) and `specs/bounded_queue.md`
- test_writer creates `tests/test_bounded_queue.py` with tests that collect
- test_reviewer completes review (may signal concerns or pass)
- implementer replaces stubs with working code; tests pass via completion gate
- Integration PR on GitHub lists all four tasks with PR URLs

### Organic concern test

The spec_writer's description contains a deliberate contradiction: the "Core
operations" section says `push()` evicts the oldest item when full, while the
"Error handling" section says `push()` raises `OverflowError` when full. The
implementer should discover this when tests conflict and record it via
`helper.record_concern()`.

To experiment with different models, edit the `model` field in `pipeline.yaml`
(or use `--model` on the CLI) and re-run. Document results below.

## Experimental results

| Model | Concern guidance | Concern recorded? | Notes |
|---|---|---|---|
| | | | |
