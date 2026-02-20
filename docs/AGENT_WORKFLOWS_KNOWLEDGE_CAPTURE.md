# Multi-Agent & Git Worktree Workflows — Knowledge Capture

> **Note:** This is a knowledge capture document from a design discussion, not an
> instructional document for an agent. The content is raw and exploratory. A
> separate, concise policy document will be derived from this after review.

---

## Table of Contents

1. [Project Infrastructure: Bare Repo + Worktrees](#1-project-infrastructure-bare-repo--worktrees)
2. [Three Approaches to Multi-Agent Work](#2-three-approaches-to-multi-agent-work)
3. [Direct vs. Indirect Orchestrator](#3-direct-vs-indirect-orchestrator)
4. [Token and Cost Comparisons](#4-token-and-cost-comparisons)
5. [CLAUDE.md as Frozen Coordination](#5-claudemd-as-frozen-coordination)
6. [Tests as the Machine-Verifiable Contract](#6-tests-as-the-machine-verifiable-contract)
7. [Two-Instance-Per-Feature TDD Pattern](#7-two-instance-per-feature-tdd-pattern)
8. [Signaling Between Agents](#8-signaling-between-agents)
9. [GitHub Actions @claude Integration](#9-github-actions-claude-integration)
10. [Scripted / Automated Claude Launches](#10-scripted--automated-claude-launches)
11. [When to Use Worktrees vs. Branch in main/](#11-when-to-use-worktrees-vs-branch-in-main)
12. [Current Approach Preference](#12-current-approach-preference)

---

## 1. Project Infrastructure: Bare Repo + Worktrees

The repo uses a bare-repo + linked-worktree pattern:

```
/data/git/chatcat/
├── .git-bare/          # bare repo — all git object data, remote origin
├── .claude/            # Claude Code project-level settings
│   └── settings.local.json
└── main/               # linked worktree on `main` branch
    └── .git            # file pointing to .git-bare/worktrees/main
```

**How bare-repo git commands work:** Commands that aren't run from within a
worktree (e.g., managing worktrees and branches at the repo level) require
specifying the git dir:

```bash
GIT_DIR=/data/git/chatcat/.git-bare git worktree list
GIT_DIR=/data/git/chatcat/.git-bare git worktree add /data/git/chatcat/phase-4 -b implementation-phase-4
```

Within a worktree, ordinary `git` commands work normally.

**Creating additional worktrees:**

```bash
GIT_DIR=/data/git/chatcat/.git-bare git worktree add /data/git/chatcat/phase-4 -b implementation-phase-4
GIT_DIR=/data/git/chatcat/.git-bare git worktree add /data/git/chatcat/phase-5 -b implementation-phase-5
```

**Removing a worktree after its branch is merged:**

```bash
GIT_DIR=/data/git/chatcat/.git-bare git worktree remove /data/git/chatcat/phase-4
```

**Updating local main after a GitHub merge:**

```bash
cd /data/git/chatcat/main
git pull origin main
```

---

## 2. Three Approaches to Multi-Agent Work

### Approach 1: Task Subagents (within a single Claude Code session)

A single Claude Code instance (the parent/orchestrator) launches subagents via
the Task tool. Each subagent:

- Runs in its own isolated context window
- Can be instructed to work within a specific worktree directory (instruction-level
  isolation, not architectural/sandbox isolation)
- Reports a summary back to the parent when done — the full subagent transcript
  does NOT flow into the parent's context, only the summary does
- Cannot communicate with other subagents directly — all coordination routes
  through the parent

**Parallel execution:** Multiple subagents can be launched simultaneously in a
single parent message. Wall-clock time is bounded by the slowest subagent.

**Best for:** Tasks with dependencies between them where the parent needs to
hand context from one result to the next task assignment.

---

### Approach 2: Independent Claude Code Instances (one per worktree)

Separate `claude` CLI processes launched in separate terminals, each working
in its own worktree on its own branch. No shared state or communication between
instances.

```bash
# Terminal 1
cd /data/git/chatcat/phase-4 && claude

# Terminal 2
cd /data/git/chatcat/phase-5 && claude
```

**You (the developer) are the coordinator.** There is no runtime coordination
mechanism between instances — coordination is done upfront via planning
documents, CLAUDE.md files, and tests.

**Best for:** Truly independent modules with no shared state requirements
(e.g., Phase 4 and Phase 5 of chatcat touch entirely different source files).

---

### Approach 3: Claude Code Agent Teams (experimental — not currently planned)

One session acts as team lead; it spawns teammates that are full independent
Claude Code instances. Teammates share a task list with automatic coordination
and file locking, and can message each other.

**Not using this approach because:**
- Experimental — session resume does not restore teammates
- Higher token cost (each teammate has a full, persisting context)
- More complex; independent instances cover the same ground with less overhead

---

## 3. Direct vs. Indirect Orchestrator

This is the key conceptual distinction between Approach 1 and Approach 2.

### Direct Orchestrator (Approach 1)

The parent Claude session coordinates in real-time:
- Reads subagent results as they come in
- Dynamically adjusts what the next task is
- Can hand context between phases (e.g., Phase 4 schema informs Phase 5 design)
- Coordination overhead is paid in tokens (parent context grows with each task)

```
Developer
  └── Claude (orchestrator, running in chatcat root)
        ├── Subagent A → works in /data/git/chatcat/phase-4/
        └── Subagent B → works in /data/git/chatcat/phase-5/
```

### Indirect Orchestrator (Approach 2)

A planning Claude session does design work upfront and produces static
coordination artifacts:
- Per-worktree CLAUDE.md files (detailed, ephemeral — see section 5)
- Plan documents with implementation steps
- Test files defining the interface contract

Execution instances then consume these artifacts independently. The
coordination work happened in tokens (planning session) rather than at
runtime. The developer is the indirect coordinator — they trigger each
execution instance manually.

```
Developer + Planning Claude (indirect orchestrator)
  → produces: plan docs, per-worktree CLAUDE.md, tests
  → then steps back

Independent Instance A → reads artifacts, works in phase-4/
Independent Instance B → reads artifacts, works in phase-5/
```

**Currently preferred approach.** See section 12.

---

## 4. Token and Cost Comparisons

### Task Subagents vs. Independent Instances

| Factor | Approach 1 (subagents) | Approach 2 (independent) |
|--------|----------------------|--------------------------|
| Total tokens | Slightly higher (parent overhead) | Just task work, no overhead |
| Wall-clock time | Same if launched in parallel | Same if run simultaneously |
| Coordination cost | Paid in tokens (parent roundtrips) | Paid in developer time (manual) |
| Parent context growth | Grows with each subagent summary | No accumulation |
| Cross-task knowledge sharing | Parent maintains state, informs later tasks | No sharing — each instance isolated |
| Recovery from errors | Parent sees results, can retry/redirect | Developer sees results, retries manually |

**Key mechanic:** A subagent's internal work (file reads, bash output, tool
calls) stays in the subagent context. Only the final summary (~1k–10k tokens)
is added to the parent's context. This is much cheaper than the full transcript.

### Planning Model Choice

- Expensive model (Opus) for planning: high-quality plan docs that execution
  agents can follow without re-doing discovery
- Cheaper model (Sonnet/Haiku) for execution: follows the plan, runs tests,
  commits code
- Total cost can be lower despite using an expensive model for planning,
  because the planning session is one call vs. N execution sessions each
  re-discovering the architecture

---

## 5. CLAUDE.md as Frozen Coordination

### Root-level CLAUDE.md

Lives at `/data/git/chatcat/CLAUDE.md` (or `main/CLAUDE.md`). Every Claude
Code instance launched from any worktree discovers this file via parent
directory traversal. Contains:
- Project overview
- Architecture summary
- Module boundaries and interface contracts
- Worktree conventions

### Per-worktree CLAUDE.md (key insight)

Each worktree can have its own `CLAUDE.md` loaded with task-specific detail:

```
/data/git/chatcat/phase-4/CLAUDE.md  ← "Your task is X. Read only these files.
                                         The interface contract is Y.
                                         Tests are at test/test_index.py."
```

**Why worktree CLAUDE.md files can be very detailed:** They are ephemeral.
The worktree only exists until the task is done and merged. There is no
maintenance burden, no risk of bloat accumulating over time. Pack in as much
detail as useful.

**What to put in a per-worktree CLAUDE.md:**
- Exact task description
- Which files to read (and which to ignore)
- Interface contracts (function signatures, schemas, file formats)
- Commands to run (`pixi run test`, etc.)
- Success criterion (e.g., "all tests in test/test_index.py must pass")
- Things to avoid (e.g., "do not modify metadata.py")

**CLAUDE.md as a discovery-skip mechanism:** The expensive part of each
execution agent's work is the discovery phase — reading files to understand
architecture. A detailed CLAUDE.md short-circuits most of this. The planning
session pays the discovery cost once; execution agents skip it.

---

## 6. Tests as the Machine-Verifiable Contract

Key insight: implementation steps in a plan are ambiguous and can go stale.
Tests are a machine-verifiable binary signal — either they pass or they don't.

**Recommended pattern:**
- Planning session defines the interface (function signatures, schemas, CLI behavior)
- Planning session writes the tests (or specifies exactly what they must cover)
- Execution agent's only hard constraint: those tests pass
- Implementation steps in the plan are labeled "suggested approach" —
  the agent follows them unless something makes them wrong, in which case it adapts

**Plan detail is not monotonic:** There is a sweet spot. Overly prescriptive
implementation plans become stale or incorrect when the agent discovers
something unexpected. Specify *what* (interfaces, schemas, file structure)
more precisely than *how* (internal implementation logic).

**For chatcat specifically:** Phases 4–6 don't yet have tests written. The
planning session should write or specify tests before execution begins.

---

## 7. Two-Instance-Per-Feature TDD Pattern

For a single feature/phase, use two sequential Claude Code instances instead
of one. This formalizes the TDD red-green cycle with a human review checkpoint
in the middle.

```
Planning Claude (indirect orchestrator)
  → writes detailed plan doc + per-worktree CLAUDE.md
  → optionally specifies test structure

Instance 1 (test writer)  [on feature branch]
  → reads plan, writes tests against the planned interface
  → commits, pushes branch, creates PR
  → leaves PR comment: "@claude please review these tests..."
    (or just creates the PR and notifies developer)

Developer review point
  → reviews tests (with or without GitHub Actions Claude assist)
  → approves or requests changes

Instance 2 (implementor)  [same branch, picks up where Instance 1 left off]
  → runs tests (should fail — no implementation yet)
  → implements until tests pass
  → commits, pushes
```

**Why two instances instead of one:**
- Separates "what should this do?" thinking from "how to implement" thinking
- Test-writer context: understand the interface and requirements
- Implementor context: understand the tests and make them pass
- Each reads different things — context stays lean
- Natural human review checkpoint between phases

**Worktree note:** Both instances can share the same worktree/branch. This is
a handoff, not parallel work — no merge needed between them.

---

## 8. Signaling Between Agents

The "indirect" in indirect orchestrator means the developer is still in the
loop for triggering the next phase. Options to minimize friction:

### Sentinel file (recommended)

Execution agent writes a status file when it reaches a checkpoint:

```json
// .agent-status/phase-4-tests-ready.json
{
  "status": "tests-ready",
  "branch": "implementation-phase-4",
  "files": ["test/test_index.py"],
  "notes": "Tests cover search index creation and query interface."
}
```

Any subsequent Claude session reads this as its first action. Also human-readable
at a glance.

### Git commit convention

Execution agent commits with a specific message format, e.g. `tests: ready for review`.
Easy to check with `git log --oneline`. Zero infrastructure.

### inotifywait trigger (automated)

```bash
inotifywait -m /data/git/chatcat/.agent-status/ -e create |
while read dir action file; do
    if [[ "$file" == *"tests-ready"* ]]; then
        cd /data/git/chatcat/main
        claude -p "Review the tests described in .agent-status/$file"
    fi
done
```

Fires immediately without polling. Uses `claude -p` (see section 10).

---

## 9. GitHub Actions @claude Integration

A real, documented Anthropic feature. Allows `@claude` mentions in GitHub
PR and issue comments to trigger a Claude Code agent running on GitHub's
infrastructure.

**Setup (one-time per repo):**
1. Install the Claude GitHub App: `github.com/apps/claude`
2. Add `ANTHROPIC_API_KEY` to repo secrets
3. Add `.github/workflows/claude.yml` — or run `/install-github-app` from
   within a Claude Code terminal session

**What it does when triggered:**
- Reads the PR diff, issue body, and project `CLAUDE.md`
- Responds as a PR/issue comment with analysis, review, or requested changes
- Can create PRs, implement features, fix bugs when instructed

**Example comment that triggers it:**
```
@claude please review these tests against the interface contract in CLAUDE.md
```

**Important distinctions:**
- The GitHub Actions Claude is a separate cloud instance, not your local session
- Runs on GitHub's runners, not your machine
- Requires separate API billing (not covered by Claude.ai Max subscription)
- Your Max subscription covers local Claude Code CLI via OAuth — not GitHub Actions

**Cost consideration:** A moderate PR review might use 10k–50k tokens (~$0.03–$0.15
at Sonnet pricing). Not expensive per review but is separate from Max subscription.

**Alternative that avoids extra API cost:** After the test-writing instance
creates a PR, launch a local Claude Code session (covered by Max) and ask it
to review the PR branch. Same quality, manual trigger, no additional billing.

---

## 10. Scripted / Automated Claude Launches

Claude Code has a non-interactive (headless) mode:

```bash
claude -p "your prompt here"
# or
claude --print "your prompt here"
```

Runs the task, prints output to stdout, exits. No interactive session. Covered
by Max subscription (or API billing if configured that way).

**Polling loop example:**
```bash
while true; do
    if [ -f "/data/git/chatcat/.agent-status/tests-ready.json" ]; then
        cd /data/git/chatcat/main
        claude -p "Tests are ready for review. Read .agent-status/tests-ready.json for context."
        rm /data/git/chatcat/.agent-status/tests-ready.json
    fi
    sleep 60
done
```

**Cron example:**
```bash
# crontab: every 30 minutes
*/30 * * * * cd /data/git/chatcat/main && claude -p "Check for unreviewed test branches."
```

**Key considerations:**
- Each `claude -p` starts fresh with no memory of previous runs
- Working directory matters — it determines which CLAUDE.md is discovered
- `--output-format json` available for structured output in scripts
- Each invocation uses tokens (Max subscription) or API credits

---

## 11. When to Use Worktrees vs. Branch in main/

**Use a new worktree when:**
- Two or more things are genuinely in progress simultaneously
- You want to hand off a branch to a dedicated Claude Code instance that
  shouldn't be switching branches
- The task is long-running and you want main/ to stay on main branch

**Branch within main/ (standard git workflow) when:**
- Work is sequential — finish one thing before starting the next
- Simple change that doesn't need branch isolation
- You're working interactively and switching branches yourself

For most day-to-day doc and code changes: branch in `main/`, create PR,
merge, pull. No new worktree needed.

```bash
cd /data/git/chatcat/main
git checkout -b my-feature-branch
# ... make changes ...
git push -u origin my-feature-branch
gh pr create
# after merge:
git checkout main
git pull origin main
git branch -d my-feature-branch
```

---

## 12. Current Approach Preference

**Favoring: Indirect Orchestrator (Approach 2)**

Rationale:
- chatcat's remaining phases (4, 5, 6) touch largely non-overlapping source
  files — cross-agent communication at runtime is not required
- Upfront planning session can define interfaces and write tests, removing
  the main advantage of a direct orchestrator (dynamic context sharing)
- Lower complexity, no experimental features, works with existing bare repo
  + worktree setup
- Covered under Max subscription for execution instances

**Likely workflow for each remaining phase:**

1. Planning session (this session or a dedicated one) produces:
   - Per-worktree `CLAUDE.md` with full task detail
   - Test specifications or actual test files
   - Plan doc with suggested implementation steps (not prescriptive)

2. Test-writing instance launched in feature worktree:
   - Writes tests, commits, creates PR
   - Writes sentinel file or uses commit convention

3. Developer reviews tests (with optional local Claude review session)

4. Implementation instance launched in same worktree:
   - Runs failing tests, implements to pass them
   - Commits, pushes, PR merges to main

5. Worktree removed, main updated

**Not using:**
- Agent Teams (experimental, not stable enough)
- Task subagents for implementation work (no hard isolation, coordination
  benefit not needed for independent phases)
- GitHub Actions @claude (separate API cost; local review session works fine)
