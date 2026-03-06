# Architectural Review: SOLID Analysis & Cleanup Opportunities
# Claude Code (claude-sonnet-4-6) — 2026-03-03

---

## SOLID Violations & Opportunities

### 1. SRP — `run_graph.py` does too much

**Problem**: The orchestrator (async loop, task dispatch, signal handling) is mixed with ~800 lines of prompt generation templates. These are completely different concerns.

**Fix**: Extract prompt builders into a dedicated `prompt_builders/` package (one module per role, or a strategy pattern). `run_graph.py` should only orchestrate — not know the content of agent instructions.

**Files affected**: [src/agentrelay/run_graph.py](../src/agentrelay/run_graph.py)

---

### 2. OCP — New roles require modifying core code

**Problem**: Adding a new `AgentRole` requires touching `_build_task_instructions()`, `validate_task_paths()`, and potentially `from_yaml()`. These are scattered `if/elif` chains.

**Fix**: A role registry / strategy pattern:
```python
class PromptStrategy(ABC):
    @abstractmethod
    def build_prompt(self, task, graph) -> str: ...
    @abstractmethod
    def validate_paths(self, task) -> list[str]: ...  # returns errors

PROMPT_STRATEGIES: dict[AgentRole, PromptStrategy] = {
    AgentRole.SPEC_WRITER: SpecWriterStrategy(),
    ...
}
```

---

### 3. DIP — High-level code depends on low-level subprocess calls (critical for pluggability)

**Problem**: The two biggest blocks of Claude-specific, tmux-specific code:

**a) Agent executor** ([task_launcher.py](../src/agentrelay/task_launcher.py) — tmux + `claude` CLI):
```python
# Currently hardcoded:
["tmux", "new-window", ...]
['claude', '--dangerously-skip-permissions', '--add-dir', ...]
```

**b) VCS/GitHub backend** ([task_launcher.py](../src/agentrelay/task_launcher.py) — git + gh):
```python
# Currently hardcoded:
["git", "worktree", "add", ...]
["gh", "pr", "merge", pr_url, "--merge"]
```

**Fix**: Two abstractions:

```python
class AgentExecutor(ABC):
    @abstractmethod
    def launch(self, cwd, task_id, signal_dir, model) -> str: ...
    @abstractmethod
    def send_prompt(self, executor_id, prompt) -> None: ...
    @abstractmethod
    def capture_output(self, executor_id) -> str: ...
    @abstractmethod
    def close(self, executor_id) -> None: ...

class TmuxClaudeExecutor(AgentExecutor): ...   # current behavior
class HeadlessExecutor(AgentExecutor): ...      # for tests
class CopilotExecutor(AgentExecutor): ...       # future
```

```python
class VCSBackend(ABC):
    @abstractmethod
    def create_worktree(self, path, branch, base) -> None: ...
    @abstractmethod
    def merge_pr(self, pr_url) -> None: ...
    @abstractmethod
    def create_pr(self, title, body, base, head) -> str: ...

class GitHubBackend(VCSBackend): ...   # current
class GitLabBackend(VCSBackend): ...   # future
```

---

### 4. ISP — `task_launcher.py` is a monolith (1,106 lines)

**Problem**: A single module mixes git operations, tmux operations, signal file I/O, and PR management. Every caller imports from this kitchen-sink.

**Fix**: Split into focused modules:
- `vcs.py` — git/worktree/branch operations
- `pr_manager.py` — PR create/merge/view/close
- `agent_executor.py` — tmux/Claude launch/prompt/log
- `signal_io.py` — read/write .done, .failed, .merged, task_context.json
- `adr.py` — ADR scanning and index writing

---

### 5. Frozen/mutable contract in `AgentTask`

**Problem**: `@dataclass(frozen=True)` but `state: TaskState = field(default_factory=TaskState)` is mutable. This is intentional but violates the stated contract and confuses readers.

**Fix**: Either drop `frozen=True` (since it isn't enforced in spirit) or separate `AgentTask` (identity, truly frozen) from a separate `TaskRun` object that holds mutable `TaskState`. The graph would hold `dict[str, TaskRun]` instead of `dict[str, AgentTask]`.

---

## Prioritized Roadmap

| Priority | Change | Scope | Why |
|---|---|---|---|
| **1** | Extract prompt builders | run_graph.py → prompt_builders/ | Unblocks new roles w/o touching orchestrator |
| **2** | `AgentExecutor` abstraction | task_launcher.py | Direct path to Copilot/Codex pluggability |
| **3** | Split task_launcher.py | 1 file → 4–5 files | Makes VCS backend extraction tractable |
| **4** | `VCSBackend` abstraction | after #3 | GitLab/Gitea support |
| **5** | Role strategy registry | run_graph.py + agent_task.py | Clean OCP fix for new roles |
| **6** | Fix AgentTask frozen/mutable | agent_task.py | Low risk, improves clarity |

**Items 1–3 are the highest leverage** — they reduce `run_graph.py` from ~950 lines to ~300, make `task_launcher.py` testable in isolation, and give you a clean seam for the pluggable harness feature in the backlog.
