# agentrelay

Multi-agent orchestration system: a Python orchestrator manages a graph of coding
tasks, each executed by a Claude Code instance in its own tmux pane and git worktree.
Each agent commits its work, creates a PR, and signals completion via a sentinel file.
The orchestrator merges PRs in dependency order.

## Commands

| Command | Purpose |
|---|---|
| `pixi run test` | Run full test suite |
| `pixi run typecheck` | Pyright static analysis |
| `pixi run format` | black + isort |
| `pixi run check` | format + typecheck + test (pre-PR verification) |
| `pixi run setup-hooks` | Enable git pre-commit hooks (one-time setup) |
| `agentrelay run graphs/<category>/<name>.yaml` | Run a task graph |
| `agentrelay reset graphs/<category>/<name>.yaml` | Reset repo to pre-run state |
| `agentrelay dry-run graphs/<category>/<name>.yaml` | Validate graph and print execution plan |
| `agentrelay check` | Preflight checks on target repo |

## Module map

| File | Responsibility |
|---|---|
| `cli.py` | Top-level `agentrelay` CLI: subcommand dispatch to run/reset/check/dry-run |
| `run_graph.py` | Top-level composition + CLI: wires graph, runners, orchestrator |
| `orchestrator/` | Async scheduler, config, runtime builders, runner builders |
| `task_graph/` | Immutable `TaskGraph` DAG model and `TaskGraphBuilder` YAML parser |
| `task_runner/` | `TaskRunner` protocol, `StandardTaskRunner`, per-step dispatch |
| `workstream/` | `WorkstreamRunner` protocol, `StandardWorkstreamRunner`, workstream lifecycle |
| `task_runtime/` | Mutable `TaskRuntime`, `TaskState`, `TaskStatus` |
| `agent/` | `Agent` / `AgentAddress` abstractions, `TmuxAgent` implementation |
| `agent_comm_protocol/` | Manifest, policies, role templates for agent instructions |
| `ops/` | Stateless subprocess wrappers: git, tmux, gh, signals |
| `task.py` | `Task`, `AgentRole`, `AgentConfig`, `TaggedPath` data models |
| `reset_graph.py` | Full graph reset: closes PRs, resets main, deletes branches |

## Signal files

Per-task directory: `.workflow/<graph>/signals/<task-id>/`

| File | Written by | Meaning |
|---|---|---|
| `.done` | Agent | Task complete; line 2 is the PR URL |
| `.failed` | Agent | Task failed; line 2 is the reason |
| `.merged` | Orchestrator | PR merged successfully |
| `agent.log` | Orchestrator | tmux pane scrollback captured after task |
| `ops_concerns.log` | Agent | Operational concerns (build errors, tooling friction) |
| `summary.md` | Orchestrator | PR body fetched before merge |

Graph-level: `.workflow/<graph>/run_info.json` — start HEAD + timestamp (for reset).

## Graph YAML

```yaml
name: my-graph
tmux_session: agentrelay  # optional; default "agentrelay"
keep_panes: false              # optional; leave tmux windows open for debugging
model: claude-sonnet-4-6       # optional; graph-level default model for all agents
fail_fast_on_workstream_error: false  # optional; block new workstreams on failure (default: false)
fail_fast_on_internal_error: true    # optional; halt on internal errors (default: true)
tasks:
  - id: my_task
    description: "..."
    role: generic              # optional; generic | test_writer | test_reviewer | implementer | spec_writer | merger
    model: claude-haiku-4-5-20251001  # optional; overrides graph-level model for this task
    tagged_paths:              # optional; list of {path, category} entries
      - path: src/my_module.py
        category: src
      - path: tests/test_my_module.py
        category: test
    # Alternative: 'paths' sugar (converted to tagged_paths internally)
    # paths:                   # optional; mutually exclusive with tagged_paths
    #   src:
    #     - src/my_module.py
    #   test:
    #     - tests/test_my_module.py
    #   spec: specs/my_spec.md
    dependencies: []
    inputs_from:               # optional; reference upstream task outputs
      task: upstream_task_id   # required; must be a (transitive) dependency
      category: stubs          # optional; filter by output category
    # inputs_from also accepts a list for multiple sources:
    # inputs_from:
    #   - task: spec_task
    #     category: stubs
    #   - task: test_task
    #     category: tests
```

## Development workflow

When making changes to agentrelay itself:

1. **Create a feature branch** — `git checkout -b feat/<short-name>`
2. **Make changes** — edit source, tests, or docs
3. **Verify** — `pixi run check` (format + typecheck + test) must pass
4. **Commit** — `git add <files> && git commit -m "type: description"`
5. **Push** — `git push -u origin feat/<short-name>`
6. **Open PR** — `gh pr create` with a `## Summary` and `## Test plan` checklist
7. **Iterate** — address review feedback; `pixi run check` after each change
8. **Merge** — `gh pr merge <url> --merge` once the human approves

Rules:
- Never commit directly to `main`
- Always run `pixi run check` before creating a PR
- PR body must include a `## Test plan` checklist (automated + human-verifiable items)
- Update `docs/HISTORY.md` with a new entry for each merged PR
- Update `docs/diagrams/uml/diagram-detailed.d2` and re-render (`pixi run diagram`)
  in every PR that touches `src/agentrelay/`. Rendering updates the detailed SVG,
  regenerates all per-module diagrams (`docs/diagrams/uml/modules/`), and regenerates
  the module overview (`diagram-modules`). Requires the TALA layout engine
  (`d2plugin-tala`) installed locally. A pre-commit hook blocks commits where `.d2`
  changed without a corresponding `.svg` update. Run `pixi run setup-hooks` once to enable.
- When adding a new module: add its diagram link to `docs/DIAGRAM.md` (per-module table)
  and to its API reference page (if one exists) under `docs/api/`.

## Coding conventions

**Public API surfaces use classes.** Every type that appears in the design diagram
(`docs/diagrams/uml/diagram-detailed.d2`) must be a class — dataclass, enum, Protocol, or ABC. When a
class exists solely as a container of static methods (no state, no `__init__`), it is
intentionally stateless — a named namespace for related operations.

**Internal helper modules may use free functions.** Private submodules (prefixed with
`_`, e.g. `task_graph/_validation.py`) may contain plain functions when they serve as
internal implementation details of a single package. These modules are diagrammed with
a `<<module>>` stereotype and are not part of the public API.

## Docs

- `docs/diagrams/uml/diagram-detailed.d2` — authoritative design diagram source (D2 with TALA layout); updated every PR
- `docs/diagrams/uml/diagram-detailed.svg` — rendered detailed diagram (generated by `pixi run diagram`)
- `docs/diagrams/uml/diagram-modules.d2` — auto-generated module-level dependency overview (do not edit)
- `docs/diagrams/uml/modules/diagram-{name}.d2` — auto-generated per-module focused diagrams (do not edit)
- `docs/DIAGRAM.md` — diagram display page with PR update policy
- `docs/ARCHITECTURE.md` — module map, design principles, extensibility notes
- `docs/WORKFLOW.md` — end-to-end workflow specification
- `docs/GUIDE.md` — installation, repo setup, development workflow
- `docs/HISTORY.md` — feature history (one entry per PR)
- `docs/BACKLOG.md` — ideas and future work (add here, don't interrupt current task)
