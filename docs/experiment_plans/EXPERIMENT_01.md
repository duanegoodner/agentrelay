# Experiment 1: Hand-authored Spec, Manual Execution

> **See also:** [`docs/PROJECT_PLAN.md`](../PROJECT_PLAN.md) — project overview and full experiment roadmap

---

## 1. Overview

**Goal:** Validate that the workflow vocabulary and YAML spec format are expressive
enough to describe a real (if trivial) multi-step workflow — before building any
tooling to execute it.

**What this experiment validates:**
- The YAML spec format is human-writable and unambiguous
- The five core abstractions (Task, Step, Gate, Signal, Reviewer) are sufficient to
  describe a two-step pipeline with a human gate between them
- The step prompts are clear enough that a Claude session can execute them without
  additional scaffolding

**What this experiment intentionally excludes:**
- No Python interpreter — there is no `agentrelay run` command yet
- No automated gate evaluation — you check the criteria yourself
- No signal detection — you create sentinel files by hand
- No state tracking — no `state.json` is written

The focus is entirely on the spec format and vocabulary. Code comes in Experiment 2.

---

## 2. The Trivial Task

The task for this experiment is: **implement an `add(a, b)` Python function, test-first.**

Per project convention, task content is kept trivial so focus stays on workflow
mechanics, not the work itself.

| Step | What the agent does |
|------|---------------------|
| `write-tests` | Write pytest tests for `add(a, b)` |
| `implement` | Implement `add()` to make all tests pass |

A single gate sits between the two steps. You (the human) evaluate it.

---

## 3. Workflow Design

```
[write-tests] → signal: write-tests.done → [gate-review-tests] → [implement] → signal: implement.done
```

- **`write-tests`** receives a prompt, produces `test_add.py`, announces completion
  via a sentinel file.
- **`gate-review-tests`** is evaluated by a human against explicit criteria. On pass,
  proceed. On fail, re-run `write-tests` with additional context (up to 2 retries).
- **`implement`** receives the test file as input, produces `add.py`, announces
  completion via a sentinel file. No gate follows — the task is done.

Signals are sentinel files (`touch`-ed by hand). Reviewer is `human` throughout.

---

## 4. Draft YAML Spec

**Location:** `.workflow/specs/exp-01.yaml`

```yaml
# .workflow/specs/exp-01.yaml
# Experiment 1: Hand-authored spec, manual execution
#
# Purpose: Validate that the workflow vocabulary and YAML spec format are
# expressive enough to describe a real (if trivial) multi-step workflow.
# Execution is fully manual — no Python interpreter, no automated gate logic.

workflow:
  id: exp-01
  name: "Experiment 1 — write-tests → implement"
  description: >
    Trivial 2-step workflow. Execute each step by launching Claude manually.
    Evaluate the gate yourself. Record vocabulary gaps in experiments/01-manual/NOTES.md.

task:
  id: add-function
  name: "Implement add(a, b) with tests"

  steps:

    - id: write-tests
      name: "Write pytest tests for add()"
      prompt: |
        Write pytest tests for a Python function `add(a, b)` that returns `a + b`.
        Save the tests to `experiments/01-manual/tests/test_add.py`.
        Cover at minimum: two positive integers, two negative integers, mixed signs,
        two floats, and one integer + one float.
        Do NOT implement `add()` — write tests only.
      outputs:
        - path: "experiments/01-manual/tests/test_add.py"
          description: "Pytest test file for add()"
      success_criterion: >
        test_add.py exists and contains at least 5 test cases covering the
        cases listed in the prompt. Tests do not define or import add().
      signal:
        type: sentinel_file
        path: ".workflow/signals/exp-01/write-tests.done"
      gate:
        id: gate-review-tests
        reviewer: human
        escalation: human
        criteria:
          - "test_add.py exists at experiments/01-manual/tests/test_add.py"
          - "At least 5 test cases are present"
          - "Cases cover: positive ints, negative ints, mixed signs, floats, int+float"
          - "add() is NOT defined or imported in test_add.py"
        on_fail:
          max_retries: 2
          retry_step: write-tests

    - id: implement
      name: "Implement add()"
      prompt: |
        Implement the Python function `add(a, b)` in `experiments/01-manual/src/add.py`.
        All tests in `experiments/01-manual/tests/test_add.py` must pass.
        Run `pixi run pytest experiments/01-manual/tests/` to verify before finishing.
      inputs:
        - path: "experiments/01-manual/tests/test_add.py"
          description: "Tests written in the write-tests step"
      outputs:
        - path: "experiments/01-manual/src/add.py"
          description: "Implementation of add()"
      success_criterion: >
        pixi run pytest experiments/01-manual/tests/ passes with zero failures.
      signal:
        type: sentinel_file
        path: ".workflow/signals/exp-01/implement.done"

  terminal_state:
    success: "Both steps completed; all gate criteria passed"
    failure: "max_retries exceeded on gate-review-tests"
```

**Schema notes:**
- The `gate:` block is a sub-key of the step it follows. It fires after the step's
  signal is detected and before the next step begins.
- The final step (`implement`) has no `gate:` — there is nothing to verify after the
  task completes.
- `depends_on` is omitted here (steps are strictly sequential). The field exists in
  the schema for future parallel-step support (Experiment 6).

---

## 5. File Layout

```
.workflow/
├── specs/
│   └── exp-01.yaml                  # Version-controlled spec (create this first)
└── signals/
    └── exp-01/                      # Gitignored — created manually during the run
        ├── write-tests.done
        └── implement.done

experiments/01-manual/
├── README.md                        # One-liner pointing to this document
├── NOTES.md                         # Vocabulary gaps and observations (fill in during run)
├── tests/
│   └── test_add.py                  # Output of step write-tests (created by Claude)
└── src/
    └── add.py                       # Output of step implement (created by Claude)
```

---

## 6. Manual Execution Procedure

### Before starting

```bash
# Ensure signal directory exists (gitignored, won't be in the repo)
mkdir -p .workflow/signals/exp-01

# Ensure experiment subdirs exist
mkdir -p experiments/01-manual/tests experiments/01-manual/src
```

### Step: `write-tests`

1. Open `.workflow/specs/exp-01.yaml` and read the `write-tests` step's `prompt:` field.
2. From `experiments/01-manual/`, launch Claude interactively:
   ```bash
   claude
   ```
3. Paste the prompt text into the Claude session (or type equivalent instructions).
4. Claude produces `experiments/01-manual/tests/test_add.py`.
5. Evaluate the gate (see checklist below).
6. **If gate passes:**
   ```bash
   touch .workflow/signals/exp-01/write-tests.done
   ```
7. **If gate fails:** note the gap in `NOTES.md`, provide feedback to Claude, and
   re-run (up to `max_retries: 2`). If still failing after 2 retries, note in
   `NOTES.md` whether the spec criteria or the prompt need adjustment.

### Gate evaluation checklist: `gate-review-tests`

Read `experiments/01-manual/tests/test_add.py` and check:

- [ ] File exists at `experiments/01-manual/tests/test_add.py`
- [ ] At least 5 test cases are present
- [ ] Cases cover: two positive ints, two negative ints, mixed signs, two floats, int+float
- [ ] `add()` is NOT defined or imported in `test_add.py`

All four must pass. If any fail, provide the failing criteria as feedback and retry
the `write-tests` step.

### Step: `implement`

1. Open `.workflow/specs/exp-01.yaml` and read the `implement` step's `prompt:` field.
2. From `experiments/01-manual/`, launch Claude interactively:
   ```bash
   claude
   ```
3. Paste the prompt text into the Claude session.
4. Claude produces `experiments/01-manual/src/add.py`.
5. Run the tests to verify:
   ```bash
   pixi run pytest experiments/01-manual/tests/
   ```
6. **If all tests pass:**
   ```bash
   touch .workflow/signals/exp-01/implement.done
   ```
7. **If tests fail:** paste the pytest output back into the Claude session as retry
   context and ask it to fix the implementation.

---

## 7. What to Record in `NOTES.md`

Fill in `experiments/01-manual/NOTES.md` during and after the run. Template:

```markdown
# Experiment 1 — Notes

## Vocabulary gaps
<!-- Concepts the spec couldn't express cleanly -->
-

## Schema ambiguities
<!-- Fields whose meaning was unclear when writing by hand -->
-

## Prompt design observations
<!-- What worked / didn't work in the step prompts -->
-

## Signal / sentinel-file observations
<!-- Was the pattern intuitive? Any timing issues? -->
-

## Gate criteria observations
<!-- Were the criteria clear enough to evaluate unambiguously? -->
-

## Open questions for Experiment 2
<!-- Anything discovered here that affects the Python interpreter design -->
-
```

---

## 8. Success Criteria

The experiment is complete when all of the following are true:

- [ ] `.workflow/specs/exp-01.yaml` is committed and passes a basic YAML parse check:
  ```bash
  python -c "import yaml; yaml.safe_load(open('.workflow/specs/exp-01.yaml')); print('OK')"
  ```
- [ ] `experiments/01-manual/tests/test_add.py` was produced by a Claude session
- [ ] `experiments/01-manual/src/add.py` was produced by a Claude session
- [ ] All tests pass: `pixi run pytest experiments/01-manual/tests/`
- [ ] `experiments/01-manual/NOTES.md` has all six sections filled in (even if some
  are "nothing notable")
- [ ] Sentinel files exist confirming both steps ran:
  - `.workflow/signals/exp-01/write-tests.done`
  - `.workflow/signals/exp-01/implement.done`
