# Experiment 1 — Notes

> Fill in each section during and after the experiment run.
> See `docs/experiment_plans/EXPERIMENT_01.md` §7 for guidance on what to record.

## Vocabulary gaps

- The spec has no way to express that a step's output must be importable by a test runner.
  The `implement` step outputs `src/add.py`, but the test file uses a bare `from add import add`,
  which requires `src/` to be on `sys.path`. This relationship between the output location and
  the test runner's import path is not captured anywhere in the spec. A `conftest.py` was needed
  as a manual fix outside the spec's scope.
- No vocabulary for expressing the *working directory* or *Python path* in which a step's
  success criterion is evaluated. The spec says `pixi run pytest experiments/01-manual/tests/`
  but doesn't specify the rootdir or path configuration pytest needs.

## Schema ambiguities

- The `signal:` block lives inside the step that produces it, which is natural. But the
  `gate:` block also lives inside the same step — it's ambiguous whether the gate is a
  property of the step that precedes it or the step that follows it. Conceptually it sits
  *between* steps, but the schema attaches it to the preceding step. This is fine but worth
  documenting as a deliberate choice.
- `on_fail.retry_step` names a step by ID, but the spec doesn't formally define step IDs as
  referenceable anchors. When reading by hand, the reference is clear; a parser would need
  to validate that the named step ID exists in the same task.
- `terminal_state.failure` describes a condition as prose but there is no machine-readable
  way to detect it from the spec alone (e.g., no field linking it to `on_fail.max_retries`).

## Prompt design observations

- The `write-tests` prompt was specific enough that the output needed no revisions — all
  five required cases were covered on the first attempt and `add()` was not imported.
- The `implement` prompt worked cleanly. Giving the test file path explicitly and the verify
  command left no ambiguity about what "done" means.
- Including the exact file paths in the prompt (rather than relative paths) was important.
  Ambiguity about working directory could easily produce output in the wrong location.
- The prompts could benefit from a `context:` field alongside `prompt:` — a place for
  background information that is not part of the instruction but helps the agent understand
  the task (e.g., "this is step 2 of 2; the previous step produced the test file you are
  about to implement against").

## Import path / stub observations

- **conftest.py as an experiment knob:** The `tests/conftest.py` that inserts `src/` into
  `sys.path` is intentional here, but not how a real Python project would normally handle
  importability (which would typically use an editable install, a `pythonpath` pytest config,
  or proper package structure). Its value in this project is as a controllable variable:
  pre-creating conftest.py tests the "imports already work" code path; omitting it lets future
  experiments test the "agent must establish importability" code path.
- The write-tests step creates both the test file AND a minimal stub (`def add(a, b): pass`)
  so that imports resolve before the implement step runs. This is TDD-aligned: tests can be
  collected and will fail predictably (stub returns None), rather than failing at import time.
- The gate criterion `pixi run pytest --collect-only` is language-agnostic in intent: the
  equivalent for other languages would be a parse/resolve step that proves module visibility
  without executing any test logic.

## Signal / sentinel-file observations

- The sentinel-file pattern is intuitive for manual execution: `touch <path>` is obvious
  and easy to audit (`ls -la .workflow/signals/exp-01/`).
- The signal path convention (`.workflow/signals/<workflow-id>/<step-id>.done`) is readable
  and unambiguous. No naming conflicts observed.
- For automated execution (Experiment 2), the interpreter will need to either poll for the
  sentinel or use `inotifywait`. Polling interval choice will matter for responsiveness vs.
  CPU overhead.
- The signals directory is gitignored, which is correct — sentinel files are runtime state,
  not versioned artifacts. However, this means there is no persistent record that the
  experiment ran successfully. The audit log (planned for Experiment 4) is the right answer.

## Gate criteria observations

- All four gate criteria for `gate-review-tests` were unambiguous and evaluatable by
  reading the file: existence, count, case coverage, and absence of `add()`.
- The case-coverage criterion ("covers: positive ints, negative ints, mixed signs, floats,
  int+float") maps cleanly to the test file contents. No interpretation was required.
- Human evaluation of a gate takes ~30 seconds for a trivial check like this. For larger
  outputs the criteria would need to be more surgical to keep review time reasonable.
- The `escalation: human` field on the gate is redundant when `reviewer: human` — if the
  reviewer is already human, there is nowhere to escalate. This field makes more sense when
  the reviewer is `auto` and escalation to `human` is a fallback. The schema should clarify
  this (or make `escalation` optional when `reviewer: human`).

## Open questions for Experiment 2

- How should the interpreter invoke Claude headlessly? `claude -p "<prompt>"` is the
  documented flag for non-interactive use. Need to confirm the flag name and behavior for
  the current Claude CLI version before Experiment 2.
- The `pixi run pytest` command in the success criterion assumes a pixi task named `pytest`
  exists. The current `pyproject.toml` has an empty `[tool.pixi.tasks]` section, so the
  correct invocation is `pixi run python -m pytest`. The spec and the actual command are
  out of sync — decide which to fix.
- Signal detection: poll vs. `inotifywait`. Should the interpreter have a configurable
  poll interval, or always use `inotifywait` when available?
- Should the interpreter write `state.json` after each step completes, or only on
  gate/failure transitions? Affects how restartable a workflow is after an interruption.
- The conftest.py needed here is not mentioned in the spec. In Experiment 2 the interpreter
  will need to understand how to set up the test environment, or the spec will need a
  `test_setup:` field to express it.
