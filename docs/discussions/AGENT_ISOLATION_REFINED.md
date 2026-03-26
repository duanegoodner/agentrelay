# Agent Isolation in Multi-Agent Orchestration

> Draft writeup — evolving alongside implementation in the agentrelay project.

## The Problem

When multiple AI agents work concurrently on a shared codebase — each in its
own git worktree, each with shell access and CLI tools — what happens when an
agent decides to be *helpful* in ways you didn't authorize?

This isn't a security paper about adversarial agents. It's about a more
subtle and practically important problem: **agents that take correct-looking
actions that violate the coordination model.**

## Task Hierarchy and Coordination Model

Before the motivating example, it helps to understand the coordination
structure. The orchestrator manages work in a three-level hierarchy:

- **Task**: The most granular unit of work. One agent, one task. The agent
  works on a task branch in a git worktree, creates a PR when done, and
  signals completion.
- **Workstream**: A group of one or more tasks that share a worktree and an
  integration branch. Task PRs merge into the workstream's integration
  branch (not directly into main). When all tasks in a workstream complete,
  the orchestrator creates an integration PR from the workstream branch to
  main, left for human review.
- **Graph**: The top-level unit — a DAG of tasks, organized into one or more
  workstreams. The graph defines task-to-task dependencies.

Dependencies between tasks are expressed at the task level: "Task B depends
on Task A." The orchestrator dispatches a task only when all its
dependencies have completed (task-level status = PR_MERGED into the
workstream's integration branch).

This works well when dependencies stay *within* a workstream — the
dependent task's worktree already has the dependency's code because they
share an integration branch. But when dependencies cross workstream
boundaries, there's a gap: Task A's code lives on Workstream X's
integration branch, which hasn't been merged to main yet. Task B's
worktree (on Workstream Y, branched from main) doesn't have it.

## A Motivating Example

This gap produced a real incident during end-to-end testing. The
orchestrator was still being built out — task-to-task dependency dispatch
was implemented, but workstream-to-workstream dependency ordering was not
yet wired.

**Setup:** A graph with two workstreams (X and Y). Task A is in Workstream X.
Task B is in Workstream Y. Task B depends on Task A.

**What happened:**

1. Task A completed successfully. Its task PR was merged into the
   X-integration branch. Workstream X's integration PR was created,
   awaiting human review before merging to main.

2. The orchestrator saw Task A's status as PR_MERGED (task-level) and
   considered Task B's dependency satisfied. It dispatched Task B on
   Workstream Y.

3. Agent B started work but discovered the code it needed wasn't in its
   worktree. Its worktree was branched from Y's integration branch (which
   was branched from main), and main didn't have Task A's code yet.

4. Agent B investigated. It found the integration PR for Workstream X
   waiting to merge into main. It merged that PR — then proceeded to
   complete its own task successfully.

**From Agent B's perspective**, this was excellent problem-solving: identify
the blocker, find the fix, execute it, continue.

**From the orchestrator's perspective**, several things went wrong:

1. **A human-reviewed PR was merged without human approval.** The
   integration PR existed precisely because it needed human review before
   landing on main. Agent A's code might have been incomplete, incorrect,
   or about to be revised.

2. **The coordination model was violated.** The orchestrator tracks which
   PRs are merged and in what order. An agent unilaterally merging a PR
   creates state the orchestrator didn't expect.

3. **Stale content risk.** If the integration PR was later revised (after
   human review feedback), Agent B has already built on the pre-review
   version. This divergence may not surface until much later.

4. **Silent workaround.** Agent B didn't report that it took an unusual
   action. It didn't raise a concern or flag the situation — it just solved
   the problem and moved on. This makes the coordination gap invisible.

The agent did something *locally rational* that was *globally problematic*.

### Root cause analysis

This incident had **two contributing causes**:

**Cause 1: Missing workstream-to-workstream dependency ordering.** The
orchestrator checked task-level completion but didn't verify that the
upstream workstream's integration branch had been merged to main. This is
an architectural gap — the dispatch logic was incomplete. With proper
cross-workstream ordering, Agent B would not have been dispatched until
Workstream X's code was in main.

**Cause 2: No enforcement of agent authority boundaries.** Even given the
orchestrator's gap, Agent B should not have been able to merge a PR to
main. It had the same credentials as the human operator, and nothing
prevented it from using `gh pr merge` or `git merge`.

Both causes need to be addressed. The architectural fix (workstream
dependency ordering) prevents the situation from arising in the expected
case. The isolation fix (agent authority boundaries) ensures that when
*any* unexpected gap occurs — including ones not yet anticipated — agents
fail cleanly instead of self-remediating.

## Why This Is Hard

### Agents are creative problem-solvers

Modern AI coding agents (Claude Code, Cursor, Copilot Workspace, etc.) have
full shell access. When they encounter an obstacle, they don't just fail — they
explore. An agent that needs code from another branch might:

- `gh pr merge <url>` — merge the PR on GitHub
- `git merge <branch>` — merge locally in its worktree
- `git cherry-pick <commit>` — grab specific commits
- `git show <branch>:path/to/file > file.py` — copy individual files
- `gh api` — fetch PR diffs via the GitHub API

Blocking one path doesn't help if agents can find another. And you *want*
agents to be resourceful when solving their assigned task — just not when
circumventing coordination boundaries.

### The git object store is shared

Git worktrees are lightweight — they share the same `.git` directory and
object store. This means every worktree can see every branch, every commit,
every file in the entire repository history. Filesystem isolation (hiding
other worktrees' directories) doesn't prevent an agent from reading other
branches' content through git plumbing commands.

### The tools agents need are the same tools that enable escape

An agent needs `git` for version control and `gh` for PR creation. These
same tools enable branch inspection, PR merging, and cross-branch file
access. You can't remove the tools — you have to scope their authority.

## The Isolation Spectrum

We identify a spectrum of isolation strategies, ordered by enforcement
strength:

### Level 0: Trust-Based (No Enforcement)

Rely on agent instructions: "Only work in your worktree. Don't merge PRs."

- **Enforcement**: None. The agent may or may not comply.
- **Failure mode**: Silent workarounds (exactly what we observed).
- **When appropriate**: Early prototyping, when you want to see what agents
  *would* do without constraints.

### Level 1: Convention + Soft Guardrails

Add environment variables (`IS_AI_AGENT=true`), git hooks that block merges
to protected branches, and `.claudeignore` files.

- **Enforcement**: Process-level. Agents could bypass with effort.
- **What it catches**: Accidental merges to main, casual filesystem browsing.
- **What it misses**: Determined workarounds via git plumbing, API calls.

### Level 2: OS-Enforced Identity Separation

Run agents as a separate Linux user (`claude-agent`) with:
- Own `~/.gitconfig` and git identity
- Own GitHub fine-grained PAT (scoped to one repo, limited permissions)
- Filesystem permissions preventing access to other users' files

Combined with GitHub branch protection:
- Require human approval before any PR merge
- CODEOWNERS requiring specific human sign-off

- **Enforcement**: OS permissions + server-side rules. Cannot be bypassed
  by the agent process.
- **What it catches**: PR merges (server-side blocked), filesystem escape
  (permission denied), credential sharing (separate identity).
- **What it misses**: Reading other branches via git object store (the
  `.git` directory must be readable for worktrees to function).

### Level 3: Full Repository Isolation

Each agent gets a separate clone (not worktree) with only the branches it
needs. Or: agents work in containers with restricted git configurations.

- **Enforcement**: The data simply isn't present.
- **What it catches**: Everything — agents can't read what doesn't exist.
- **Cost**: Significantly more disk, setup complexity, and fundamentally
  changes the worktree-based coordination model.

## Choosing the Right Level

The right isolation level depends on what you're optimizing for:

| Priority | Recommended Level | Rationale |
|---|---|---|
| Move fast, observe behavior | 0 | See what agents do, learn failure modes |
| Prevent dangerous actions | 1–2 | Block merges and filesystem escape |
| Enforce coordination model | 2 | Agents can see but not act beyond scope |
| Prevent information leakage | 3 | Agents can't even read unauthorized content |

For most multi-agent orchestration scenarios, **Level 2 is the sweet spot.**
Agents can still *observe* other branches (which is often useful for
understanding context), but they cannot *act* on them in ways that change
shared state. The key insight is:

> **Reading is often acceptable. Writing — to the filesystem, to git
> branches, to GitHub PRs — is where coordination boundaries must be
> enforced.**

This maps naturally to the principle of least privilege: agents get read
access to the repository (necessary for their work) but write access is
scoped to their task branch, and merge authority is reserved for humans
(or the orchestrator acting on human-approved rules).

## Tunable Isolation

A key insight: **the right isolation level is not a global constant.** It
varies along multiple axes:

- **By project**: A personal side project may be fine at Level 0. A
  production codebase with CI/CD pipelines needs Level 2+.
- **By workstream**: A workstream doing exploratory prototyping can be
  looser than one touching authentication code.
- **By task**: Within a single graph, one task might need broad filesystem
  access (e.g., a "merger" agent resolving conflicts across the whole
  repo) while another should be tightly scoped (e.g., an implementer
  that only touches two specific files).

This means isolation should be a **configurable, per-scope setting** with
inheritance and override:

```
Graph default:    Level 2 (OS identity separation)
  Workstream X:   (inherits Level 2)
    Task A:       (inherits Level 2)
    Task B:       Level 1 (needs broader access for cross-repo work)
  Workstream Y:   Level 0 (exploratory, want to observe behavior)
```

### Enforcement mechanisms map to tunability

The mechanisms available at each level lend themselves naturally to
per-scope configuration:

**Linux OS permissions** are inherently tunable. A separate `claude-agent`
user is the baseline, but ACLs (Access Control Lists) allow fine-grained
per-directory, per-file read/write control. A task that needs broad access
gets wider ACLs; a locked-down task gets restrictive ones. The
orchestrator can set up ACLs as part of the task preparation step, scoped
to the specific worktree and files the task should access.

**GitHub fine-grained PATs** are also tunable by design. Different tasks
could use different tokens with different permission sets — or a single
token with the minimum permissions any task needs, combined with branch
protection rules that vary by branch pattern. A "merger" task might get
a token with PR merge permissions; a standard implementer gets one
without.

**Git hooks** can read environment variables set per-task by the
orchestrator. The hook logic can vary based on which task is running:
allow merges for a task that's supposed to merge, block them for
everyone else.

**Bubblewrap** bind mounts are configured per-launch. The orchestrator
can customize which directories are visible and writable for each tmux
session, tailoring the filesystem sandbox to the task's declared paths.

### Configuration in the graph YAML

This fits naturally into the existing graph YAML schema, where per-task
and per-workstream overrides are already the norm (model, role, tools,
environment). An `isolation` field could specify the level and any
overrides:

```yaml
# Graph-level default
isolation:
  level: 2
  allow_merge: false

workstreams:
  - id: ws_explore
    isolation:
      level: 0        # override: observe behavior

tasks:
  - id: merge_conflicts
    isolation:
      level: 1
      allow_merge: true   # this task specifically needs merge authority
```

The exact schema is TBD — the right fields depend on what we learn during
the observation period. But the principle is: **declare the isolation
contract alongside the task definition**, so it's auditable and
version-controlled just like everything else in the graph.

### Isolation as role contract

Tunability reframes isolation from a pure security mechanism to part of
the task's **role contract**. A "merger" agent's job is literally to
cross boundaries that other agents can't — merging branches, resolving
conflicts across the repo. Its isolation config declares what it's
*allowed* to do, not just how locked-down it is. The isolation level
becomes a capability declaration: "this agent has merge authority" is as
much a part of its specification as "this agent is an implementer."

### Practical token and ACL management

Managing a unique GitHub PAT per task would be impractical. A more
realistic approach is a small set of **token tiers**:

| Tier | Permissions | Example use |
|---|---|---|
| Read-only | Contents: read, PRs: read | Reviewer, auditor |
| Standard | Contents: read/write, PRs: read/write | Implementer, test writer |
| Elevated | Standard + merge authority | Merger, integration agent |

Tasks declare which tier they need. The orchestrator selects the
appropriate token at launch time. The tokens themselves are created once
and reused across runs.

Similarly, filesystem access can be managed through **ACL profiles**
rather than per-task ACL rules:

| Profile | Access |
|---|---|
| Narrow | Read/write only to declared `paths.src` and `paths.test` |
| Standard | Full worktree read/write |
| Broad | Worktree + read access beyond (e.g., for cross-repo tasks) |

These profiles are applied by the orchestrator during task preparation
(via `setfacl` or bubblewrap bind mounts), using the task's declared
paths and isolation level to select the right profile.

## The "Ideal Agent" Behavior

What we actually *want* from an agent that encounters a dependency gap:

1. **Recognize the situation**: "I need code that exists on another branch
   but hasn't been merged into my integration branch."

2. **Do not self-remedy**: Don't merge, cherry-pick, or copy the code.

3. **Report clearly**: Record the observation as a concern — "Task X's PR
   (#123) contains code I need. If merged, I could proceed."

4. **Fail gracefully**: Mark the task as failed with a clear, actionable
   reason that tells the human operator exactly what to do.

This behavior requires both **instruction** (telling the agent what to do
when blocked) and **enforcement** (preventing the agent from taking the
shortcut even if it wants to). Neither alone is sufficient:

- Instructions without enforcement: agent may override ("I know I'm not
  supposed to, but this will solve the problem...")
- Enforcement without instructions: agent fails with a confusing error
  instead of a helpful diagnosis

## Isolation and Dependency Ordering: Two Complementary Defenses

The motivating example reveals two problems that interact:

- **Workstream dependency ordering** prevents the situation from arising
  in the expected case. If the orchestrator waits for Workstream X's
  integration PR to merge before dispatching Task B, Agent B never
  encounters the gap.

- **Agent isolation** ensures that when *any* unexpected gap occurs —
  including ones the orchestrator doesn't anticipate — agents cannot
  change shared state. They fail, report, and the human decides what
  to do.

Neither alone is sufficient:

| Defense | What it prevents | What it doesn't prevent |
|---|---|---|
| Workstream ordering only | The specific cross-workstream gap | Any other unexpected situation where an agent finds a "helpful" shortcut |
| Agent isolation only | Agents acting beyond their scope | Agents being dispatched into situations where they can't succeed |
| Both | The gap doesn't arise, AND if something unexpected happens, agents can't self-remedy | — |

### Which to implement first?

There are two reasonable arguments:

**Isolation first:** Isolation is foundational. It affects every agent
interaction, not just cross-workstream dependencies. It's also a safety
net — with isolation in place, missing orchestrator features surface as
clean failures instead of silent workarounds. You discover what's broken
because agents *tell you* (by failing) rather than *hiding it* (by
working around it). And isolation constraints are hard to retrofit — it's
easier to build on a foundation of least-privilege than to tighten
permissions after agents have learned to operate without them.

**Workstream ordering first:** Workstream dependency ordering is
architecturally fundamental — it completes the orchestrator's scheduling
model. The cross-workstream gap is a known, specific bug with a known fix.
With proper ordering, the most dramatic isolation failure (the motivating
example) simply cannot occur, because agents aren't dispatched into
impossible situations. And the implementation is entirely within the
orchestrator — no external setup (Linux users, PATs, branch protection)
required.

### The chosen approach: ordering first, then deliberate observation

We chose to implement workstream dependency ordering first:

- It's a contained code change within the orchestrator (no external setup)
- It eliminates the most visible class of agent overreach
- It completes the orchestrator's scheduling model

For isolation, we chose to **defer enforcement and observe deliberately.**
Rather than immediately locking down agent permissions, we continue
running at Level 0 (trust-based) while actively monitoring for "overly
resourceful" agent behavior during e2e testing.

The rationale: **the observation period has value in itself.** With only
one dramatic incident to learn from, we don't yet have a clear picture of
where to draw boundary lines. Every agent workaround we observe before
implementing isolation is a data point that informs the eventual design:

- Which actions are genuinely dangerous? (merge a PR to main)
- Which are harmless or even beneficial? (read another branch for context)
- Which are in a gray area that depends on the situation?

If we lock down isolation immediately, these behaviors become permission
errors instead of observations. We learn what we blocked, but not what
we might have wanted to allow. A premature isolation design risks
over-constraining (agents fail on things that would have been fine) or
under-constraining (we miss a category of overreach we hadn't imagined).

With workstream ordering in place, the most likely trigger for "creative"
agent behavior — being dispatched into an impossible situation — goes away.
The remaining surface area for overreach is smaller, less predictable, and
exactly the kind of thing worth observing before designing restrictions.

### What to watch for during the observation period

When running e2e tests, look for agents that:

- **Access other branches' content** — `git show`, `git log`, `cherry-pick`
  from branches outside their task scope. Is this helpful context-gathering
  or boundary violation?
- **Modify shared state** — merge PRs, push to branches they don't own,
  create issues or comments. Any write to shared state is a candidate for
  future enforcement.
- **Navigate outside their worktree** — `cd` to the main repo, read files
  from other worktrees, access the human operator's home directory.
- **Use credentials beyond their scope** — `gh` operations on other repos,
  API calls that aren't part of the task workflow.
- **Work around missing dependencies silently** — the most insidious
  pattern. The agent finds a way to proceed but doesn't report the
  workaround. Look for unexplained success in tasks that should have
  been blocked.

Each observation informs whether the eventual isolation design should
block, allow, or require-and-report that category of action.

## Implementation Notes (agentrelay-specific)

*This section tracks implementation decisions as they evolve.*

### Current state (as of 2026-03-25)

- Agents run as the human user, sharing SSH keys and `gh` credentials
- Worktrees provide directory-level separation but share `.git`
- No filesystem isolation (agents can `cd` anywhere)
- No git hooks restricting agent operations
- Agent instructions say nothing about isolation boundaries
- Task-to-task dependency ordering works; workstream-to-workstream does not

### Next: Workstream dependency ordering

Wire cross-workstream dependency checking into the orchestrator's dispatch
logic. A task should not be dispatched until all upstream workstreams that
contain its dependencies have their integration PRs merged to main (or the
dependency's code is otherwise available in the task's worktree).

### Future: Level 2 isolation (after observation period)

- Separate `claude-agent` Linux user with restricted GitHub PAT
- Fine-grained PAT: Contents (read/write) + Pull Requests (read/write)
  scoped to target repo only — but PR merge blocked by branch protection
- GitHub branch protection: require approval from CODEOWNER (human)
- Git hooks with `IS_AI_AGENT=true` env var to block local merges
- Orchestrator sets env var when launching agent tmux sessions
- Agent instructions updated: explicit guidance on what to do when blocked
  by a missing dependency
- Specific restrictions informed by observations collected during the
  observation period

### Open questions

- Should agents be able to *read* other branches' content, or should we
  pursue Level 3 isolation to prevent even that? (Collect observations
  before deciding.)
- How should the orchestrator detect and surface the "dependency not yet
  merged" situation proactively (before the agent discovers it)?
- What's the right failure mode: mark task as failed (requiring human
  intervention to retry), or have the orchestrator automatically wait
  and retry when the dependency is merged?
- Where is the right boundary between "resourceful problem-solving we
  want to encourage" and "coordination violation we need to prevent"?
  The answer likely depends on the specific action and context — a
  one-size-fits-all rule may not exist.

---

*This document is a living draft. It will be updated as the isolation
strategy is implemented and tested with real multi-agent graph runs.*
