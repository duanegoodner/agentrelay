# Guide

## Installation

### Prerequisites

- Python 3.12+
- `pixi` (https://pixi.sh) for dependency management
- `git` with support for worktrees

### Install agentrelay

```bash
# Clone the repository
git clone https://github.com/duanegoodner/agentrelay.git
cd agentrelay

# Install dependencies
pixi install
```

### Verify Installation

```bash
pixi run check   # Runs formatting, type-checking, and tests
```

### Working with pixi

Use `pixi run <task>` rather than activating a shell. This keeps environments explicit and matches how agents will work in worktrees.

```bash
pixi run test        # Run tests
pixi run format      # Format code
pixi run docs        # Serve documentation locally
```

## Repository Setup (for Target Repos)

This section describes the directory layout that orchestrator-managed projects should use.

### Directory Structure

agentrelay projects use a specific layout to support isolated task worktrees and signal coordination:

```
<project>/                          ← project root (not a git repo itself)
  .git-bare/                        ← bare git repository
  main/                             ← primary worktree (linked to .git-bare)
    .git                            ← file (not dir): gitdir: ../.git-bare/worktrees/main
    src/
    tests/
    ...
  worktrees/                        ← placeholder for task worktrees (created at runtime)
```

### Setup Procedure

#### 1. Create the project root directory

```bash
mkdir -p /data/git/<project>
```

#### 2. Clone as bare repository

```bash
git clone --bare git@github.com:<user>/<project>.git \
    /data/git/<project>/.git-bare
```

#### 3. Create the primary worktree

```bash
cd /data/git/<project>
git -C .git-bare worktree add main --track origin/main
```

#### 4. Set up fetch refspec (required for bare clones)

```bash
git -C .git-bare config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'
git -C .git-bare fetch origin
```

#### 5. Verify

```bash
cd main
git branch -a   # should show origin/main and local main tracking it
```

## Development Workflow

See `CLAUDE.md` in the project root for development guidelines, command reference, and module map.

Key commands:

```bash
pixi run test        # Run tests
pixi run typecheck   # Pyright static analysis
pixi run format      # Black + isort
pixi run check       # All three (pre-PR verification)
pixi run docs        # Serve docs locally at http://localhost:8000
```
