# Sprint Notes — 2026-03-30: Max Plan OAuth in Containers

> **Status: Planning.**

## Goal

Enable containerized agents to authenticate with Anthropic using Max plan
OAuth credentials instead of a pay-per-token API key. This avoids separate
API costs when running agents in Docker containers.

## Context

Currently, containerized agents authenticate via `ANTHROPIC_API_KEY` injected
as an env var through the credential provider pipeline. To prevent Claude
Code's interactive "API key detected" prompt, the key is renamed to
`_ANTHROPIC_API_KEY` in `OciSandbox.wrap_command()`, and the Docker image's
pre-seeded `settings.json` includes an `apiKeyHelper` that echoes it.

The Max plan uses OAuth tokens stored in `~/.claude/.credentials.json`. Claude
Code reads this file natively — no `apiKeyHelper` needed. The file contains
an access token (~1 hour TTL), a refresh token, expiration timestamp,
subscription metadata, and organization UUID. Claude Code refreshes the access
token automatically when it expires, writing the updated token back to the
file.

### Key constraints

- **Token refresh requires write access**: Claude Code writes refreshed tokens
  back to `.credentials.json`. A read-only mount works if the task completes
  within the token TTL (~1 hour), but longer tasks need read-write or an
  alternative strategy.
- **Concurrent container writes**: Multiple containers sharing a read-write
  mount of the same file could corrupt tokens during concurrent refresh. For
  now, copy-on-launch (each container gets its own copy) is safer than a
  shared mount.
- **apiKeyHelper conflict**: The pre-seeded `settings.json` includes
  `apiKeyHelper`. When `.credentials.json` is present and no API key is
  injected, the helper echoes an empty string. Need to verify whether Claude
  Code falls back to `.credentials.json` when `apiKeyHelper` returns empty,
  or whether the helper must be absent entirely.
- **apiKeyHelper vs .credentials.json precedence**: Unknown whether Claude
  Code falls back to `.credentials.json` when `apiKeyHelper` is present but
  returns an empty string, or whether `apiKeyHelper` must be entirely absent
  for OAuth to work. Must verify empirically before implementation — this
  determines whether the startup script can always include `apiKeyHelper`
  (simpler) or must conditionally omit it (current plan).
- **Backwards compatibility**: API key mode must continue to work for users
  who prefer pay-per-token or don't have a Max subscription.
- **File ownership**: Host file is UID 1000 (`duane`), container agent user
  is UID 1000 (`agent`). Ownership aligns — no permission issues.

### Design decisions

**Copy-on-launch, not shared mount**: Each container gets its own copy of
`.credentials.json` at startup. This avoids concurrent write corruption and
makes each container self-contained. The copy script runs alongside
`claude-trust-workdir` before the agent command.

**Conditional settings.json generation at runtime**: The Docker image's
pre-seeded `settings.json` currently bakes in `apiKeyHelper`. For OAuth,
this helper should be absent. Rather than building separate images, generate
`settings.json` at container startup:
- API key mode: include `apiKeyHelper` (current behavior)
- OAuth mode: omit `apiKeyHelper`, let Claude Code read `.credentials.json`

This can be done by a startup script (similar pattern to `trust-workdir.py`)
that writes `settings.json` based on which env vars / files are present.

**CLI flag**: `--claude-credentials <path>` on `run_graph.py` specifies the
host path to `.credentials.json`. When provided:
- `OciSandbox` copies the file into the container at startup
- `settings.json` is generated without `apiKeyHelper`
- `ANTHROPIC_API_KEY` in the credentials YAML `defaults` is ignored

When not provided, the current API key flow is unchanged.

---

## PR plan

### PR A: OAuth credential support for containerized agents

- Branch: `feat/oauth-containers`

**Scope:**

1. **Startup script** (`docker/framework/claude-code/setup-credentials.py`):
   - Runs at container startup, before the agent command
   - Generates `~/.claude/settings.json` conditionally:
     - If `_ANTHROPIC_API_KEY` env var is set and non-empty: include
       `apiKeyHelper` (API key mode)
     - Otherwise: omit `apiKeyHelper` (OAuth mode — Claude Code reads
       `.credentials.json` natively)
   - Always includes `skipDangerousModePermissionPrompt: true`
   - Replaces the build-time pre-seeded `settings.json`

2. **Dockerfile update** (`docker/framework/claude-code/Dockerfile`):
   - Add `setup-credentials.py` to image at `/usr/local/bin/claude-setup-credentials`
   - Remove the `apiKeyHelper` from the pre-seeded `settings.json` (the
     startup script handles it at runtime)
   - Keep other pre-seeded config (`statsig.json`, `.claude.json`)

3. **OciSandbox changes** (`src/agentrelay/sandbox/implementations/oci_sandbox.py`):
   - Accept optional `claude_credentials_path: Path | None` in constructor
   - When set, mount the file read-only into the container at
     `/tmp/.claude-credentials.json`
   - Add a startup step that copies from the mount to
     `~/.claude/.credentials.json` (so the agent owns the file and can
     refresh tokens)
   - Skip the `ANTHROPIC_API_KEY` → `_ANTHROPIC_API_KEY` rename when OAuth
     credentials are provided (no API key to rename)

4. **CLI + wiring**:
   - Add `--claude-credentials` flag to `run_graph.py`
   - Pass through to `build_standard_runner()` → `OciSandbox` constructor
   - When both `--credentials` (PAT YAML) and `--claude-credentials` are
     provided, the PAT YAML supplies `GH_TOKEN` per tier while OAuth
     supplies Anthropic authentication

5. **Unit tests**:
   - `OciSandbox` with OAuth path: verify mount added, `_ANTHROPIC_API_KEY`
     not injected, copy command prepended
   - `OciSandbox` without OAuth (API key mode): verify unchanged behavior
   - Startup script: test settings.json generation for both modes
   - CLI flag parsing and wiring

**Key files modified:**
- `src/agentrelay/sandbox/implementations/oci_sandbox.py`
- `src/agentrelay/run_graph.py`
- `src/agentrelay/orchestrator/builders.py`
- `docker/framework/claude-code/Dockerfile`
- New: `docker/framework/claude-code/setup-credentials.py`

**Acceptance criteria:**
- [ ] `--claude-credentials` flag accepted by `run_graph.py`
- [ ] OAuth mode: `.credentials.json` copied into container, `apiKeyHelper`
      absent from settings, agent authenticates via OAuth
- [ ] API key mode: unchanged behavior (apiKeyHelper present, key injected)
- [ ] Concurrent containers each get independent credential copies
- [ ] `pixi run check` passes
- [ ] E2E: `basic_oci.yaml` with `--claude-credentials` completes
      successfully using Max plan authentication

---

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Claude Code ignores `.credentials.json` when `apiKeyHelper` returns empty | Agent has no Anthropic auth | Startup script ensures `apiKeyHelper` is absent in OAuth mode, not just empty |
| Token expires mid-task (>1 hour) | Agent loses auth | Copy is read-write so Claude Code can refresh. Docker network allows outbound HTTPS to Anthropic auth servers |
| Refresh token becomes invalid | All containers fail | Refresh token has long TTL. User re-authenticates on host (`claude` login), gets new `.credentials.json` |
| Multiple containers refresh simultaneously | Stale tokens on host file | Containers use independent copies, not shared mount. Host file is unmodified |
