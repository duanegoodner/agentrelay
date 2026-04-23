# agentrelay

`agentrelay` is a Python orchestrator that runs a DAG of coding tasks as
autonomous agents. Each task runs in its own git worktree, with a live
agent in its own tmux pane, and opens a pull request when it completes.
The orchestrator sequences tasks, aggregates their PRs into
per-workstream integration PRs, and coordinates everything through
plain files on disk. The default wiring today is Claude Code in tmux
inside Docker, but the abstractions are deliberately pluggable, so
other agent frameworks, cloud agents, local-LLM backends, and
alternative isolation approaches are all intended extension points.

> ⚠️ **Under active development.** `agentrelay` is a pre-Rust Python
> prototype. Its CLI surface, graph YAML schema, and internal APIs may
> change without notice. See the [Status](#status) section for the
> current phase and roadmap.

📚 Full documentation: https://duanegoodner.github.io/agentrelay/

## What it does

Work is described as a graph of tasks in YAML. `agentrelay run` creates
a git worktree per workstream, launches each task as a Claude Code
agent in a fresh tmux pane inside an OCI container, and polls signal
files to detect agent completion. Each task opens its own PR, and each
workstream opens an integration PR that aggregates its tasks. A
workstream can optionally be declared `auto_merge: true` in the graph
YAML, in which case the orchestrator merges the integration PR to the
target branch after the PR is created, provided no task in the
workstream recorded a design concern. Otherwise the integration PR is
left for human review.

That runtime model is the *current default wiring*, not a fixed
architecture. The core surfaces (`Agent`, `AgentEnvironment`,
`AgentSandbox`, `AgentFrameworkAdapter`, `CredentialProvider`) are
protocols, so the agent framework, execution environment, and isolation
mechanism are swappable. Today that resolves to Claude Code + tmux +
Docker. Planned targets include other agent frameworks, cloud-hosted
agents, local-LLM backends, and alternative isolation mechanisms.

## A minimal graph

```yaml
# graphs/smoke/quick_chained.yaml
name: quick-chained
model: claude-sonnet-4-6
tools:
  - pixi

tasks:
  - id: counter_fn
    description: >-
      Create src/agentrelaydemos/counter.py with a Counter class
      (increment, decrement, value property; floor at zero) and
      pytest tests in test/test_counter.py.
    dependencies: []

  - id: use_counter
    description: >-
      Create src/agentrelaydemos/counter_utils.py with count_up(n)
      and count_down(start, n) built on Counter. Add pytest tests.
    dependencies:
      - counter_fn
```

Running it against a target repo:

```bash
agentrelay run graphs/smoke/quick_chained.yaml \
  --target-repo /path/to/repo \
  --sandbox oci \
  --credentials ~/.config/agentrelay/credentials.yaml
```

What happens when that command fires:

- A worktree is created per workstream under
  `.worktrees/<graph>/<ws-id>/` (in the target repo).
- Each task gets a git branch, a tmux pane running Claude Code (by
  default inside a Docker container), and a per-task signal directory
  under `.workflow/<graph>/runs/<N>/signals/<task-id>/` containing
  `manifest.json`, resolved `instructions.md`, `outputs.json`,
  per-attempt logs, and `.done` / `.failed` sentinels.
- On task completion, the agent writes `.done` (with a PR URL) and the
  orchestrator merges the task PR into the workstream's integration
  branch.
- When a workstream's tasks are all merged, the orchestrator opens an
  integration PR. If the workstream is declared `auto_merge: true` and
  no task recorded a design concern, the orchestrator merges that PR
  to the target branch automatically; otherwise it is left for human
  review.
- A partial run can be resumed: re-invoking `agentrelay run` on the
  same graph picks up where the previous run left off. Targeted
  rollback is available via `reset-task`, `reset-workstream`, and
  `reset-to`.

## Design notes

- **Pluggable.** Agent framework, execution
  environment, and isolation are behind protocols. The current
  realization is one configuration; swapping in a different agent
  framework, cloud runner, or local LLM is a wiring change, not a
  rewrite.
- **Signal-file-backed state.** The orchestrator
  and agents coordinate through files under
  `.workflow/<graph>/runs/<N>/`. State is inspectable with `ls` and
  `cat`, survives process death, and is what makes resumption and
  observability tractable.
- **Immutable spec, mutable runtime.** The split runs through the
  codebase: `Task` vs `TaskRuntime`, `WorkstreamSpec` vs
  `WorkstreamRuntime`, with status, artifacts, and errors held
  separately from the definition. Execution never mutates the spec,
  which is what makes frozen records (`resolved.json`), state
  probing, and resumption tractable.
- **Guidance, not restriction, for agent autonomy.** `inputs_from` and
  role templates are contracts and convenience, not access control.
  Agents retain full graph awareness; observation of how they use
  broad context precedes any design of restrictions.
- **Concern-gated automation.** Agents can raise design concerns via
  the `TaskHelper` SDK during execution. A recorded concern blocks
  auto-merge of the workstream's integration PR and falls through to
  human review. Machine precision is the default path; human
  judgment is an explicit escape hatch the agent can invoke.
- **OCI isolation spectrum.** Containers are the recommended default,
  with configurable levels from relaxed to strict. Relaxed is a knob
  on a container, not a reason to skip containers. `SandboxType.NONE`
  exists as an explicit opt-out for the agentrelay dev loop and
  first-time setup.
- **Clean rewrite over incremental for the Rust port.** The Python
  codebase is the behavioral spec. When Phase 5 lands, the Python
  version freezes; Rust starts greenfield and reimplements against
  the existing e2e test suite.

## Getting started

**Requirements:**

- Python 3.12+
- [pixi](https://pixi.sh)
- [Claude Code CLI](https://github.com/anthropics/claude-code)
- `git` (with worktree support), `tmux`, `gh` (authenticated)
- Docker or Podman (recommended; OCI is the default execution mode)

**Install and verify:**

```bash
git clone https://github.com/duanegoodner/agentrelay.git
cd agentrelay
pixi install
pixi run check
```

**Credentials.** `agentrelay` reads a YAML file with a named
`anthropic` section (either `api_key` via `key_file`, or `oauth` via a
session path) and optional GitHub PAT tiers for in-container git/gh
access. See [docs/GUIDE.md](docs/GUIDE.md) for the schema. By
convention this lives at `~/.config/agentrelay/credentials.yaml`.

**First run** against a target repo:

```bash
agentrelay check --target-repo /path/to/target
agentrelay run graphs/smoke/quick_chained.yaml \
  --target-repo /path/to/target \
  --credentials ~/.config/agentrelay/credentials.yaml
```

`agentrelay run` creates per-task PRs and an integration PR. The
integration PR is merged automatically when the workstream declares
`auto_merge: true` and no design concerns were raised; otherwise it is
left for human review.

## Status

Python prototype, pre-Rust. **Phase 4 (graph resumption) landed
2026-04-23.** Partial runs can now be resumed, and targeted rollback
commands (`reset-task`, `reset-workstream`, `reset-to`) cover
stack-based and batch undo. Test suite: 1722 tests across 21
end-to-end graph scenarios, all passing with OCI isolation.

Development is paused for ~2 to 3 weeks. On resume, the plan is:

- **Phase 4.5: Persistent agents.** Minimal prototype of agents that
  carry conversation context across tasks within a workstream.
- **Phase 5: Documentation sprint.** README deepening, design
  philosophy document, getting-started refresh, runtime diagrams.
- **Phase 6: Freeze Python, begin Rust.** Clean rewrite against the
  existing e2e test suite as acceptance criteria.

See [docs/planning/pre-rust-roadmap.md](docs/planning/pre-rust-roadmap.md)
for the full plan and strategic decisions.

## Learn more

- [docs/planning/pre-rust-roadmap.md](docs/planning/pre-rust-roadmap.md): roadmap and strategic decisions
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): core abstractions and orchestrator contract
- [docs/WORKFLOW.md](docs/WORKFLOW.md): run/reset cycle end-to-end
- [docs/GUIDE.md](docs/GUIDE.md): install, credentials, CLI reference
- [docs/sprints/complete/](docs/sprints/complete/): sprint archive (Phases 1 through 4)
