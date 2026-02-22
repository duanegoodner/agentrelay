# Experiment 1b: Two-Tier Execution — Claude Code Plans, Copilot Executes

> **See also:**
> - [`docs/experiment_plans/EXPERIMENT_01.md`](EXPERIMENT_01.md) — baseline run (Claude Code for both steps)
> - [`docs/discussions/multi-agent-workflow-insights.md`](../discussions/multi-agent-workflow-insights.md) — motivation for this run
> - [`docs/PROJECT_PLAN.md`](../PROJECT_PLAN.md) — project overview and full experiment roadmap

---

## 1. Overview

**Goal:** Test the two-tier model — Claude Code as planner/architect, VS Code Copilot as
executor — using the same trivial `add(a, b)` workflow from Experiment 1.

The primary question is not "does the task complete successfully?" (it should — the task
is trivial). The question is: **does the structured plan-file handoff between tools work
in practice, and what does that reveal about what the runner abstraction needs to support?**

**What this experiment validates:**
- A plan packet (structured `.md` in the repo) is a sufficient handoff artifact between
  a planning agent and an executing agent
- VS Code Copilot can follow a step-level plan reliably without additional scaffolding
- The gate criteria from exp-01.yaml are sufficient to evaluate Copilot's output
- The 7 observation categories below are useful for comparing tool configurations

**What this experiment intentionally excludes:**
Same as Experiment 1 — no Python interpreter, no automated gate evaluation, no signal
detection, no state tracking. The only difference is the execution tool for each step.

**Configuration:**

| Role | Tool | Notes |
|------|------|-------|
| Planner | Claude Code (terminal) | Reads spec, produces plan packet |
| Executor | VS Code Copilot | Follows plan packet for each step |
| Gate reviewer | Human | Same as Experiment 1 |

---

## 2. Task, Workflow Design, and YAML Spec

Same as Experiment 1. See [EXPERIMENT_01.md §2–4](EXPERIMENT_01.md#2-the-trivial-task).

The spec file is `.workflow/specs/exp-01.yaml` — unchanged.

---

## 5. File Layout

Same as Experiment 1, plus one new directory for the plan packet:

```
experiments/01-manual/
├── NOTES.md                         # Experiment 1 observations (already filled in)
├── NOTES-1b.md                      # Experiment 1b observations (fill in during this run)
├── plan-packets/
│   └── exp-01-1b.md                 # Plan packet produced by Claude Code (new)
├── tests/
│   ├── conftest.py                  # May be overwritten by Copilot
│   └── test_add.py                  # May be overwritten by Copilot
└── src/
    └── add.py                       # May be overwritten by Copilot
```

The output files (`test_add.py`, `add.py`, `conftest.py`) already exist from the 1a run.
You may optionally delete them before starting to observe Copilot producing them from
scratch, but it is not required — the gate criteria evaluate content, not provenance.

---

## 6. Execution Procedure

### Before starting

```bash
# Ensure signal directory exists (gitignored)
mkdir -p .workflow/signals/exp-01
mkdir -p experiments/01-manual/plan-packets
```

---

### Phase 1 — Planning: Claude Code produces the plan packet

The goal of this phase is to have Claude Code read the spec and produce a richer
handoff artifact than the bare step prompts, so Copilot has full context without
needing to interpret the YAML itself.

1. From the project root, launch Claude Code interactively:
   ```bash
   claude
   ```

2. Ask Claude to read the spec and produce a plan packet. Suggested prompt:

   > Read `.workflow/specs/exp-01.yaml`. For each step in the workflow, produce a
   > structured Plan Packet that an IDE coding agent (Copilot) can use to execute
   > the step without reading the spec directly. Format each plan packet as:
   >
   > - **Goal** (1–2 sentences)
   > - **Non-goals / do-not-touch** (explicit scope boundary)
   > - **Assumptions** (what is already true when the step runs)
   > - **Files to produce** (paths, descriptions)
   > - **Exact steps** (what to write/change)
   > - **Verification command** (how to confirm the step succeeded)
   >
   > Save the plan packet to `experiments/01-manual/plan-packets/exp-01-1b.md`.

3. Review the plan packet. Check that it is concrete enough for Copilot to follow
   without guessing — especially the file paths, the stub requirement, and the
   `--collect-only` verification for the write-tests step.

4. If the plan packet is too vague, ask Claude to add specificity before proceeding.
   Record any observations about what Claude chose to emphasize vs. omit.

---

### Phase 2 — Execution: Copilot runs each step

Open VS Code with the project root as the workspace.

#### Step: `write-tests`

1. Open the Copilot chat panel in VS Code.
2. Attach or reference `experiments/01-manual/plan-packets/exp-01-1b.md` so Copilot
   has the plan packet in context.
3. Give Copilot the write-tests instruction. Suggested prompt:

   > Using the plan packet in `experiments/01-manual/plan-packets/exp-01-1b.md`,
   > execute the `write-tests` step. Follow the plan exactly. Do not implement
   > `add()`. After producing all files, run the verification command and confirm
   > it exits 0, then report what was done.

4. Copilot should produce:
   - `experiments/01-manual/tests/test_add.py`
   - `experiments/01-manual/src/add.py` (stub only)
   - `experiments/01-manual/tests/conftest.py` (if needed)

5. Evaluate the gate — same checklist as Experiment 1:

   - [ ] `tests/test_add.py` exists at `experiments/01-manual/tests/test_add.py`
   - [ ] At least 5 test cases are present
   - [ ] Cases cover: positive ints, negative ints, mixed signs, two floats, int+float
   - [ ] `add()` is NOT implemented in `tests/test_add.py`
   - [ ] `src/add.py` exists as a stub (body is `pass` or equivalent)
   - [ ] Command criterion exits 0:
     ```bash
     pixi run pytest experiments/01-manual/tests/ --collect-only
     ```

6. **If gate passes:**
   ```bash
   touch .workflow/signals/exp-01/write-tests.done
   ```
7. **If gate fails:** provide the failing criteria back to Copilot and retry
   (up to `max_retries: 2` per the spec). Note the failure in `NOTES-1b.md`.

---

#### Step: `implement`

1. In the same Copilot chat session (preserving context) or a new one — note which
   you use, as it affects the "context sufficiency" observation.
2. Give Copilot the implement instruction. Suggested prompt:

   > Using the plan packet in `experiments/01-manual/plan-packets/exp-01-1b.md`,
   > execute the `implement` step. Replace the stub body with the real implementation.
   > Run the verification command and confirm all tests pass, then report what was done.

3. Copilot replaces the `pass` body in `experiments/01-manual/src/add.py`.

4. Verify:
   ```bash
   pixi run pytest experiments/01-manual/tests/
   ```

5. **If all tests pass:**
   ```bash
   touch .workflow/signals/exp-01/implement.done
   ```
6. **If tests fail:** paste the pytest output back into Copilot and ask for a fix.
   Note the failure in `NOTES-1b.md`.

---

## 7. What to Record in `NOTES-1b.md`

Fill in `experiments/01-manual/NOTES-1b.md` during and after the run.
The observations here focus on cross-tool handoff quality rather than spec vocabulary
(which was the focus of NOTES.md for Experiment 1).

```markdown
# Experiment 1b — Notes (Claude Code plans, Copilot executes)

## 1. Handoff friction
<!-- Did Copilot understand the step prompt/plan packet without additional context?
     Did you need to rephrase, restate, or add context beyond what the plan packet said? -->
-

## 2. Scope discipline
<!-- Did Copilot stay within the step's scope?
     Drive-by changes? Unsolicited refactors? Extra files created? -->
-

## 3. Gate evaluation
<!-- Were the gate criteria sufficient to evaluate Copilot's output?
     Anything the criteria missed, or that needed interpretation? -->
-

## 4. Transparency
<!-- Could you see what Copilot was doing?
     Commands shown in terminal? Files listed before/after? Diff visible? -->
-

## 5. Cost / request usage
<!-- Rough count: how many Copilot requests did each step take?
     How does this compare to the token cost feel of the 1a Claude Code run? -->
-

## 6. Context sufficiency
<!-- Did Copilot have enough context to complete the step?
     Did it need to read additional files beyond the plan packet?
     Did it correctly infer the project structure (pixi, src/, tests/)? -->
-

## 7. Plan packet format
<!-- Was the plan packet the right level of detail?
     Too abstract (Copilot filled in blanks incorrectly)?
     Too prescriptive (unnecessary for a trivial task)?
     What would you change for a more complex task? -->
-

## 8. Comparison to 1a (Claude Code for both steps)
<!-- Overall: was the cross-tool handoff smoother, rougher, or about the same
     as using Claude Code for both steps?
     Would you use this configuration again for a similar task? -->
-

## Open questions for future runs or Experiment 2
<!-- Anything discovered here that affects the runner abstraction design,
     the plan packet format, or the gate evaluation model -->
-
```

---

## 8. Success Criteria

The run is complete when all of the following are true:

- [ ] `experiments/01-manual/plan-packets/exp-01-1b.md` exists and was produced by Claude Code
- [ ] `experiments/01-manual/tests/test_add.py` was (re)produced by Copilot
- [ ] `experiments/01-manual/src/add.py` was (re)produced by Copilot
- [ ] Test collection passes:
  ```bash
  pixi run pytest experiments/01-manual/tests/ --collect-only
  ```
- [ ] All tests pass:
  ```bash
  pixi run pytest experiments/01-manual/tests/
  ```
- [ ] All six gate criteria for `gate-review-tests` were satisfied
- [ ] `experiments/01-manual/NOTES-1b.md` has all eight sections filled in
- [ ] Sentinel files exist (or were re-created):
  - `.workflow/signals/exp-01/write-tests.done`
  - `.workflow/signals/exp-01/implement.done`
