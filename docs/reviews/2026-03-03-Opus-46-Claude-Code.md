# Architectural Review: SOLID Analysis & Cleanup Opportunities
# Claude Code (claude-opus-4-6) — 2026-03-03

---

## Part 1: SOLID Analysis

### Executive Summary

The codebase (~2,800 LOC across 7 production files) is well-structured for its current size —
clean data models, good test coverage, and sensible conventions. But two files dominate
complexity ([task_launcher.py](../src/agentrelaysmall/task_launcher.py) at 1,105 lines and
[run_graph.py](../src/agentrelaysmall/run_graph.py) at 952 lines), and the code is tightly
coupled to specific external tools (Claude CLI, tmux, git+GitHub). The backlog goal of making
the agent backend pluggable requires addressing these structural issues first.

---

### 1. SRP: `task_launcher.py` is a god module

[task_launcher.py](../src/agentrelaysmall/task_launcher.py) has at least 6 distinct
responsibilities in one flat collection of 30+ functions:

| Concern | Example functions | Lines (approx) |
|---------|-------------------|----------------|
| Git worktree/branch ops | `create_worktree`, `remove_worktree`, `create_graph_branch`, `pull_main`, `list_remote_task_branches`, `reset_target_repo_to_head` | ~250 |
| Tmux window management | `launch_agent`, `send_prompt`, `_wait_for_claude_tui`, `save_agent_log`, `close_agent_pane` | ~170 |
| GitHub PR operations | `create_final_pr`, `merge_pr`, `pixi_toml_changed_in_pr`, `save_pr_summary`, `append_concerns_to_pr` | ~200 |
| Signal file I/O | `write_task_context`, `write_context`, `write_instructions`, `write_merged_signal`, `read_done_note`, `poll_for_completion` | ~200 |
| ADR scanning | `scan_adr_section`, `write_adr_index_to_graph_branch`, `_extract_front_matter_field` | ~170 |
| Run tracking + gates | `record_run_start`, `read_run_info`, `run_completion_gate`, `record_gate_failure`, `neutralize_pixi_lock_in_pr`, `run_pixi_install` | ~120 |

**Recommendation:** Split into focused modules — `git_ops.py`, `terminal_ops.py`,
`github_ops.py`, `signal_io.py`, `adr_ops.py`. Each module gets its own responsibility
and can evolve independently.

---

### 2. SRP: `run_graph.py` mixes orchestration with prompt generation

[run_graph.py](../src/agentrelaysmall/run_graph.py) is ~950 lines, roughly half of which are
prompt template strings embedded in Python code:

- `_build_spec_writer_prompt` (~75 lines)
- `_build_test_writer_prompt` (~55 lines)
- `_build_test_reviewer_prompt` (~50 lines)
- `_build_implementer_prompt` (~75 lines)
- `_build_generic_instructions` (~100 lines)
- `_build_merger_prompt` (~55 lines)

Plus helpers: `_resolve_gate`, `_build_context_content`, `_adr_step`, `_spec_reading_step`,
`_effective_verbosity`.

**Recommendation:** Extract to a `prompt_builder.py` module. The orchestrator loop
(`_run_task`, `_run_graph_loop`, `main`) stays in `run_graph.py` as pure coordination logic.
Prompt-building is already tested independently in
[test_run_graph.py](../test/test_run_graph.py).

---

### 3. OCP + DIP: No abstraction boundary for the agent backend

This is the critical issue for the pluggability goal. The agent launch sequence is hardcoded
to Claude CLI + tmux across multiple functions:

- [task_launcher.py](../src/agentrelaysmall/task_launcher.py) `launch_agent()` — hardcodes `tmux new-window` + `claude --dangerously-skip-permissions`
- `_wait_for_claude_tui()` — polls for "bypass permissions" text specific to Claude TUI
- `send_prompt()` — uses `tmux send-keys`
- `save_agent_log()` — uses `tmux capture-pane`
- `close_agent_pane()` — uses `tmux kill-window`

To support Copilot/Codex/Gemini, a protocol-based abstraction is needed:

```python
class AgentHarness(Protocol):
    """Abstraction over how a coding assistant is launched and communicated with."""

    def launch(self, task_id: str, cwd: Path, model: str | None,
               signal_dir: Path, session_name: str) -> str:
        """Launch an agent. Returns an opaque handle for later operations."""
        ...

    def send_prompt(self, handle: str, prompt: str) -> None: ...

    def capture_log(self, handle: str) -> str: ...

    def close(self, handle: str) -> None: ...

    def is_ready(self, handle: str, timeout: float) -> bool: ...
```

`ClaudeCodeTmuxHarness` implements this with the current tmux+claude logic. A future
`CopilotHarness` or `CodexHarness` implements the same interface with different mechanics.

---

### 4. DIP: Orchestrator depends on concrete implementations

[run_graph.py](../src/agentrelaysmall/run_graph.py) imports 26 concrete functions from
`task_launcher` at the top of the file. Any change to how git/tmux/GitHub works requires
touching both the launcher and the orchestrator. The orchestrator should depend on
abstractions, not a bag of 26 free functions.

**Recommendation:** Group operations behind protocol-based service objects injected into
the orchestrator:

```python
@dataclass
class Orchestrator:
    graph: AgentTaskGraph
    harness: AgentHarness          # agent launch/communication
    vcs: VCSOperations             # git worktree/branch ops
    code_host: CodeHostOperations  # PR create/merge/view
    signals: SignalStore           # signal file read/write
```

---

### 5. OCP: Adding a new `AgentRole` requires modifying existing code

The prompt dispatch in `run_graph.py` is an if/elif chain that must be extended for every
new role. Similarly, `validate_task_paths()` has role-specific if/elif chains.

**Recommendation:** Registry dict mapping `AgentRole` to a prompt builder callable. New roles
can be registered without modifying existing dispatch code:

```python
PROMPT_BUILDERS: dict[AgentRole, PromptBuilder] = {
    AgentRole.SPEC_WRITER: build_spec_writer_prompt,
    AgentRole.TEST_WRITER: build_test_writer_prompt,
    # ...
}
```

---

### 6. ISP: `TaskState` couples agent-backend-specific state into the core model

[agent_task.py](../src/agentrelaysmall/agent_task.py) `TaskState`:

```python
@dataclass
class TaskState:
    status: TaskStatus = TaskStatus.PENDING
    worktree_path: Path | None = None
    branch_name: str | None = None
    tmux_session: str | None = None    # tmux-specific
    pane_id: str | None = None          # tmux-specific
    pr_url: str | None = None
    ...
```

`tmux_session` and `pane_id` are tmux-specific details that won't apply to other harnesses.
These should move behind the `AgentHarness` abstraction — the harness tracks its own handles
internally, and `TaskState` retains only orchestrator-level concerns (status, PR URL, retries).

---

### Prioritized Roadmap (SOLID only)

| Priority | Change | SOLID principle | Why this order |
|----------|--------|----------------|----------------|
| 1 | Extract `prompt_builder.py` from `run_graph.py` | SRP | Pure move, no behavior change; makes run_graph.py readable |
| 2 | Split `task_launcher.py` into focused modules | SRP, ISP | Prerequisite for introducing protocols |
| 3 | Define `AgentHarness` protocol + extract `ClaudeCodeTmuxHarness` | DIP, OCP | The pluggability enabler |
| 4 | Remove tmux-specific fields from `TaskState` | ISP | Clean separation once harness exists |
| 5 | Introduce `VCSOperations` / `CodeHostOperations` protocols | DIP | Enables non-GitHub hosting |
| 6 | Registry-based prompt dispatch + path validation | OCP | Nice-to-have extensibility |

---

## Part 2: Class Encapsulation Opportunities

Reviewing the codebase through the lens of repeated parameter groups and feature envy
reveals five clear places where free functions should become classes.

---

### A. `(graph_name, target_repo_root)` — passed together 16 times

This is the biggest offender. Functions across
[task_launcher.py](../src/agentrelaysmall/task_launcher.py) and
[reset_graph.py](../src/agentrelaysmall/reset_graph.py) — `pull_graph_branch`,
`create_final_pr`, `record_run_start`, `read_run_info`, `list_remote_task_branches`,
`delete_local_graph_branch`, `graph_branch_exists_on_remote`, `merge_history_path`,
`record_gate_failure`, `scan_adr_section`, `write_adr_index_to_graph_branch`,
`_close_open_prs`, `_remove_workflow_dir` — all take the same pair.

**Missing class:** Something like `GraphRepo` — initialized with `graph_name` and
`target_repo_root`, with all these operations as methods. This is distinct from
`AgentTaskGraph` (the in-memory task DAG); `GraphRepo` owns the on-disk git/GitHub
operations for a graph run.

---

### B. `(task, graph_branch, graph)` — the prompt builder trio, 6 functions

Every `_build_*_prompt` in [run_graph.py](../src/agentrelaysmall/run_graph.py) takes
`(task: AgentTask, graph_branch: str, graph: AgentTaskGraph | None = None)` and then calls
the same helpers (`_adr_step`, `_spec_reading_step`, `_resolve_gate`, `_effective_verbosity`)
which read the same fields from `task` and `graph`.

**Missing class:** `PromptBuilder` — initialized with `task`, `graph_branch`, and `graph`.
Shared helpers become methods. The role-specific builders dispatch via a dict registry.
This also naturally hosts the role→builder registry from the OCP finding above.

---

### C. `signal_dir: Path` — constructed, then passed 10+ times

The signal dir path `target_repo_root / ".workflow" / graph_name / "signals" / task_id` is
computed in the orchestrator and then threaded through to `write_context`,
`write_instructions`, `save_agent_log`, `poll_for_completion_at`, `read_done_note_at`,
`read_design_concerns`, `save_pr_summary`, etc.

Note: `AgentTaskGraph.signal_dir()` is already the single source of truth for computing the
path — the issue is that the operations on that directory are scattered free functions.

**Missing class:** `SignalDirectory` — wraps a `Path` and provides the read/write methods.
Thin, but it eliminates the repeated `signal_dir` parameter threading and centralizes file
conventions (`.done`, `.failed`, `.merged`, `context.md`, `instructions.md`).

---

### D. `task: AgentTask` passed just to read `task.state.pane_id` — 4 functions

- `save_agent_log(task, signal_dir)` — reads only `task.state.pane_id`
- `close_agent_pane(task)` — reads only `task.state.pane_id`
- `remove_worktree(task, target_repo_root)` — reads only `task.state.worktree_path` and `task.state.branch_name`
- `neutralize_pixi_lock_in_pr(task)` — reads only `task.state.worktree_path` and `task.state.branch_name`

Classic feature envy — these functions want `TaskState` fields, not the full `AgentTask`.
This resolves naturally when tmux/pane operations move into `AgentHarness` (priority 3 above)
and worktree operations become methods on a worktree manager. The agent handle replaces
passing the whole task object.

---

### E. `pr_url: str` — threaded through 5+ functions

`merge_pr`, `pixi_toml_changed_in_pr`, `append_concerns_to_pr`, `save_pr_summary`, and the
merger prompt builder all take a PR URL and shell out to `gh pr ...`. A `PRHandle` class
(initialized with the URL, and optionally the parsed owner/repo/number) would consolidate
these and eliminate the URL-parsing duplication.

---

### Updated Prioritized Roadmap (SOLID + class encapsulation)

| Priority | Change | Addresses |
|----------|--------|-----------|
| 1 | Extract `PromptBuilder` class from `run_graph.py` | SRP + Finding B |
| 2 | Split `task_launcher.py` into modules, extracting `GraphRepo` (A), `SignalDirectory` (C), `PRHandle` (E) | SRP + ISP + Findings A/C/E |
| 3 | Define `AgentHarness` protocol + extract `ClaudeCodeTmuxHarness` | DIP + OCP + resolves Finding D |
| 4 | Remove tmux-specific fields from `TaskState` | ISP |
| 5 | `VCSOperations` / `CodeHostOperations` protocols | DIP |
| 6 | Registry-based prompt dispatch | OCP |

Steps 1–2 are pure refactors with no behavior change. The class extractions make step 3
(the pluggability enabler) much cleaner because the harness protocol boundary is obvious —
it wraps the tmux functions that were already grouped together.
