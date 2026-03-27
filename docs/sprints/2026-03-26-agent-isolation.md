# Sprint Notes — 2026-03-26: Agent Isolation

> **Status: In progress.** PR A merged (#139). Next: PR B.

## Goal

Design and implement tunable agent isolation infrastructure — per-graph,
per-workstream, per-task configurable sandboxing using Docker containers,
scoped GitHub PATs, and framework-specific config injection. The architecture
supports Level 0–2 isolation with extensibility to Level 3 and alternative
runtimes (Podman, bubblewrap).

## Context

Sprint 2026-03-25 completed cross-workstream dependency ordering (PR #134)
and optional auto-merge (PR #135). The motivating incident — an agent
unilaterally merging an integration PR to main — is now prevented
architecturally. But the broader problem remains: agents run as the human
user with full credentials, and nothing prevents them from taking
globally-problematic actions when they encounter unexpected situations.

See `docs/discussions/AGENT_ISOLATION_REFINED.md` for full analysis of the
isolation spectrum (Levels 0–3), tunable isolation design, token tiers, ACL
profiles, and the motivating incident.

### Architecture decisions

**Container-per-task, orchestrator on host:**

- Each task runs in its own Docker container. The container IS the isolation
  boundary — no Linux user management needed on the host.
- Orchestrator stays on host (trusted code, needs Docker socket + tmux +
  filesystem).
- tmux stays on host: each pane runs `docker run -it ...`, preserving the
  current debugging UX where the human sees all agents in one tmux session.
- Docker network per graph for inter-agent communication restrictions.

**Sandbox as command wrapper, orthogonal to environment:**

- `AgentSandbox` protocol wraps the agent command string
  (`docker run ... claude ...`).
- Sandbox is orthogonal to `AgentEnvironment` (tmux). No new environment
  type needed — the `StepDispatch` key `(framework, env_type)` is unchanged.
- `NullSandbox` preserves current behavior exactly (Level 0).

**Four-level isolation inheritance:**

- Isolation is configurable at four levels: graph → workstream → task → agent.
  Each level can set `isolation:` in YAML; unset fields inherit from parent.
  Resolution happens during YAML parsing in `TaskGraphBuilder`.
- `Task.isolation: Optional[IsolationConfig]` — task-level override. Applies
  to all agents in the task (primary + review) unless an agent overrides.
- `AgentConfig.isolation: Optional[IsolationConfig]` — agent-level override.
  Allows primary and review agents to differ (e.g., review agent gets
  read-only PAT while primary gets standard).
- The builder resolves the full chain and stores the final resolved config
  (all fields set, no `None`s) on each `AgentConfig.isolation`.

**Credentials via protocol, injected as env vars:**

- `CredentialProvider` protocol resolves token tier → env var dict.
- Credentials never written to disk inside container — env var injection only.
- `FileCredentialProvider` reads from `~/.config/agentrelay/credentials.yaml`.

**Framework config extracted to adapter:**

- `FrameworkConfigAdapter` protocol builds the framework-specific command string.
- `ClaudeCodeAdapter` extracts current command-building logic from
  `TmuxAgent.from_config()`.
- Future `CodexAdapter` etc. implement the same protocol.

**Docker image: ubuntu:24.04 base:**

- Full Linux userspace for multi-framework support (Claude Code, future
  Codex/Copilot).
- Layers: ubuntu base → git/gh → node/python → claude-code + agent SDK.
- Target repo tools (pixi, etc.) handled by image variants or setup scripts.

**Git worktree bind mounts at same absolute path:**

- Mount worktree + signal dir read/write, repo `.git` read-only.
- Same absolute paths inside container → `.git` file internal paths resolve
  without modification.
- Helper reads worktree `.git` file to discover main repo `.git` dir path.

### New module: `src/agentrelay/sandbox/`

```
sandbox/
  __init__.py
  core/
    __init__.py
    config.py          # SandboxType, TokenTier, IsolationConfig, SandboxContext
    sandbox.py         # AgentSandbox protocol
    credentials.py     # CredentialProvider protocol
    adapters.py        # FrameworkConfigAdapter protocol
  implementations/
    __init__.py
    null_sandbox.py    # NullSandbox (pass-through, Level 0)
    oci_sandbox.py     # OciSandbox (Docker/Podman, Level 2)
    claude_code_adapter.py  # ClaudeCodeAdapter
    file_credentials.py     # FileCredentialProvider
```

Also: `src/agentrelay/ops/docker.py` — thin subprocess wrappers (same
pattern as `ops/tmux.py`).

### Example YAML with isolation

```yaml
name: isolated-graph
isolation:                    # graph default (level 1)
  sandbox: oci
  token_tier: standard

workstreams:
  - id: ws_review
    isolation:                # workstream override (level 2)
      token_tier: read_only
  - id: ws_merge
    isolation:
      token_tier: elevated

tasks:
  - id: write_tests
    workstream: ws_review
    role: test_writer
    # inherits: sandbox=oci, token_tier=read_only (from ws_review)

  - id: implement
    workstream: ws_merge
    role: implementer
    isolation:                # task override (level 3) — applies to all agents
      token_tier: standard
    # primary_agent inherits: sandbox=oci, token_tier=standard (from task)
    # review agent (if any) also inherits task-level isolation

  - id: reviewed_task
    workstream: ws_review
    role: generic
    isolation:                # task override (level 3)
      token_tier: read_only
    review:
      agent:
        isolation:            # agent override (level 4) — review agent only
          token_tier: elevated
    # primary_agent: sandbox=oci, token_tier=read_only (from task)
    # review agent: sandbox=oci, token_tier=elevated (from agent override)
    dependencies: [write_tests]
```

---

## PR plan

### PR A: Sandbox data models + AgentSandbox protocol + NullSandbox — MERGED (#139)

- Branch: `feat/sandbox-protocol`
- Note: `SandboxType.CONTAINER` used instead of `OCI` (user preference).

**Scope:**
- `SandboxType` enum: `NONE`, `CONTAINER` (future: `BWRAP`)
- `TokenTier` enum: `READ_ONLY`, `STANDARD`, `ELEVATED`
- `IsolationConfig` frozen dataclass: `sandbox_type`, `token_tier`, `image`,
  `runtime` (docker/podman)
- `SandboxContext` frozen dataclass: worktree_path, signal_dir, repo_path,
  task_id, graph_name, env_vars
- `AgentSandbox` protocol: `wrap_command(cmd, context) -> str`,
  `setup(context) -> None`, `teardown(context) -> None`
- `NullSandbox` implementation: returns command unchanged, setup/teardown
  are no-ops
- Add `isolation: Optional[IsolationConfig]` to `Task` — task-level override,
  applies to all agents in the task unless an agent overrides
- Add `isolation: Optional[IsolationConfig]` to `AgentConfig` — agent-level
  override, allows primary and review agents to differ
- Add `isolation: Optional[IsolationConfig]` to `WorkstreamSpec`
- YAML parsing: `_parse_isolation_config()` in builder.py
- Four-level inheritance: graph → workstream → task → agent
  - Parse raw isolation config at each level (all fields Optional)
  - Merge function: child overrides parent for explicitly set fields,
    inherits unset fields
  - Final resolved config (all fields set) stored on each
    `AgentConfig.isolation` after full chain resolution

**Key files modified:**
- `src/agentrelay/task.py` — `Task` gains `isolation` field,
  `AgentConfig` gains `isolation` field
- `src/agentrelay/workstream/core/workstream.py` — `WorkstreamSpec` gains
  `isolation` field
- `src/agentrelay/task_graph/builder.py` — `_parse_isolation_config()`,
  update `_parse_task()`, `_parse_agent_config()`, `_parse_workstream()`,
  four-level merge logic
- New: `src/agentrelay/sandbox/` package

**Acceptance criteria:**
- [x] `IsolationConfig` frozen dataclass with sensible defaults
      (SandboxType.NONE, TokenTier.STANDARD)
- [x] `AgentSandbox` protocol defined with `@runtime_checkable`
- [x] `NullSandbox` satisfies protocol, returns command unchanged
- [x] YAML graphs with `isolation:` parse at graph, workstream, task,
      and agent levels
- [x] Four-level inheritance: agent overrides task overrides workstream
      overrides graph; unset fields inherit
- [x] Graphs without `isolation:` use defaults (zero behavior change)
- [x] `pixi run check` passes (1032 tests, 43 new)
- [x] All existing tests pass unchanged
- [x] E2E regression: `diamond_4_workstreams_auto_merge.yaml` passes

---

### PR B: FrameworkConfigAdapter + refactor TmuxAgent command building

- Branch: `feat/framework-adapter`

**Scope:**
- `FrameworkConfigAdapter` protocol:
  `build_command(config: AgentConfig, signal_dir: Path) -> str`
- `ClaudeCodeAdapter`: extracts command-building from
  `TmuxAgent.from_config()` lines 67–72
- Refactor `TmuxAgent.from_config()` to accept
  `adapter: FrameworkConfigAdapter` and `sandbox: AgentSandbox`
- Flow: adapter builds command → sandbox wraps it → tmux sends wrapped
  command
- Update `TmuxTaskLauncher` to construct adapter and sandbox
- Update `build_standard_runner()` to thread dependencies into launcher

**Key files modified:**
- `src/agentrelay/agent/implementations/tmux_agent.py` — `from_config()`
  accepts adapter + sandbox
- `src/agentrelay/task_runner/implementations/task_launcher.py`
- `src/agentrelay/orchestrator/builders.py`
- New: `src/agentrelay/sandbox/core/adapters.py`,
  `src/agentrelay/sandbox/implementations/claude_code_adapter.py`

**Acceptance criteria:**
- [ ] `ClaudeCodeAdapter.build_command()` produces identical command string
      to current `TmuxAgent.from_config()`
- [ ] `TmuxAgent.from_config()` with `NullSandbox` + `ClaudeCodeAdapter`
      is behaviorally identical to current code
- [ ] Command building testable independently of tmux
- [ ] `pixi run check` passes

---

### PR C: CredentialProvider + FileCredentialProvider

- Branch: `feat/credential-provider`

**Scope:**
- `CredentialProvider` protocol: `resolve(tier: TokenTier) -> dict[str, str]`
- `FileCredentialProvider`: reads `~/.config/agentrelay/credentials.yaml`
- `EnvCredentialProvider`: reads from env vars
  (`AGENTRELAY_PAT_READ_ONLY`, etc.)
- `NullCredentialProvider`: returns empty dict (for SandboxType.NONE)
- Credential file schema:
  ```yaml
  token_tiers:
    read_only:
      GH_TOKEN: ghp_xxxx
    standard:
      GH_TOKEN: ghp_yyyy
    elevated:
      GH_TOKEN: ghp_zzzz
  defaults:
    ANTHROPIC_API_KEY: sk-ant-xxxx
  ```
- Wire into sandbox flow: `SandboxContext.env_vars` populated from
  credential resolution
- Wire into `build_standard_runner()`: credential provider constructed
  and passed to launcher

**Key files modified:**
- New: `src/agentrelay/sandbox/core/credentials.py`,
  `src/agentrelay/sandbox/implementations/file_credentials.py`
- `src/agentrelay/orchestrator/builders.py`
- `src/agentrelay/task_runner/implementations/task_launcher.py`

**Acceptance criteria:**
- [ ] `FileCredentialProvider` reads YAML config and resolves token tiers
- [ ] `EnvCredentialProvider` reads from env vars
- [ ] Missing tier raises clear error
- [ ] `NullCredentialProvider` returns empty dict (default for
      SandboxType.NONE)
- [ ] Credentials flow into `SandboxContext.env_vars` during launch
- [ ] `pixi run check` passes

---

### PR D: Docker ops layer + OciSandbox implementation

- Branch: `feat/oci-sandbox`

**Scope:**
- `ops/docker.py`: thin subprocess wrappers — `run()`,
  `network_create()`, `network_remove()`, `stop()`, `rm()`,
  `is_available()`, `image_exists()`
- `OciSandbox` implementation:
  - `wrap_command()`: builds `docker run -it --rm
    --name agentrelay-<task_id>
    -v <worktree>:<worktree>
    -v <signal_dir>:<signal_dir>
    -v <git_dir>:<git_dir>:ro
    -e GH_TOKEN=... -e ANTHROPIC_API_KEY=...
    --network <network> -w <worktree> <image> <cmd>`
  - `setup()`: validates Docker available, creates network if needed
  - `teardown()`: stops + removes container if still running
- Git dir resolution helper: reads worktree `.git` file to find main
  repo `.git/` path
- `runtime` field on `IsolationConfig` (`"docker"` or `"podman"`) selects
  the binary
- Wire `SandboxType.OCI` into launcher

**Key files modified:**
- New: `src/agentrelay/ops/docker.py`
- New: `src/agentrelay/sandbox/implementations/oci_sandbox.py`
- `src/agentrelay/task_runner/implementations/task_launcher.py`
- `src/agentrelay/orchestrator/builders.py`

**Acceptance criteria:**
- [ ] `ops/docker.py` wrappers follow `ops/tmux.py` pattern
- [ ] `OciSandbox.wrap_command()` produces correct `docker run` string
      with all bind mounts and env vars
- [ ] Git dir resolution reads `.git` file and extracts gitdir path
- [ ] Worktree, signal dir, and `.git` dir mounted at same absolute paths
- [ ] `OciSandbox.setup()` fails fast if Docker not available
- [ ] Container name includes task_id for debuggability
- [ ] `pixi run check` passes (Docker ops tests use subprocess mocking)

---

### PR E: Docker image + network lifecycle + CLI flags

- Branch: `feat/docker-image`

**Scope:**
- `Dockerfile` for `agentrelay-agent` image:
  - Base: `ubuntu:24.04`
  - Installs: git, gh, python3, pip, node (via nodesource), npm
  - Installs: claude-code (`npm install -g @anthropic-ai/claude-code`)
  - Installs: agentrelay agent SDK
  - Runs as non-root `agent` user
- `pixi run docker-build` task for building the image
- Docker network lifecycle in `run_graph.py`:
  - Create `agentrelay-<graph_name>` network before orchestrator runs
  - Remove network after orchestrator completes (in finally block)
- `--sandbox` CLI flag: `--sandbox oci` or `--sandbox none` (global
  override)
- `--credentials` CLI flag: path to credentials file
  (default `~/.config/agentrelay/credentials.yaml`)
- Update `reset_graph.py` to clean up orphaned Docker networks/containers

**Key files modified:**
- New: `docker/Dockerfile`
- `src/agentrelay/run_graph.py` — CLI flags, network lifecycle
- `src/agentrelay/reset_graph.py` — Docker cleanup
- `pixi.toml` — `docker-build` task

**Acceptance criteria:**
- [ ] Docker image builds successfully
- [ ] Image contains git, gh, python3, node, claude-code, agent SDK
- [ ] Image runs as non-root user
- [ ] `--sandbox oci` triggers OciSandbox path
- [ ] `--sandbox none` (default) preserves current behavior
- [ ] Docker network created/destroyed around graph execution
- [ ] `reset_graph.py` cleans up Docker resources
- [ ] `pixi run check` passes

---

### PR F: Agent boundary instructions + e2e isolation test graphs

- Branch: `feat/isolation-instructions`

**Scope:**
- Agent instruction additions (role templates):
  - Isolation boundary section: "You are running in an isolated
    environment. Do not attempt to access resources outside your worktree."
  - "What to do when blocked" guidance: record ops concern, mark task
    failed with actionable reason
  - Conditional: only included when `isolation.sandbox_type != NONE`
- `IS_AI_AGENT=true` env var set on all containerized agents
- Git hooks (pre-push) that block pushes to protected branches when
  `IS_AI_AGENT=true`
- New `graphs/isolation/` e2e test category:
  - `basic_oci.yaml`: simple task with `isolation: {sandbox: oci}` —
    verify agent completes in container
  - `token_tiers.yaml`: tasks with different token tiers — verify correct
    PAT injection
  - `permission_boundary.yaml`: agent instructed to attempt out-of-scope
    action — verify it fails/reports
- Update `docs/BACKLOG.md`: mark agent isolation items as addressed
- Update `docs/ARCHITECTURE.md`: add isolation section
- Update `docs/HISTORY.md`: sprint entry

**Key files modified:**
- `src/agentrelay/agent_comm_protocol/templates.py`
- New: `graphs/isolation/` directory with test graphs
- `docs/BACKLOG.md`, `docs/ARCHITECTURE.md`, `docs/HISTORY.md`

**Acceptance criteria:**
- [ ] Agent instructions include isolation boundary guidance when sandbox
      is configured
- [ ] `IS_AI_AGENT=true` injected into container env
- [ ] E2E: `basic_oci.yaml` completes with agent in Docker container
- [ ] E2E: agent in container can read worktree, write to signal dir,
      push to task branch
- [ ] E2E: agent in container cannot merge PRs (read_only/standard PAT)
- [ ] `pixi run check` passes

---

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Git worktree `.git` file contains absolute host path | Bind mounts won't work if paths differ | Mount at same absolute path inside container |
| Docker TTY passthrough may confuse `wait_for_tui_ready()` | Agent launch hangs | Test TTY flow manually; use `--quiet` Docker flags |
| Credentials visible via `docker inspect` and agent logs | Token leakage | Document risk; future PR to scrub token patterns |
| Docker not installed on user's system | OciSandbox fails | `NullSandbox` remains default; `is_available()` check with clear error |
| Container startup latency | Slower task launch | Pre-pull image; tasks are minutes long so seconds of overhead is acceptable |
