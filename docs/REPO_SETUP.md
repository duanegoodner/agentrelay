# Repository Setup

This document describes the directory layout agentrelaysmall projects use and the steps to set one up from scratch. The same procedure applies to both the orchestrator repo (`agentrelaysmall`) and any target repos it drives (e.g. `agentrelaydemos`).

---

## Layout

```
<project>/                          ← container directory (not a git repo itself)
  .git-bare/                        ← bare git repository
  main/                             ← primary worktree (linked to .git-bare)
    .git                            ← file (not dir): gitdir: ../.git-bare/worktrees/main
    src/
    ...
  worktrees/                        ← placeholder for task worktrees created at runtime
  <project>.code-workspace          ← VS Code multi-folder workspace
```

Task worktrees are created at runtime under `worktrees/<graph-name>/<task-id>/` and deleted after their PR is merged. Signal files are written to `main/.workflow/<graph-name>/signals/<task-id>/` (ignored by `.gitignore`).

---

## Setup procedure

### 1. Create the container directory

```bash
mkdir /data/git/<project>
```

### 2. Clone the repo as bare

```bash
git clone --bare git@github.com:<user>/<project>.git \
    /data/git/<project>/.git-bare
```

> `git clone --bare` does **not** add a fetch refspec by default. Step 3 is required.

### 3. Add the fetch refspec

Without this, `git fetch` on the bare repo fetches nothing, and `git pull --ff-only` (used by the orchestrator after each PR merge) will not update `main`.

```bash
git -C /data/git/<project>/.git-bare \
    config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'
```

### 4. Fetch remote-tracking refs

```bash
git -C /data/git/<project>/.git-bare fetch
```

Verify: `git -C /data/git/<project>/.git-bare branch -r` should show `origin/main`.

### 5. Add the main worktree

```bash
git -C /data/git/<project>/.git-bare \
    worktree add /data/git/<project>/main main
```

Verify: `cat /data/git/<project>/main/.git` should read `gitdir: /data/git/<project>/.git-bare/worktrees/main`.

### 6. Create the worktrees directory

```bash
mkdir /data/git/<project>/worktrees
```

### 7. Create a VS Code workspace file

`/data/git/<project>/<project>.code-workspace`:

```json
{
  "folders": [
    { "name": "main", "path": "main" },
    { "name": "<project>", "path": "." }
  ]
}
```

---

## Verification checklist

```bash
# Bare repo + main worktree are linked
git -C /data/git/<project>/.git-bare worktree list
# → /data/git/<project>/.git-bare  (bare)
# → /data/git/<project>/main       <sha> [main]

# Fetch refspec is present
grep fetch /data/git/<project>/.git-bare/config
# → fetch = +refs/heads/*:refs/remotes/origin/*

# Remote-tracking refs exist
git -C /data/git/<project>/.git-bare branch -r
# → origin/main

# Pull works from the main worktree
git -C /data/git/<project>/main pull --ff-only
# → Already up to date.
```

---

## Notes

- The container directory (`/data/git/<project>/`) is **not** a git repo. Only `.git-bare/` is.
- Never run plain `git` commands from the container directory — always use `-C main` or `-C .git-bare`.
- To add the project as a target repo for an agentrelaysmall graph, set `target_repo: /data/git/<project>/main` in the graph YAML. The orchestrator's `git -C target_repo_root worktree add` will follow the `.git` file to the bare repo automatically.
- The `agentrelaysmall` pixi environment must be available in task worktrees so agents can call `WorktreeTaskRunner`. For target repos, add `agentrelaysmall = { path = "/data/git/agentrelaysmall/main", editable = true }` to the target repo's `pixi.toml`.
