# agentrelaysmall — Project Context

## What We're Building

A lightweight custom multi-agent orchestration system for coding workflows. The core idea: a Python orchestrator manages a graph of tasks, each of which runs as a Claude Code instance in its own tmux pane and git worktree. We are deliberately keeping this simple and building incrementally.

## Key Design Decisions

- **No frameworks** — built directly on the Anthropic API and subprocess calls, not LangChain/LangGraph/CrewAI
- **Async Python** — `asyncio` for concurrent task dispatch; agent calls are I/O-bound so async is a natural fit
- **Tmux for agent visibility** — agents launched interactively via `claude` (not `claude -p`) in tmux panes so we can watch them work
- **Git worktrees for isolation** — each task gets its own worktree and branch; no filesystem race conditions
- **Sentinel files for signaling** — agents communicate status by writing files to `.workflow/signals/<task-id>/` (e.g. `.done`, `.failed`, `.needs-human`, `.needs-review`, `.in-progress`)
- **Agent creates the PR** — the worktree agent has the context to write a meaningful PR description; it creates the PR then touches `.done`

## Current Code

### TaskStatus and AgentTask

```python
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

class TaskStatus(Enum):
    PENDING = "pending"       # deps not yet satisfied
    READY = "ready"           # deps done, can be dispatched
    RUNNING = "running"
    NEEDS_REVIEW = "needs_review"
    DONE = "done"
    FAILED = "failed"

@dataclass
class TaskState:
    status: TaskStatus = TaskStatus.PENDING
    worktree_path: Path | None = None
    branch_name: str | None = None
    tmux_session: str | None = None
    pane_id: str | None = None        # tmux pane ID e.g. "%3" — stable, never renumbered
    pr_url: str | None = None
    result: Any = None
    error: str | None = None
    retries: int = 0

@dataclass(frozen=True)
class AgentTask:
    id: str
    description: str
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    state: TaskState = field(default_factory=TaskState)
```

`AgentTask` is frozen (immutable identity); all mutable progress lives in `TaskState`.

### Tmux Launch

```python
import subprocess, asyncio
from pathlib import Path

TMUX_SESSION = "agentrelaysmall"

def launch_in_tmux(task: AgentTask) -> str:
    pane_id = (
        subprocess.check_output([
            "tmux", "new-window",
            "-t", TMUX_SESSION,
            "-n", task.id,
            "-P", "-F", "#{pane_id}",
            "-c", str(task.state.worktree_path),
        ])
        .decode()
        .strip()
    )
    subprocess.run(["tmux", "send-keys", "-t", pane_id, "claude", "Enter"])
    # TODO: wait for Claude to initialize, then send task description
    # subprocess.run(["tmux", "send-keys", "-t", pane_id, task.description, "Enter"])
    return pane_id

async def wait_for_sentinel(task: AgentTask, poll_interval: float = 2.0) -> str:
    sentinel = Path(f".workflow/signals/{task.id}/.done")
    while not sentinel.exists():
        await asyncio.sleep(poll_interval)
    return sentinel.read_text()
```

**Note:** `pane_id` (e.g. `%3`) is the only stable tmux identifier — window indices renumber when windows close. Always use pane_id for programmatic targeting.

### Worktree Creation (Python, not agent)

```python
def create_worktree(task_id: str, base_branch: str = "main") -> Path:
    path = Path(f"worktrees/{task_id}")
    branch = f"task/{task_id}"
    subprocess.run(["git", "worktree", "add", "-b", branch, str(path), base_branch], check=True)
    return path

def remove_worktree(path: Path):
    subprocess.run(["git", "worktree", "remove", str(path)], check=True)
```

## Signal Directory Structure

```
.workflow/
  signals/
    task_001/
      .in-progress     # written at task start
      .done            # written by agent on success (may include PR URL)
      .failed          # written by agent on failure
      .needs-human     # agent hit an ambiguity
      .needs-review    # done but wants human eyes before downstream tasks start
```

Signal files should contain a timestamp and brief note, not just be empty.

## Typical Task Lifecycle

1. Orchestrator detects task is READY (all deps DONE)
2. Python creates git worktree + branch
3. Python creates tmux window, launches `claude` interactively
4. Claude Code prompt is sent via `send-keys`
5. Agent does work, creates PR, writes `.done` sentinel
6. Orchestrator polls for sentinel, confirms completion
7. Orchestrator merges PR (or flags for human review)
8. Orchestrator closes tmux pane, removes worktree

## What's Next (Incremental Plan)

- [ ] Single hardcoded AgentTask — get one agent running end-to-end, sentinel working
- [ ] Two tasks with dependency — work out context passing and polling loop
- [ ] Extract TaskGraph with `_refresh_ready()` and async dispatch loop
- [ ] Add semaphore for bounded parallelism
- [ ] Automate worktree creation/teardown
- [ ] Add trust-prompt automation (`Enter` keystroke after Claude initializes)

## Notes

- Keep things simple. Add abstraction only when you feel real friction, not anticipated friction.
- The orchestrator is single-threaded async — no locks needed on TaskState.
- For CPU-heavy work use `asyncio.run_in_executor()`; LLM calls are pure I/O so plain async is fine.
- When prompting agents, pass dep results via a `context.md` file in the worktree rather than inlining large content into the prompt string.