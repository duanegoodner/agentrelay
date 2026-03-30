# Isolation Tests

Validate agent sandboxing, credential scoping, and permission boundaries.
All graphs require real credentials (GitHub PAT + Anthropic API key) configured
via `--credentials` for actual e2e execution.

## Graphs

| Graph | Feature | What it tests |
|---|---|---|
| `basic_oci.yaml` | Basic OCI sandbox | Agent completes task inside Docker container |
| `token_tiers.yaml` | Token tier injection | Tasks with different token tiers receive correct credentials |
| `permission_boundary.yaml` | Pre-push hook | Agent with read_only PAT cannot push to main; records ops concern |

## Running

```bash
# Preflight check
pixi run e2e-check /path/to/target-repo

# Run (requires --credentials for real PAT injection)
pixi run e2e graphs/isolation/basic_oci.yaml /path/to/target-repo --credentials ~/.config/agentrelay/credentials.yaml
pixi run e2e graphs/isolation/token_tiers.yaml /path/to/target-repo --credentials ~/.config/agentrelay/credentials.yaml --max-concurrency 2
pixi run e2e graphs/isolation/permission_boundary.yaml /path/to/target-repo --credentials ~/.config/agentrelay/credentials.yaml

# Reset
pixi run e2e-reset graphs/isolation/basic_oci.yaml /path/to/target-repo
```

## What to verify after a run

### basic_oci
- Task completes with `.done` and `.merged` signals
- Agent ran inside Docker container (check tmux pane for `docker run` command)
- PR created and merged successfully

### token_tiers
- `standard_task` receives standard-tier GH_TOKEN and can push + create PR
- `readonly_task` receives read_only-tier GH_TOKEN
- Both tasks complete (readonly can still push to task branch with read_only PAT
  if the PAT has Contents: write; adjust expectations based on actual PAT scopes)

### permission_boundary
- Agent attempts `git push origin HEAD:refs/heads/main`
- Pre-push hook blocks the push (exit 1, stderr message)
- Agent records an ops concern about the blocked push
- Agent pushes to task branch and completes normally
