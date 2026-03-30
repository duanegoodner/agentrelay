# Supplementary Info — Agent Isolation Sprint (PR Fcleanup)

Detailed descriptions of the seven issues discovered during PR F1 e2e
testing. Each section describes the problem, how it manifested, and the
impact on the e2e workflow.

---

## 1. reset_graph leaves stale local branches and worktree refs

**Problem:** `reset_graph.py` removes the worktree directory
(`shutil.rmtree`) and the workflow directory, but does not:
- Run `git worktree prune` to clean up git's worktree registry
- Delete local branches created during the run

**How it manifested:** After every `pixi run e2e-reset`, the next
`pixi run e2e` failed with:

```
_WorkspaceIntegrationError: Failed to create branch for task 'hello_fn':
  Command '['git', 'branch', '-f', '...', '...']' returned non-zero exit status 128.
```

Because git still considered the branch "used by" the now-deleted
worktree. Required manual `git worktree prune && git branch -D ...`
after every reset.

**Impact:** This was the single biggest time sink — every failed e2e
attempt required ~4 manual commands to fully clean up.

**Fix direction:** Add `git worktree prune` and local branch deletion
(all branches matching `agentrelay/<graph>/*`) to `reset_graph.py`'s
`execute_reset()` function, after the directory removal step.

**Relevant code:** `src/agentrelay/reset_graph.py` — `execute_reset()`
function, after `shutil.rmtree(plan.worktree_dir)`.

---

## 2. Container UID mismatch (agent=1001 vs host=1000)

**Problem:** The Docker image creates user `agent` with UID 1001. The
host user (`duane`) is UID 1000. Ubuntu 24.04 base images include a
pre-existing `ubuntu` user at UID 1000.

Bind-mounted directories (worktree, signal dir) are created by the host
user (UID 1000) with mode 0775. The container's `agent` user (UID 1001)
is not in the host user's group, so it cannot write to these directories.

**How it manifested:** Agent got `EACCES: permission denied` when trying
to write files, commit, or write signal files (`.done`, `.failed`,
`ops_concerns.log`).

**Current workaround:** `--group-add` with host GID gives the container
process supplementary group access to host-owned directories. This works
for the forward direction (container writing to host dirs) but not the
reverse (host cleaning up container-created files — see item 5).

**Impact:** Required multiple iterations to diagnose. The `--user`
approach (running as host UID) fixed permissions but broke the Claude
Code TUI rendering and the HOME directory resolution.

**Fix direction:** In the Dockerfile, remove the `ubuntu` user
(`userdel ubuntu`) and create `agent` with UID 1000. This aligns UIDs
so no `--group-add` or `--user` workarounds are needed, and
container-created files are owned by the host UID.

**Relevant code:**
- `docker/base/Dockerfile` — user creation
- `src/agentrelay/sandbox/implementations/oci_sandbox.py` — `--group-add`
  in `wrap_command()`

---

## 3. Claude Code first-run prompts consume kickoff in containers

**Problem:** Every container launch triggers Claude Code's interactive
first-time setup prompts:
- API key confirmation
- Folder trust confirmation
- Possibly other first-run dialogs

Because containers are ephemeral (`--rm`), every run is a "first time."
The orchestrator sends the kickoff prompt ("Read instructions.md and
follow the steps exactly.") via `tmux send-keys`, but this text is
consumed by the startup prompts before Claude Code's main input is ready.

**How it manifested:** Claude Code launched and completed its startup
prompts, then sat waiting for input. The orchestrator showed "waiting for
completion signal" indefinitely. Required manual entry of the kickoff
prompt.

**Impact:** Every e2e run required manual interaction — negates the
automation value of the orchestrator for containerized agents.

**Fix direction (in priority order):**
1. **Suppress interactive prompts**: Investigate Claude Code CLI flags or
   env vars that skip first-run setup. Pre-seed config files in the
   image (e.g., write `~/.claude/settings.json` with trust and API key
   confirmation during `docker build`).
2. **Pass prompt as CLI argument**: Use `claude -p "Read ..."` or
   `claude --prompt "..."` instead of tmux send-keys, bypassing the
   timing issue.
3. **Container warm-up step**: Run Claude Code briefly in
   `OciSandbox.setup()` to complete first-run initialization before the
   real task launches.

**Relevant code:**
- `src/agentrelay/agent/implementations/tmux_agent.py` —
  `send_kickoff()` (line 85)
- `src/agentrelay/sandbox/implementations/claude_code_adapter.py` —
  command construction
- `docker/framework/claude-code/Dockerfile` — could pre-seed config

---

## 4. Reset doesn't clean up Docker containers/networks from failed runs

**Problem:** When an e2e run fails mid-execution (e.g., the agent
crashes, the orchestrator is killed with Ctrl+C, or a container error
occurs), Docker containers may still be running and the Docker network
may still exist. The next `pixi run e2e` fails because:
- The container name is already in use
- The network already exists (though `run_graph.py` handles this better
  now)

`reset_graph.py` has Docker cleanup logic (added in PR E / #144) that
stops/removes containers by label and removes the network. However, this
cleanup is best-effort and can miss containers that exited but weren't
removed (no `--rm` didn't apply, or the container was killed).

**How it manifested:** After Ctrl+C'ing a stuck run, the next attempt
sometimes failed with network or container name conflicts.

**Impact:** Required manual `docker stop` / `docker rm` / `docker
network rm` between attempts.

**Fix direction:** Make the reset Docker cleanup more robust:
- Always run `docker ps -a --filter label=agentrelay.graph=<name>` and
  force-remove all matching containers
- Always attempt network removal
- Add Docker cleanup to the e2e-reset script as well (currently only in
  `reset_graph.py`)

**Relevant code:**
- `src/agentrelay/reset_graph.py` — Docker cleanup section
- `tools/e2e_reset.sh` — could add Docker cleanup

---

## 5. Reset fails on container-created files (PermissionError)

**Problem:** Files created inside the container by the `agent` user (UID
1001) are owned by UID 1001 on the host filesystem. When `reset_graph.py`
tries to `shutil.rmtree()` the worktree directory, it fails with
`PermissionError` on these files because the host user (UID 1000)
doesn't have write permission to UID 1001-owned files.

**How it manifested:**
```
PermissionError: [Errno 13] Permission denied:
  '.worktrees/isolation-basic-oci/default/.pixi'
```

Required `sudo rm -rf` to clean up.

**Impact:** Every reset after a partially successful run required sudo.

**Fix direction:** This is largely resolved by fixing item 2 (UID
alignment). If the container runs as UID 1000, all files it creates are
owned by UID 1000, and the host user can delete them normally.

As a defense-in-depth measure, `reset_graph.py` could also catch
`PermissionError` during `rmtree` and log a warning with instructions
(or attempt cleanup via `docker run --rm -v ... rm -rf ...` using the
container runtime itself).

**Relevant code:** `src/agentrelay/reset_graph.py` — `execute_reset()`,
`shutil.rmtree()` calls.

---

## 6. E2e script coupled to target repo's pixi env

**Problem:** `tools/e2e_run.sh` (line 71) does:
```bash
cd "$TARGET_REPO"
exec pixi run python -m agentrelay.run_graph "$GRAPH_ABS" "$@"
```

This runs the orchestrator via the *target repo's* pixi environment,
which requires `agentrelay` to be installed as a dependency in the target
repo's `pixi.toml`. If the target repo removes or changes that
dependency, the orchestrator breaks.

**How it manifested:** After temporarily removing the agentrelay path
dependency from agentrelaydemos' `pixi.toml` (to fix an in-container
pixi error), the e2e script itself broke:
```
ModuleNotFoundError: No module named 'agentrelay'
```

Required reverting the target repo change to restore orchestrator
functionality.

**Impact:** The target repo's dependency management is tightly coupled to
the orchestrator's ability to run. Changes to the target repo can break
the orchestrator.

**Fix direction:** Change `e2e_run.sh` to run the orchestrator from the
agentrelay repo's pixi environment instead:
```bash
cd "$TARGET_REPO"
exec pixi run --manifest-path "$REPO_ROOT/pixi.toml" \
  python -m agentrelay.run_graph "$GRAPH_ABS" "$@"
```

Or set `PIXI_PROJECT_MANIFEST` to point to the agentrelay repo. The
target repo's pixi env is only needed by agents (inside containers or
worktrees), not by the orchestrator.

Similarly update `e2e_reset.sh` and `e2e_check.sh`.

**Relevant code:**
- `tools/e2e_run.sh` — line 71
- `tools/e2e_reset.sh` — similar pattern
- `tools/e2e_check.sh` — similar pattern

---

## 7. Git credential helper not configured in container

**Problem:** The container has `GH_TOKEN` injected as an env var, and
`gh auth status` shows authentication is working (gh CLI reads
`GH_TOKEN`). However, git push/pull over HTTPS doesn't use `GH_TOKEN`
automatically — it needs a credential helper configured.

**How it manifested:** The agent's `git push` failed:
```
fatal: could not read Username for 'https://github.com': No such device
or address
```

The agent worked around this by manually constructing the URL:
```bash
git push "https://x-access-token:$GH_TOKEN@github.com/owner/repo.git" branch
```

This works but is fragile and relies on the agent being clever enough to
figure it out.

**Impact:** The agent wasted cycles diagnosing the push failure and
constructing the workaround URL. A less capable model might fail the
task entirely.

**Fix direction:** Configure `gh` as the git credential helper in the
Docker image:
```dockerfile
RUN gh auth setup-git
```

Or configure git to use `GH_TOKEN` directly:
```dockerfile
RUN git config --global credential.helper \
  '!f() { echo "username=x-access-token"; echo "password=$GH_TOKEN"; }; f'
```

The `gh auth setup-git` approach is cleaner — it configures the
credential helper to use whatever auth `gh` has (which reads `GH_TOKEN`
from the environment automatically).

**Relevant code:**
- `docker/base/Dockerfile` — git/gh configuration
- Possibly `src/agentrelay/sandbox/implementations/oci_sandbox.py` if
  the setup needs to happen at runtime rather than build time
