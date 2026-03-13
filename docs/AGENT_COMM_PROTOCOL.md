# Agent Communication Protocol

This document defines the communication protocol between the agentrelay
orchestrator and the agents it manages. The protocol is the foundation for
instruction builders, framework adapters, and the agent-side API.

## Design qualities

1. **Traceable / auditable / persistent** — file-based; every instruction
   and signal is recoverable after the fact
2. **Structured with natural language where appropriate** — machine-readable
   envelope, human-readable payload; formal structure preferred when it
   enables concise/precise description; natural language allowed when easier
   or when formal channels have shortcomings
3. **Environment/backend agnostic** — works regardless of where the agent
   runs (local tmux, cloud API) or what backend it uses (Claude Code, Codex,
   Copilot, local LLM, etc.)
4. **Unidirectional simplicity** — orchestrator writes files before launch,
   agent writes signals during/after execution; no mid-task back-and-forth
5. **Minimal coupling** — instruction content does not know how signaling
   works; role-specific work does not embed framework-specific commands
6. **Composable** — workflow behaviors are independently present or absent;
   adding a new behavior does not require changing instruction builders

## Protocol layers

The protocol has five layers. Layers 1-4 are framework-agnostic. Layer 5 is
the framework-specific translation.

### Layer 1 — Task manifest (`manifest.json`)

| | |
|---|---|
| **Writer** | Orchestrator via `TaskPreparer` (before launch) |
| **Reader** | Framework adapter and agent |
| **Format** | JSON, strictly typed |

Pure facts about the task. No shell commands, no framework-specific data.

```json
{
  "schema_version": "1",
  "task": {
    "id": "write_greet_tests",
    "role": "test_writer",
    "description": "Write pytest tests for the greet module"
  },
  "paths": {
    "src": ["src/myproject/greet.py"],
    "test": ["tests/test_greet.py"],
    "spec": null
  },
  "workspace": {
    "branch_name": "graph/demo/write_greet_tests",
    "integration_branch": "graph/demo"
  },
  "execution": {
    "attempt_num": 0,
    "graph_name": "demo"
  },
  "dependencies": {
    "write_greet_stubs": {
      "description": "Create stub module for greet with docstrings"
    }
  }
}
```

### Layer 2 — Work instructions

| | |
|---|---|
| **Format** | Markdown, natural language |
| **Content** | Role-specific work only — no git commands, no signaling, no gate loops |

Work instructions operate in two modes.

#### Mode A — Role templates (formulaic tasks)

For standard roles (`spec_writer`, `test_writer`, `test_reviewer`,
`implementer`), instructions are a function of `(role, paths)`. A graph with
20 test-writer tasks should not produce 20 nearly-identical files.

Role templates live in a shared `templates/` directory. The manifest provides
parameters. The adapter resolves template + parameters at delivery time.

Template resolution order: adapter-specific override > shared template >
per-task custom instructions.

Adapter-specific overrides go in `templates/<adapter_name>/` (e.g.,
`templates/claude_code/test_writer.md`).

Example shared template (`templates/test_writer.md`):

```markdown
# Role: TEST_WRITER

## Context
If context.md exists in this directory, read it first.

## Work
1. Read the source stubs at {src_paths} to understand the API contract.
   The docstrings are the authoritative spec.
2. Write pytest test files at: {test_paths}
   The stub modules already exist — do NOT create or overwrite them.
3. Verify tests collect without import errors.

Do NOT implement the feature. Only write tests.
```

Parameters come from `manifest.json`: `paths.src`, `paths.test`, etc.

#### Mode B — Custom instructions (novel tasks)

For `generic` role or unusual tasks, a per-task `instructions.md` file is
written to the signal directory with natural language content. This is the
escape hatch for work that cannot be expressed as a template.

#### Common workflow pattern

The protocol is designed around this recurring task sequence:

1. **Spec writer** — transform natural language intent into code specs
   (Python stubs with docstrings, C++ headers, UML diagrams, etc.). This is
   the creative/custom step.
2. **Test writer** — write tests against the specs. Formulaic: template +
   paths.
3. **Test reviewer** — review the tests. Formulaic: template + paths.
4. **Implementer** — implement code satisfying specs, pass tests, meet
   coverage threshold. Formulaic with gate loop: template + paths + gate.

Once specs exist (after step 1), steps 2-4 are mechanical. The system makes
mechanical steps trivially repeatable without per-task instruction authoring.

### Layer 3 — Workflow policies (`policies.json`)

| | |
|---|---|
| **Writer** | Orchestrator via `TaskPreparer` (before launch) |
| **Reader** | Framework adapter (translates to framework-specific actions) |
| **Format** | JSON, composable (each key independently present or `null`) |

Uses an abstract workflow step vocabulary that adapters translate into
framework-specific actions.

Initial vocabulary:

| Action | Meaning |
|---|---|
| `commit_and_push` | Stage, commit, and push to remote |
| `create_pr` | Create a pull request against the integration branch |
| `signal_done` | Signal task completion with PR URL |
| `signal_failed` | Signal task failure with reason |
| `run_completion_gate` | Run a gate command with retry logic |
| `record_concern` | Record a design concern |
| `write_adr` | Write an architecture decision record |
| `run_verification` | Run verification commands (e.g., `pytest --collect-only`) |

Example:

```json
{
  "schema_version": "1",
  "commit_policy": {
    "action": "commit_and_push"
  },
  "pr_policy": {
    "action": "create_pr",
    "base_branch": "graph/demo",
    "title_template": "{task_id}",
    "body_sections": ["summary", "files_changed"]
  },
  "completion_gate": {
    "command": "pixi run pytest tests/test_greet.py",
    "max_attempts": 5,
    "output_file": "gate_last_output.txt"
  },
  "review": null,
  "adr": null,
  "verification": {
    "commands": ["pytest --collect-only"]
  }
}
```

Adding a new composable behavior means adding a new key to
`policies.json` and teaching adapters to translate it. Removing a behavior
means setting its key to `null`. No instruction builder changes needed.

### Layer 4 — Signaling contract

Defines what signals exist, not how they are transmitted.

#### Agent to orchestrator

| Signal | Meaning | Required data |
|---|---|---|
| `done` | Task complete, PR exists | `pr_url` (string) |
| `failed` | Task failed | `error` (string) |
| `concern` | Design concern noted | `text` (string), `timestamp` (ISO 8601) |
| `gate_attempt` | Gate was run | `attempt_num` (int), `passed` (bool), `timestamp` (ISO 8601) |

#### Orchestrator to agent (pre-launch files)

| Signal | File | Purpose |
|---|---|---|
| Task manifest | `manifest.json` | Structured task facts |
| Work instructions | `instructions.md` | Role-specific work (resolved template or custom) |
| Workflow policies | `policies.json` | Composable workflow configuration |
| Dependency context | `context.md` | Summary of prerequisite tasks (optional) |

#### Orchestrator post-completion

| Signal | Meaning |
|---|---|
| `merged` | PR was successfully merged |

#### File-based implementation (default)

| Abstract signal | File | Format |
|---|---|---|
| `done` | `.done` | Line 1: ISO timestamp, Line 2: PR URL |
| `failed` | `.failed` | Line 1: ISO timestamp, Line 2: error message |
| `concern` | `concerns.log` | Append-only, timestamped entries |
| `gate_attempt` | `gate_attempts.log` | Append-only, `timestamp attempt=N passed=True/False` |
| `merged` | `.merged` | Line 1: ISO timestamp |

Maps directly to the existing `TaskCompletionSignal` dataclass.

### Layer 5 — Framework adapter

Not a new abstraction — maps onto existing `TaskRunnerIO` protocol
implementations. Concrete implementations of `TaskPreparer`, `TaskLauncher`,
`TaskKickoff`, `TaskCompletionChecker`, `TaskMerger`, `TaskTeardown` per
framework/environment combination.

The adapter does not modify `instructions.md`. It reads the abstract policies
and adds or translates as needed for its framework.

#### Claude Code + tmux (first adapter)

1. Orchestrator produces `manifest.json`, `instructions.md`, `policies.json`
   (all framework-agnostic)
2. `ClaudeCodeTmuxPreparer.prepare()` reads `policies.json` and generates
   framework-specific material — could be `workflow.md`, `CLAUDE.md` in the
   worktree, MCP tool registration, or a combination
3. `ClaudeCodeTmuxKickoff.kickoff()` sends bootstrap prompt telling the agent
   where to find everything
4. `ClaudeCodeTmuxCompletionChecker.wait_for_completion()` polls for
   `.done`/`.failed` files

#### Hypothetical API agent

1. Same framework-agnostic files produced
2. `CodexApiPreparer.prepare()` composes a single API prompt from the three
   files — no extra files needed
3. `CodexApiKickoff.kickoff()` submits the prompt via HTTP
4. `CodexApiCompletionChecker.wait_for_completion()` parses the API response
   into `TaskCompletionSignal`

## Signal directory layout

```
.workflow/<graph>/signals/<task-id>/

  # Layer 1-3: orchestrator writes before launch
  manifest.json
  instructions.md
  policies.json
  context.md                 (optional, if task has dependencies)

  # Layer 5: adapter writes before launch (varies by adapter)
  [adapter-specific files]

  # Layer 4: agent writes during execution
  .done
  .failed
  concerns.log
  gate_attempts.log
  gate_last_output.txt

  # Orchestrator writes after completion
  .merged
  agent.log
  summary.md
```

File ownership rules:

| Timing | Writer | Files |
|---|---|---|
| Before launch | Orchestrator | `manifest.json`, `policies.json`, `context.md` |
| Before launch | Instruction builder (via orchestrator) | `instructions.md` |
| Before launch | Framework adapter | adapter-specific files |
| During execution | Agent | `.done`, `.failed`, `concerns.log`, `gate_attempts.log`, `gate_last_output.txt` |
| After completion | Orchestrator | `.merged`, `agent.log`, `summary.md` |

## Spec representation

Spec formats are abstracted via a `SpecRepresentation` protocol in a `spec/`
package. The first concrete implementation is `PythonStubSpec` (Python files
with docstrings and `raise NotImplementedError`).

Future implementations (e.g., `CppHeaderSpec`, `UmlSpec`) can be added without
changing the protocol. The spec_writer role template is parameterized by spec
representation type.

## Relationship to existing architecture

| Existing component | Protocol relationship |
|---|---|
| `TaskRunnerIO` (six protocols) | Layer 5 maps directly onto these |
| `TaskCompletionSignal` | Layer 4 maps directly; no changes needed |
| `TaskRunner` state machine | Unchanged; orchestrates the protocols |
| `Orchestrator` | Unchanged; schedules tasks |
| `Task`, `TaskRuntime` | Unchanged; data models |
| `ops/signals.py` | File-based implementation of Layer 4 |
