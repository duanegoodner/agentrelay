# agentrelay — Workflow Orchestration for Multi-Agent Claude Code Pipelines

## Context

While planning multi-agent workflows for the chatcat project, recurring coordination patterns emerged — units of work, handoffs, reviews, retries — that are domain-independent. This standalone project explores those patterns in isolation. The two seed documents (`AGENT_WORKFLOWS_KNOWLEDGE_CAPTURE.md` and `WORKFLOW_ORCHESTRATION_PROJECT_PLAN.md`) capture the original brainstorm and proposed plan. This plan refines that proposal with concrete next steps.

**Intended outcome:** A working prototype of a declarative workflow framework that can describe and execute multi-agent Claude Code pipelines, validated through a series of incremental experiments.

---

## Project Setup

### Current State

- `/data/git/agentrelay/main/` — regular git repo with remote `git@github.com:duanegoodner/agentrelay.git`
- One commit on main (`95d19ed initial commit`), contains `README.md`
- `docs/` directory exists but is untracked
- pixi 0.61.0 is installed

### Target Repository Structure

```
/data/git/agentrelay/
├── .git-bare/                         # bare repo — all git object data, remote origin
├── .claude/                           # Claude Code project-level settings
│   └── settings.local.json
├── main/                              # linked worktree on `main` branch
│   ├── .git                           # file (not dir) pointing to .git-bare/worktrees/main
│   ├── CLAUDE.md                      # root project context for all agents
│   ├── docs/                          # planning documents
│   ├── src/
│   │   └── agentrelay/                 # Python package — the orchestrator
│   ├── tests/                         # pytest tests for the framework itself
│   ├── experiments/                   # one subdirectory per experiment
│   ├── .workflow/                     # runtime state (created by the framework)
│   └── pyproject.toml                 # project config (pixi-managed)
└── <feature-worktrees>/               # created as needed for experiments
```

### Step 1: Commit and push current work

Ensure everything is on the remote before restructuring.

```bash
cd /data/git/agentrelay/main
git add docs/
git commit -m "add planning documents"
git push origin main
```

### Step 2: Convert to bare repo + worktree pattern

The idea: clone the remote as a bare repo, then set up `main/` as a linked worktree instead of a standalone clone.

```bash
cd /data/git/agentrelay

# 2a. Move the current main/ aside (we'll recreate it as a worktree)
mv main main-old

# 2b. Bare-clone the remote into .git-bare/
git clone --bare git@github.com:duanegoodner/agentrelay.git .git-bare

# 2c. Fix the fetch refspec.
#     A bare clone defaults to +refs/heads/*:refs/heads/*  which means
#     `git fetch` would overwrite local branch refs with remote ones.
#     We want the normal pattern where remote branches are tracked
#     separately under refs/remotes/origin/*.
git --git-dir=.git-bare config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'

# 2d. Fetch with the corrected refspec so remote tracking refs exist
git --git-dir=.git-bare fetch origin

# 2e. Create main/ as a linked worktree on the `main` branch
GIT_DIR=/data/git/agentrelay/.git-bare git worktree add /data/git/agentrelay/main main

# 2f. Verify it works
cd /data/git/agentrelay/main
git status          # should show "On branch main", clean working tree
git log --oneline   # should show the commits we pushed

# 2g. Clean up the old clone
rm -rf /data/git/agentrelay/main-old
```

**How git commands work after this:**
- Inside `main/` (or any worktree): normal `git` commands work as usual
- Repo-level commands (manage worktrees, branches) from the project root:
  ```bash
  GIT_DIR=/data/git/agentrelay/.git-bare git worktree list
  GIT_DIR=/data/git/agentrelay/.git-bare git worktree add /data/git/agentrelay/<name> -b <branch>
  ```

### Step 3: Initialize pixi environment

```bash
cd /data/git/agentrelay/main

# Initialize pixi with pyproject.toml format
pixi init --format pyproject

# Add Python and core dependencies
pixi add python
pixi add pyyaml         # YAML spec parsing
pixi add pytest          # testing

# Verify the environment works
pixi run python --version
pixi run pytest --version
```

This creates `pyproject.toml` and `pixi.lock` in `main/`.

### Step 4: Create project skeleton

```bash
cd /data/git/agentrelay/main

# Python package (src layout)
mkdir -p src/agentrelay
touch src/agentrelay/__init__.py

# Test directory
mkdir -p tests
touch tests/__init__.py

# Experiment directories
mkdir -p experiments/{01-manual,02-headless,03-signals,04-gates-retry,05-escalation,06-dependencies,07-agent-orchestrator}

# Workflow runtime directories (add to .gitignore — these are runtime state)
mkdir -p .workflow/{specs,signals,retry-context,state,audit}
```

### Step 5: Configure .gitignore

Add `.workflow/signals/`, `.workflow/retry-context/`, `.workflow/state/`, and `.workflow/audit/` to `.gitignore` (runtime state shouldn't be committed). Keep `.workflow/specs/` tracked — those are the workflow definitions.

### Step 6: Create CLAUDE.md

Write the root-level `CLAUDE.md` with project overview, conventions, bare repo usage, and pixi commands. This is the file every Claude Code instance will discover.

### Step 7: Commit scaffolding and push

```bash
cd /data/git/agentrelay/main
git add -A
git commit -m "project scaffolding: pixi env, package skeleton, experiment dirs"
git push origin main
```

### Step 8: Restructure to src/ layout

Move the package into the standard `src/` layout.

```bash
cd /data/git/agentrelay/main

# Move package into src/
mkdir -p src
git mv agentrelay/ src/agentrelay/

# Update pyproject.toml: change hatch build target to src/
# Change: packages = ["agentrelay"]  →  packages = ["src/agentrelay"]
# Change pixi pypi-dependencies path if needed

# Verify
pixi install
pixi run python -c "import agentrelay; print('OK')"
pixi run pytest

# Commit
git add -A
git commit -m "restructure: move agentrelay/ to src/agentrelay/ (src layout)"
git push origin main
```

### Key Decisions

- **YAML for specs** — unambiguous to parse, Claude handles it well, structured data maps naturally. Not Markdown.
- **Python for the interpreter** — starts as a simple script, grows into the orchestrator across experiments. Avoids a shell-to-Python rewrite later. YAML parsing, state management, and file watching are all natural in Python.
- **pixi for environment management** — consistent with the chatcat project's tooling.
- **Bare repo + worktrees** — enables parallel agent work in isolated worktrees sharing the same repo, as described in the knowledge capture document.

---

## Core Vocabulary (Refined)

The five abstractions from the original plan, with two additions:

| Concept | Description |
|---------|-------------|
| **Task** | Top-level unit — a name, a sequence of Steps, a terminal state |
| **Step** | Discrete work chunk for one agent. Has inputs, outputs, success_criterion, signal |
| **Gate** | Verification between Steps. Has reviewer, escalation level, retry config |
| **Signal** | How a Step announces completion (sentinel file, git commit, exit code) |
| **Reviewer** | Who evaluates a Gate (auto / notify / human), with escalation on max retries |
| **Workflow State** | **(new)** Explicit `state.json` per workflow — current step, attempt count, status. Single source of truth for "where is the pipeline right now?" |
| **Step Status** | **(new)** Distinguish between: step running, step completed (output produced), step failed (no output / crash / timeout). Gates only fire on step-completed. |

### Schema Refinement: `depends_on` for Future Parallelism

Steps gain an optional `depends_on: [step-id, ...]` field. For now, steps still execute linearly (the interpreter processes them in order). But the schema is ready for parallel execution without a breaking change.

---

## Experiment Plan

Each experiment has a trivial task (e.g., "write a function that adds two numbers") so focus stays on mechanics.

### Experiment 1: Hand-authored spec, manual execution
- Write a 2-step workflow spec YAML (write-tests → implement)
- Execute each step manually (launch Claude by hand)
- Evaluate the gate yourself
- **Deliverable:** A valid `.workflow/specs/exp-01.yaml` and notes on vocabulary gaps
- **Validates:** Spec format is expressive enough; vocabulary covers the workflow

### Experiment 2: Python interpreter, headless execution
- Build `src/agentrelay/loader.py` — parse YAML spec into Python dataclasses
- Build `src/agentrelay/runner.py` — iterate steps, launch `claude -p` for each
- Build `src/agentrelay/state.py` — write/read `state.json` per workflow
- Gates are no-ops (always pass) in this experiment
- **Deliverable:** `python -m agentrelay run .workflow/specs/exp-02.yaml` executes a 2-step pipeline end-to-end
- **Validates:** `claude -p` + CLAUDE.md is a workable execution model; state tracking works

### Experiment 3: Signals and automated step triggering
- Build `src/agentrelay/signals.py` — watch for sentinel files via polling or `inotifywait`
- Steps write a JSON signal file on completion
- The interpreter blocks on signal detection before proceeding
- **Deliverable:** Steps trigger gates without manual intervention
- **Validates:** Asynchronous signal mechanism works

### Experiment 3.5: Agent-generated specs
- Give a planning agent a natural-language task description
- Agent produces a valid workflow YAML spec
- Run the spec through the interpreter from Experiment 2
- **Deliverable:** A prompt template + example of agent-authored spec
- **Validates:** The YAML format is agent-writable (not just agent-readable)

### Experiment 4: Gate evaluation + retry context + audit log
- Build `src/agentrelay/gates.py` — launch a `claude -p` reviewer agent that reads step outputs
- On failure: write retry context file, re-run the previous step with enriched inputs
- Start writing to `.workflow/audit/` — record gate outcomes (timestamp, gate ID, result, reviewer, attempt number)
- **Deliverable:** Fail → feedback → retry loop works end-to-end; audit log is human-readable
- **Validates:** Retry context accumulation works; gates produce useful feedback

### Experiment 5: Escalation levels
- Enforce escalation per gate: `auto` (agent decides, continue), `notify` (agent decides, desktop notification, brief pause), `human` (block until human writes pass/fail)
- Implement `max_retries` escalation to `human`
- **Deliverable:** Mixed-escalation workflow runs correctly
- **Validates:** Human checkpoints integrate without breaking automation

### Experiment 6: Cross-step dependencies
- Define two Tasks where Task Y depends on Task X output
- Implement dependency checking: Y-1 does not launch until X-2's signal exists
- Use `depends_on` field in the schema
- **Deliverable:** Two-task DAG executes in correct order
- **Validates:** DAG support is feasible with minimal schema additions

### Experiment 7 (stretch): Agent-driven orchestrator
- Replace the Python interpreter with a Claude Code agent that reads the spec and launches subagents via the Task tool
- Compare: script-driven vs. agent-driven in flexibility, token cost, failure handling
- **Deliverable:** Same workflow spec, two execution modes, comparison notes
- **Validates:** When agent orchestration adds value over a script

---

## Implementation Order

1. **Project scaffolding** — repo setup, pyproject.toml, CLAUDE.md, directory structure
2. **Experiment 1** — hand-author a spec, manual run, validate vocabulary
3. **Experiment 2** — Python loader + runner + state tracking
4. **Experiment 3** — signals
5. **Experiment 3.5** — agent-generated specs (can run in parallel with 3)
6. **Experiment 4** — gates + retry + audit
7. **Experiment 5** — escalation
8. **Experiment 6** — dependencies
9. **Experiment 7** — agent orchestrator (stretch)

---

## Verification

Each experiment has its own validation criteria (listed above). For the framework code itself:

- **Unit tests:** `pytest tests/` — test loader, state, signal detection, gate logic against fixture YAML files
- **Integration test:** Run a full 2-step workflow spec end-to-end with `claude -p` (requires API/Max subscription)
- **Manual smoke test:** Inspect `.workflow/state/`, `.workflow/signals/`, `.workflow/audit/` after a run to confirm state is correct and human-readable

---

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `CLAUDE.md` | Create | Root project context — project overview, conventions, how to run |
| `pyproject.toml` | Create | Python project config with dependencies (pyyaml, etc.) |
| `src/agentrelay/__init__.py` | Create | Package init |
| `src/agentrelay/models.py` | Create | Dataclasses for workflow vocabulary |
| `src/agentrelay/loader.py` | Create | YAML → model objects |
| `src/agentrelay/state.py` | Create | Workflow state read/write |
| `src/agentrelay/runner.py` | Create | Step execution via `claude -p` |
| `src/agentrelay/gates.py` | Create | Gate evaluation logic |
| `src/agentrelay/signals.py` | Create | Signal detection |
| `experiments/01-manual/` | Create | Experiment 1 spec + notes |
| `tests/` | Create | Framework unit tests |
