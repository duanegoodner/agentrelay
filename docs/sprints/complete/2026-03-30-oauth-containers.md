# Sprint Notes — 2026-03-30: Max Plan OAuth in Containers

> **Status: Complete.** PR #148 merged.

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

**CLI flag** (original plan): `--claude-credentials <path>` on `run_graph.py`
specifies the host path to `.credentials.json`.

**CLI flag** (what we shipped): During implementation, we identified that
having both `--credentials` (with `ANTHROPIC_API_KEY` in `defaults`) and
`--claude-credentials` caused a conflict — API key always won because the
startup script checks `_ANTHROPIC_API_KEY` first. To prevent accidental
billing surprises, we replaced the `--claude-credentials` path flag with
a consolidated credential model:

- The credentials YAML gains a named `anthropic` section with typed entries
  (`api_key` and `oauth`) instead of using the `defaults` section.
- `--anthropic-credential <name>` selects which entry to use. Auto-selects
  when only one entry exists. Errors clearly when multiple exist and no
  selection is made.
- Graph YAML gains `anthropic_credential: <name>` as an operational key
  (like `model`), overridden by the CLI flag.
- API key entries support `key_file` as an alternative to inline `key`,
  keeping secrets out of repo-specific YAML files.

---

## PR plan

### PR A: OAuth credential support for containerized agents — #148

- Branch: `feat/oauth-containers`

**Original scope** (5 items — startup script, Dockerfile, OciSandbox with
`claude_credentials_path`, `--claude-credentials` CLI flag, unit tests).

**Actual scope** expanded during implementation to include credential
consolidation and `key_file` support. Shipped as 5 commits:

1. **Startup script + OAuth mount** (`02bde56`):
   - `setup-credentials.py`: generates `settings.json` conditionally
     (API key mode includes `apiKeyHelper`; OAuth mode omits it)
   - Dockerfile: adds script, removes baked-in `settings.json`
   - `OciSandbox`: `claude_credentials_path` param, read-only mount,
     `claude-setup-credentials` in startup chain
   - CLI: `--claude-credentials <path>` flag wired through run_graph →
     builders → OciSandbox
   - 14 new tests (1172 total)

2. **Credential consolidation** (`2eab8e1`):
   - `CredentialType` enum (`api_key`, `oauth`) and `AnthropicCredential`
     frozen dataclass in `sandbox/core/config.py`
   - `FileCredentialProvider`: removed `defaults` section, added
     `anthropic` section parsing with `resolve_anthropic()` method
   - `OciSandbox`: replaced `claude_credentials_path: Path | None` with
     `anthropic_credential: AnthropicCredential | None`; type-aware
     injection (env var for API key, volume mount for OAuth)
   - Replaced `--claude-credentials` with `--anthropic-credential <name>`
   - Graph YAML `anthropic_credential` operational key
   - SCHEMA.md credentials section + 3 example files
   - 13 new tests (1185 total)

3. **`key_file` support** (`9926887`):
   - `api_key` entries accept `key_file` path alternative to inline `key`
   - File read at construction with tilde expansion and whitespace strip
   - 4 new tests (1189 total)

4. **Remove migration guard** (`fef9277`):
   - Removed the `defaults` section migration error (no longer needed
     after user migrated)
   - 2 tests removed (1187 total)

5. **Docs** (`7b44fa8`):
   - Sprint doc, archived previous sprint, backlog items for container
     pre-seed versioning and isolation terminal visibility

**Key files modified:**
- `src/agentrelay/sandbox/core/config.py` — `CredentialType`, `AnthropicCredential`
- `src/agentrelay/sandbox/implementations/file_credentials.py` — new YAML schema
- `src/agentrelay/sandbox/implementations/oci_sandbox.py` — credential-aware injection
- `src/agentrelay/orchestrator/builders.py` — `anthropic_credential` wiring
- `src/agentrelay/run_graph.py` — `--anthropic-credential`, operational key, resolution
- `docker/framework/claude-code/Dockerfile` — startup script, no baked-in settings
- `docker/framework/claude-code/setup-credentials.py` — new container startup script
- `docs/SCHEMA.md` — credentials YAML schema documentation
- `docs/examples/credentials-*.yaml` — 3 example credential files

**Acceptance criteria:**
- [x] `--anthropic-credential` flag accepted by `run_graph.py`
- [x] OAuth mode: `.credentials.json` copied into container, `apiKeyHelper`
      absent from settings, agent authenticates via OAuth
- [x] API key mode: `_ANTHROPIC_API_KEY` injected, `apiKeyHelper` present
- [x] Concurrent containers each get independent credential copies
- [x] `pixi run check` passes (1187 tests)
- [x] E2E: `basic_oci.yaml` with `--anthropic-credential dev_api_key`
      (API key from file) succeeds
- [x] E2E: `basic_oci.yaml` with `--anthropic-credential max_plan`
      (OAuth) succeeds

### Resolved uncertainties

- **apiKeyHelper precedence**: Confirmed empirically that `apiKeyHelper`
  must be absent (not just empty) for Claude Code to read
  `.credentials.json`. The startup script omits `apiKeyHelper` entirely
  in OAuth mode.

---

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Claude Code ignores `.credentials.json` when `apiKeyHelper` returns empty | Agent has no Anthropic auth | Startup script ensures `apiKeyHelper` is absent in OAuth mode, not just empty |
| Token expires mid-task (>1 hour) | Agent loses auth | Copy is read-write so Claude Code can refresh. Docker network allows outbound HTTPS to Anthropic auth servers |
| Refresh token becomes invalid | All containers fail | Refresh token has long TTL. User re-authenticates on host (`claude` login), gets new `.credentials.json` |
| Multiple containers refresh simultaneously | Stale tokens on host file | Containers use independent copies, not shared mount. Host file is unmodified |
| Accidental API key usage when OAuth intended | Unexpected billing | Named credential entries with explicit `--anthropic-credential` selection; error when multiple entries and no selection |
