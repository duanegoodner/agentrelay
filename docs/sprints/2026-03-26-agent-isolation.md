# Sprint Notes — 2026-03-26: Agent Isolation

> **Status: In progress.** PRs A–E merged (#139–#144), F1 merged (#145), Fcleanup merged (#146). Remaining: PR F2 (e2e: token_tiers, permission_boundary).

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
- Note: `SandboxType.OCI` (renamed from `CONTAINER` in PR D).

**Scope:**
- `SandboxType` enum: `NONE`, `OCI` (future: `BWRAP`)
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

### PR B: AgentFrameworkAdapter + refactor TmuxAgent command building — MERGED (#140)

- Branch: `feat/framework-adapter`
- Note: Protocol renamed from `FrameworkConfigAdapter` to
  `AgentFrameworkAdapter` (names what it is, not what it wraps).
- Design change: `TmuxAgent.from_config()` accepts pre-built `cmd: str`
  instead of adapter + sandbox directly. `TmuxTaskLauncher` orchestrates
  the adapter → sandbox pipeline — cleaner separation of concerns.

**Scope:**
- `AgentFrameworkAdapter` protocol:
  `build_command(config: AgentConfig, signal_dir: Path) -> str`
- `ClaudeCodeAdapter`: extracts command-building from
  `TmuxAgent.from_config()`
- Refactor `TmuxAgent.from_config()` to accept `cmd: str` (pre-built
  command) instead of building the command internally
- `TmuxTaskLauncher` orchestrates: `adapter.build_command()` →
  `sandbox.setup()` → `sandbox.wrap_command()` → `TmuxAgent.from_config(cmd)`
- `build_standard_runner()` wires `ClaudeCodeAdapter` + `NullSandbox` into
  launcher

**Key files modified:**
- `src/agentrelay/agent/implementations/tmux_agent.py` — `from_config()`
  accepts `cmd: str` instead of `signal_dir: Path`
- `src/agentrelay/task_runner/implementations/task_launcher.py` — gains
  `adapter`, `sandbox`, `repo_path`, `graph_name` fields
- `src/agentrelay/orchestrator/builders.py`
- New: `src/agentrelay/sandbox/core/adapters.py`,
  `src/agentrelay/sandbox/implementations/claude_code_adapter.py`

**Acceptance criteria:**
- [x] `ClaudeCodeAdapter.build_command()` produces identical command string
      to previous `TmuxAgent.from_config()`
- [x] `TmuxAgent.from_config()` with `NullSandbox` + `ClaudeCodeAdapter`
      is behaviorally identical to previous code
- [x] Command building testable independently of tmux
- [x] `pixi run check` passes (1039 tests, 7 new)
- [x] E2E regression: `diamond_4_workstreams_auto_merge.yaml` passes

---

### PR C: CredentialProvider + FileCredentialProvider — MERGED (#141)

- Branch: `feat/credential-provider`
- Note: `EnvCredentialProvider` deferred to backlog (not needed for
  initial isolation; CI/CD use case). Only `NullCredentialProvider` and
  `FileCredentialProvider` shipped.

**Scope:**
- `CredentialProvider` protocol: `resolve(tier: TokenTier) -> dict[str, str]`
- `FileCredentialProvider`: reads tiered credentials from a YAML file,
  merges `defaults` with tier-specific env vars
- `NullCredentialProvider`: returns empty dict (default for SandboxType.NONE)
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
  credential resolution via `TmuxTaskLauncher`
- Wire `NullCredentialProvider` into `build_standard_runner()` as default

**Key files modified:**
- New: `src/agentrelay/sandbox/core/credentials.py`,
  `src/agentrelay/sandbox/implementations/file_credentials.py`,
  `src/agentrelay/sandbox/implementations/null_credentials.py`
- `src/agentrelay/orchestrator/builders.py`
- `src/agentrelay/task_runner/implementations/task_launcher.py`

**Acceptance criteria:**
- [x] `FileCredentialProvider` reads YAML config and resolves token tiers
- [x] Missing tier raises clear error
- [x] `NullCredentialProvider` returns empty dict (default for
      SandboxType.NONE)
- [x] Credentials flow into `SandboxContext.env_vars` during launch
- [x] `pixi run check` passes (1061 tests, 22 new)

---

### PR D: Docker ops layer + OciSandbox implementation — MERGED (#143)

- Branch: `feat/oci-sandbox`
- Note: Renamed `SandboxType.CONTAINER` → `SandboxType.OCI` for naming
  consistency with `OciSandbox`. Added `ContainerRuntime` enum
  (`DOCKER`, `PODMAN`) to replace the raw string `runtime` field on
  `IsolationConfig`.

**Scope:**
- Rename `SandboxType.CONTAINER` → `SandboxType.OCI` across codebase
- `ContainerRuntime` enum in `config.py`, `IsolationConfig.runtime`
  changed from `Optional[str]` to `Optional[ContainerRuntime]`
- `_parse_optional_container_runtime()` in builder (same pattern as
  `_parse_optional_sandbox_type`)
- `ops/docker.py`: thin subprocess wrappers — `is_available()`,
  `image_exists()`, `network_exists()`, `network_create()`,
  `network_remove()`, `stop()`, `rm()`, `build_run_command()`
- `ops/git.py`: `worktree_git_dir()` — reads worktree `.git` file to
  find main repo `.git/` path
- `OciSandbox` implementation:
  - `wrap_command()`: builds `docker run -it --rm` with bind mounts
    (worktree, signal dir, .git dir read-only), env vars, network
  - `setup()`: validates Docker available, creates network if needed
  - `teardown()`: stops + removes container, swallows errors
- Per-task sandbox selection in `builders.py`: `_make_launcher()` factory
  inspects `IsolationConfig.sandbox_type` to choose NullSandbox or
  OciSandbox

**Key files modified:**
- `src/agentrelay/sandbox/core/config.py` — `SandboxType.OCI`,
  `ContainerRuntime` enum, `IsolationConfig.runtime` type change
- New: `src/agentrelay/ops/docker.py`
- New: `src/agentrelay/sandbox/implementations/oci_sandbox.py`
- `src/agentrelay/ops/git.py` — `worktree_git_dir()`
- `src/agentrelay/task_graph/builder.py` — `ContainerRuntime` parsing
- `src/agentrelay/orchestrator/builders.py` — per-task sandbox selection

**Acceptance criteria:**
- [x] `ops/docker.py` wrappers follow `ops/tmux.py` pattern
- [x] `OciSandbox.wrap_command()` produces correct `docker run` string
      with all bind mounts and env vars
- [x] Git dir resolution reads `.git` file and extracts gitdir path
- [x] Worktree, signal dir, and `.git` dir mounted at same absolute paths
- [x] `OciSandbox.setup()` fails fast if Docker not available
- [x] Container name includes task_id for debuggability
- [x] `pixi run check` passes (Docker ops tests use subprocess mocking)

---

### PR E: Docker image + network lifecycle + CLI flags — MERGED (#144)

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
- [x] Three-layer Docker image (base, python toolchain, claude-code framework)
- [x] Image contains git, gh, python3, pixi, claude-code, agent SDK
- [x] Image runs as non-root `agent` user
- [x] `--credentials` CLI flag wires FileCredentialProvider
- [x] Docker network created/destroyed around graph execution (OCI only)
- [x] Docker label-based container tracking (`agentrelay.graph`, `agentrelay.task`)
- [x] Graph-scoped container naming: `agentrelay-{graph}-{task}`
- [x] OciSandbox.setup() validates network (doesn't create)
- [x] `reset_graph.py` cleans up Docker containers and network
- [x] `pixi run check` passes (1123 tests, 16 new)

---

### PR F1: Agent boundary instructions + container fixes — MERGED (#145)

- Branch: `feat/isolation-instructions`

**Scope:**
- Agent instruction additions (role templates):
  - `## Isolation Boundary` section with four subsections: What You Can
    Access, What You Cannot Access, What Exists Beyond Your Boundary,
    When You Are Blocked
  - Conditional: only included when `isolation.sandbox_type != NONE`
  - `resolve_instructions()` gains `sandbox_type` parameter
- `IS_AI_AGENT=true` env var set on all containerized agents
- Git hooks (pre-push) that block pushes to protected branches when
  `IS_AI_AGENT=true`, baked into Docker base image
- Container execution fixes discovered during e2e testing:
  - `bash -c` shell wrapper for `docker run` command interpretation
  - `--group-add` with host GID for file permission compatibility
  - `.git` dir mounted read-write (needed for commits)
  - `TERM` env var injection for Claude Code TUI rendering
  - `chmod` on `/home/agent` and `.local/` for cross-UID execution
  - `safe.directory` wildcard in container git config
  - `--user` and `--group-add` params on `build_run_command()`
- New `graphs/isolation/` e2e test category:
  - `basic_oci.yaml`, `token_tiers.yaml`, `permission_boundary.yaml`
- Documentation: BACKLOG (credential mgmt, GitHub App, Anthropic strategy,
  reset gap, UID cleanup, first-run prompts), ARCHITECTURE (isolation
  section), HISTORY (PR F1 entry)

**Key files modified:**
- `src/agentrelay/agent_comm_protocol/templates.py`
- `src/agentrelay/sandbox/implementations/oci_sandbox.py`
- `src/agentrelay/task_runner/implementations/task_preparer.py`
- `src/agentrelay/ops/docker.py`
- `docker/base/Dockerfile`, `docker/framework/claude-code/Dockerfile`
- New: `docker/hooks/pre-push`
- New: `graphs/isolation/` directory with test graphs
- `docs/BACKLOG.md`, `docs/ARCHITECTURE.md`, `docs/HISTORY.md`

**Acceptance criteria:**
- [x] Agent instructions include isolation boundary guidance when sandbox
      is configured
- [x] `IS_AI_AGENT=true` injected into container env
- [x] E2E: `basic_oci.yaml` completes with agent in Docker container
- [x] E2E: agent in container can read worktree, write to signal dir,
      push to task branch
- [x] `pixi run check` passes (1148 tests)

---

### PR Fcleanup: Container e2e infrastructure fixes — MERGED (#146)

- Branch: `feat/container-e2e-cleanup`
- Depends on: PR F1

**Scope:**
Seven issues discovered during F1 e2e testing, plus additional first-run
prompt suppression discovered during Fcleanup e2e validation.

1. `reset_graph` leaves stale local branches and worktree refs
2. Container UID mismatch — agent UID 1001 vs host UID 1000
3. Claude Code first-run prompts consume kickoff in containers
4. Reset doesn't clean up Docker containers/networks from failed runs
5. Reset fails on container-created files (PermissionError)
6. E2e script coupled to target repo's pixi env
7. Git credential helper not configured in container

**Key files modified:**
- `docker/base/Dockerfile` — UID 1000, credential helper
- `docker/framework/claude-code/Dockerfile` — pre-seeded config, trust script
- `docker/framework/claude-code/trust-workdir.py` — runtime folder trust
- `src/agentrelay/ops/docker.py` — `force_rm()`, removed `user`/`group_add`
- `src/agentrelay/ops/git.py` — `worktree_prune()`, `branch_list_local()`
- `src/agentrelay/reset_graph.py` — prune, local branches, PermissionError fallback
- `src/agentrelay/sandbox/implementations/oci_sandbox.py` — env var rename,
  trust-workdir prepend, suppression env vars
- `tools/e2e_run.sh`, `tools/e2e_reset.sh`, `tools/e2e_check.sh` — `--manifest-path`

**Acceptance criteria:**
- [x] `pixi run e2e-reset` fully resets (no manual worktree prune, branch
      delete, or sudo rm needed)
- [x] Container runs as UID 1000 (`agent` user) — no `ubuntu` user
      confusion, no `sudo` needed for cleanup
- [x] Claude Code starts without interactive prompts in container
- [x] Agent can `git push` using injected `GH_TOKEN` without manual URL
      construction
- [x] E2e script runs orchestrator from agentrelay's pixi env
- [x] `pixi run check` passes (1158 tests, 10 new)
- [x] E2E: `basic_oci.yaml` completes end-to-end (39s, no manual intervention)

---

### PR F2: Remaining e2e isolation testing

- Branch: TBD (after Fcleanup)
- Depends on: PR Fcleanup

**Scope:**
- E2E: `token_tiers.yaml` — verify correct PAT injection per tier
- E2E: `permission_boundary.yaml` — verify pre-push hook blocks agent
  push to main, agent records ops concern
- Any fixes discovered during those tests
- Final acceptance criteria sign-off

**Acceptance criteria:**
- [ ] E2E: `token_tiers.yaml` completes with correct credential scoping
- [ ] E2E: agent in container cannot merge PRs (read_only/standard PAT)
- [ ] E2E: `permission_boundary.yaml` — agent records ops concern when
      push to main is blocked
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
