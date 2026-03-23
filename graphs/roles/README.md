# Roles Tests

Tests for role-specific templates and multi-role pipeline handoff. Validates
that spec_writer, test_writer, test_reviewer, and implementer roles produce
expected artifacts and propagate work through the dependency chain.

## Graphs

### Pipeline (full handoff chain)

| Graph | What it tests |
|---|---|
| `pipeline.yaml` | Four-role pipeline (spec_writer -> test_writer -> test_reviewer -> implementer) building a BoundedQueue class. Includes a deliberate spec inconsistency to test organic concern discovery. |

```bash
pixi run e2e graphs/roles/pipeline.yaml /path/to/target-repo -v
pixi run e2e-reset graphs/roles/pipeline.yaml /path/to/target-repo
```

### Concern experiments (single-role, controlled inputs)

Each experiment isolates one role with synthetic BoundedQueue inputs containing a
deliberate contradiction (push() docstring says eviction, Raises section says
OverflowError). All experiments use the same file paths; reset between runs.

| Graph | Role | Setup mode | What the agent sees |
|---|---|---|---|
| `experiments/concern_spec_writer.yaml` | spec_writer | none | Task description with contradiction |
| `experiments/concern_test_writer.yaml` | test_writer | `stubs` | Pre-committed stubs with contradictory docstrings |
| `experiments/concern_test_reviewer.yaml` | test_reviewer | `all` | Pre-committed stubs + tests with mismatched behavior |
| `experiments/concern_implementer.yaml` | implementer | `all` | Pre-committed stubs + tests with mismatched behavior |

**Setup** (before each experiment that needs fixtures):
```bash
graphs/roles/fixtures/setup_fixtures.sh <stubs|all> /path/to/target-repo
```

**Running**:
```bash
pixi run e2e graphs/roles/experiments/concern_<role>.yaml /path/to/target-repo -v
# Check: .workflow/<graph>/signals/<task-id>/concerns.log
```

**Between experiments** (reset graph run + undo fixture commit):
```bash
pixi run e2e-reset graphs/roles/experiments/concern_<role>.yaml /path/to/target-repo
git -C /path/to/target-repo reset --hard HEAD~1   # undo fixture commit
```

For spec_writer: just `e2e-reset` (no fixture commit to undo).

## What to verify

### Pipeline
- spec_writer creates `src/agentrelaydemos/bounded_queue.py` (stubs with
  docstrings, bodies raise NotImplementedError) and `specs/bounded_queue.md`
- test_writer creates `tests/test_bounded_queue.py` with tests that collect
- test_reviewer completes review (may signal concerns or pass)
- implementer replaces stubs with working code; tests pass via completion gate
- Integration PR on GitHub lists all four tasks with PR URLs

### Concern experiments
- Agent completes the task successfully
- Agent records at least one design concern about the contradiction
- Concern appears in `concerns.log` in the signal directory
- Concern appears in console output

## Experimental results

### Concern refinement matrix

| Model | Role | Concern recorded? | What was recorded | Notes |
|---|---|---|---|---|
| | | | | |
