# Landscape Research: agentrelay — Similar Projects & Deep Dives

## Context

agentrelay is a lightweight, declarative workflow framework for multi-agent Claude Code task pipelines. Its distinctive design combines: **YAML workflow specs**, **DAG execution**, **verification gates between steps**, **retry with context accumulation**, **sentinel-file signaling**, **state tracking**, and **audit logging**. This document catalogs the landscape of similar projects.

---

## Tier 1: Most Architecturally Similar

These projects share the most design DNA with agentrelay.

### Kestra
- **URL**: https://github.com/kestra-io/kestra
- **Source**: Open source (Apache 2.0) | **Maker**: Kestra (VC-backed startup)
- **What it does**: Declarative, event-driven orchestration platform. Workflows defined entirely in YAML. Kestra 1.0 added AI Agent tasks that combine LLMs, memory, and tools within YAML-defined DAGs.
- **Overlap**: YAML-first workflow definitions, DAG execution, 500+ plugins, event-driven triggers, version-controllable specs. Nearly identical design philosophy to agentrelay's YAML approach.
- **Difference**: Large Java-based platform designed for data/infra pipelines first, AI agents bolted on. Not Claude Code-specific. Enterprise-scale, not lightweight/exploratory.
- **Status**: Very active. Kestra 1.0 GA.

### LangGraph (LangChain)
- **URL**: https://github.com/langchain-ai/langgraph
- **Source**: Open source | **Maker**: LangChain Inc.
- **What it does**: Graph-based agent orchestration. Workflows modeled as directed graphs with state flowing between nodes. Supports checkpoints, human-in-the-loop via `interrupt()`, and durable execution with resume-from-failure.
- **Overlap**: Checkpoints (analogous to Gates), state management, retry, conditional routing, human-in-the-loop.
- **Difference**: Code-first Python (not YAML-declarative). Model-agnostic, not Claude Code-specific.
- **Status**: Very active. Dominant framework in the space. 2.2x faster than CrewAI in benchmarks.

### Microsoft Agent Framework (AutoGen + Semantic Kernel)
- **URL**: https://github.com/microsoft/agent-framework
- **Source**: Open source | **Maker**: Microsoft
- **What it does**: Merged AutoGen + Semantic Kernel. Supports **declarative YAML/JSON workflow definitions** that are version-controllable. Graph-based runtime enables declarative workflow execution. Supports both LLM-driven and deterministic orchestration.
- **Overlap**: YAML/JSON declarative agent configs, DAG execution, handoff orchestration, version-controllable specs.
- **Difference**: Deeply Azure-integrated, enterprise-focused, multi-language (C#, Python, Java). Not Claude Code-specific.
- **Status**: Public preview. GA targeted Q1 2026.

### Julep AI
- **URL**: https://github.com/julep-ai/julep
- **Source**: Open source | **Maker**: Julep AI
- **What it does**: Serverless platform for agent-based workflows. **Defines multi-step tasks in YAML or JSON.** Built-in persistent state management, retries, conditional logic.
- **Overlap**: YAML workflow definitions, state management, retry capabilities. Julep's creators explicitly advocate YAML as the universal language for AI agent workflows.
- **Difference**: Hosted/serverless (not local-first). No Gate/sentinel-file vocabulary. Not Claude Code-specific.
- **Status**: Active.

### Oracle Open Agent Specification
- **URL**: https://github.com/oracle/agent-spec
- **Source**: Open source | **Maker**: Oracle
- **What it does**: Framework-agnostic **declarative language** (JSON/YAML) for defining agentic systems. Defines agents, flows, nodes, tools. Aims for portability across frameworks.
- **Overlap**: Most philosophically aligned spec effort -- creating a universal declarative language for agent workflows.
- **Difference**: A spec, not a runtime. No Gates, Signals, or retry-context-accumulation. More abstract/ambitious.
- **Status**: Active. Published as arXiv paper.

---

## Tier 2: Claude Code-Specific Multi-Agent Tools

These target the same platform (Claude Code) but take different approaches.

### claude-flow (ruvnet)
- **URL**: https://github.com/ruvnet/claude-flow
- **Source**: Open source (TypeScript/WASM) | **Maker**: Individual developer
- **What it does**: 60+ specialized agents in coordinated swarms. Shared memory, consensus, smart model routing, stream-json agent-to-agent communication. 250k+ lines, ~100k monthly active users.
- **Overlap**: Claude Code multi-agent orchestration with dependency management.
- **Difference**: Maximalist approach vs. agentrelay's minimalist/exploratory one. Code/config-driven, not YAML-declarative with explicit Gates.
- **Status**: Very active. V3 rebuild completed.

### Oh My Claude Code (OMC)
- **URL**: https://github.com/Yeachan-Heo/oh-my-claudecode
- **Source**: Open source | **Maker**: Individual developer
- **What it does**: Teams-first orchestration layer. 32 specialized agents, 40+ skills, smart model routing. Zero learning curve -- natural language task description.
- **Overlap**: Claude Code multi-agent orchestration.
- **Difference**: Natural-language-driven (no YAML specs). No formal gate/checkpoint concepts.
- **Status**: Active. v4.1.7+.

### Gas Town (Steve Yegge)
- **URL**: https://github.com/steveyegge/gastown
- **Source**: Open source (Go) | **Maker**: Steve Yegge
- **What it does**: Coordinates 20-30 parallel AI coding agents using tmux. Workers play one of seven defined roles. Claims 12,000 lines of code daily.
- **Overlap**: Multi-agent coding coordination with defined roles.
- **Difference**: Maximalist parallelism, tmux-based, no YAML specs or gates.
- **Status**: Active. Released Jan 2026.

### ccswarm
- **URL**: https://github.com/nwiizo/ccswarm
- **Source**: Open source (Rust) | **Maker**: Individual developer
- **What it does**: Multi-agent orchestration with Git worktree isolation. Session persistence, task delegation, terminal UI.
- **Overlap**: Shares Git worktree isolation pattern.
- **Difference**: Runtime orchestrator (Rust TUI), not declarative workflow framework.
- **Status**: Active/experimental.

### multiclaude (Dan Lorenc)
- **URL**: https://github.com/dlorenc/multiclaude
- **Source**: Open source | **Maker**: Individual developer
- **What it does**: Autonomous Claude Code instances that coordinate, compete, and collaborate. "Brownian ratchet" philosophy -- merge everything that passes CI.
- **Overlap**: Git worktree-per-agent pattern.
- **Difference**: Philosophically opposite control model -- emergent vs. agentrelay's structured/gated approach.
- **Status**: Active/experimental.

### wshobson/agents
- **URL**: https://github.com/wshobson/agents
- **Source**: Open source | **Maker**: Individual developer
- **What it does**: 112 specialized agents, 16 workflow orchestrators, 146 skills organized into 72 plugins for Claude Code.
- **Overlap**: Structured workflows (Context -> Spec -> Implement).
- **Difference**: Plugin-based architecture, much larger scope, not YAML-spec-driven.
- **Status**: Active.

### Claude Code Agent Teams (Official)
- **URL**: https://code.claude.com/docs/en/agent-teams
- **Source**: Proprietary (built into Claude Code) | **Maker**: Anthropic
- **What it does**: One session acts as team lead coordinating teammates with shared task lists and dependency tracking.
- **Overlap**: The native platform agentrelay builds on top of.
- **Difference**: Low-level coordination primitive. No YAML specs, no gate concept, no structured retry logic.
- **Status**: Experimental. Feature-flagged.

### Claude Agent SDK (Official)
- **URL**: https://github.com/anthropics/claude-agent-sdk-python
- **Source**: Open source | **Maker**: Anthropic
- **What it does**: Official library for building AI agents. Supports subagents with parallel execution and isolated context windows.
- **Overlap**: Foundation for multi-agent Claude systems.
- **Difference**: General-purpose SDK, not a workflow framework. No YAML, gates, or retry-with-context.
- **Status**: Active.

---

## Tier 3: Durable Execution Platforms (Industrial-Strength Analogues)

These provide the enterprise-grade versions of agentrelay's state/retry/audit capabilities.

### Temporal.io
- **URL**: https://github.com/temporalio/temporal
- **Source**: Open source (MIT) + managed cloud | **Maker**: Temporal Technologies
- **What it does**: Durable execution platform. Every interaction captured in deterministic workflows. Automatic replay and state restoration. Append-only Event History. OpenAI Agents SDK integration.
- **Overlap**: State tracking, retry, audit logging -- all at industrial scale. Event History = agentrelay's audit log.
- **Difference**: General-purpose workflow engine requiring significant infrastructure. Code-first, not YAML. Not AI-agent-specific.
- **Status**: Extremely active. Just raised $300M (Feb 2026).

### Inngest
- **URL**: https://github.com/inngest/inngest
- **Source**: Open source + managed | **Maker**: Inngest Inc.
- **What it does**: Event-driven durable step functions. `step.ai.infer()` for LLM calls with built-in retries, timeouts, observability.
- **Overlap**: Step-level retry and durability, traceability.
- **Difference**: Serverless-oriented, event-driven. No state machine or gate semantics.
- **Status**: Active.

### Hatchet
- **URL**: https://github.com/hatchet-dev/hatchet
- **Source**: Open source | **Maker**: Hatchet (YC W24)
- **What it does**: Task orchestration with both declarative DAGs and procedural child spawning. Sub-20ms latency. Resume-from-failure. Explicit AI agent support.
- **Overlap**: Declarative DAGs, retry, resume-from-failure, agent support.
- **Difference**: General-purpose task queue, not YAML-declarative or state-machine-based.
- **Status**: Active. YC-backed.

### Trigger.dev
- **URL**: https://github.com/triggerdotdev/trigger.dev
- **Source**: Open source (TypeScript) | **Maker**: Trigger.dev
- **What it does**: Durable, long-running tasks with retries, queues, observability. CRIU for checkpoint-resume. Human-in-the-loop workflows.
- **Overlap**: Checkpoint-resume, retry, human-in-the-loop (similar to gate escalation levels).
- **Difference**: Managed execution platform, not a workflow definition framework.
- **Status**: Active. V4 GA.

---

## Tier 4: General Multi-Agent Frameworks

Broader multi-agent frameworks that overlap with parts of agentrelay's design.

| Project | Maker | Source | Key Feature | agentrelay Overlap |
|---------|-------|--------|-------------|-------------------|
| **CrewAI** | CrewAI Inc. | Open | Role-based agents, Flows for sequential/parallel | Task assignment, workflow patterns |
| **OpenAI Agents SDK** | OpenAI | Open | Handoffs, guardrails | Handoff = relay; guardrails ~ gates |
| **Google ADK** | Google | Open | Sequential/Parallel/Loop workflow agents | DAG patterns |
| **AWS Strands Agents** | AWS | Open | Model-driven, multi-agent primitives | Agent coordination |
| **PydanticAI** | Pydantic team | Open | Durable execution, graph-based flow, HITL | State tracking, retry |
| **smolagents** | Hugging Face | Open | Minimalist (~1000 lines), hierarchical agents | Lightweight philosophy |
| **Agno (Phidata)** | Agno | Open | High-performance, AgentOS control plane | Agent orchestration |
| **Mastra** | Mastra (YC) | Open | TypeScript, workflows, memory, Studio | Workflow orchestration |
| **Letta (MemGPT)** | Letta AI | Open | Stateful agents, self-editing memory | State persistence |
| **DSPy** | Stanford NLP | Open | Declarative LLM pipeline programming | Declarative philosophy |
| **MetaGPT** | FoundationAgents | Open | Software company simulation (5 roles) | Multi-agent coding pipeline |

---

## Tier 5: Commercial Coding Agent Products

These are closed-source products with multi-agent capabilities.

| Product | Maker | Multi-Agent Feature | Notable |
|---------|-------|-------------------|---------|
| **Devin 2.0** | Cognition | Dispatch sub-tasks to other Devins | Blog post: "Don't Build Multi-Agents" |
| **Cursor 2.0** | Anysphere | Up to 8 parallel agents in git worktrees | Custom RL-trained Composer model |
| **Augment Code** | Augment | Intent workspace for multi-agent orchestration | #1 SWE-Bench Pro |
| **GitHub Copilot** | GitHub/Microsoft | Coding Agent (issue -> PR), Agent Mode | Multi-model (Copilot, Claude, Codex) |
| **OpenAI Codex** | OpenAI | Multiple parallel agents in isolated copies | GPT-5.3-Codex, 1M+ developers |
| **Factory Droids** | Factory | Agents across IDE to CI/CD | #1 Terminal Bench, $50M Series B |
| **Cosine Genie** | Cosine AI | End-to-end coding with proprietary model | Genie 2.1, strong SWE-Lancer |
| **Windsurf** | Windsurf | Cascade agent with deep codebase awareness | Formerly Codeium |
| **Amp** | Amp Inc. | Autonomous agent, thread sharing | Spun out of Sourcegraph Dec 2025 |
| **Qodo** | Qodo | Multi-agent code quality (judge agent) | Highest F1 on code review benchmark |
| **Zencoder** | Zencoder | Zenflow: spec-driven multi-agent with verification gates | Closest commercial match to agentrelay |
| **Verdent AI** | Verdent | Planner/Coder/Verifier three-agent pattern | Uses git worktrees, 76.1% SWE-bench |
| **Codegen** | Codegen (ClickUp) | Ticket-to-PR, unlimited parallel agents | Acquired by ClickUp |

---

## Tier 6: Workflow Engines with AI Adaptations

Traditional pipeline tools that have added AI agent support.

| Project | Maker | YAML? | AI Agents? | Overlap |
|---------|-------|-------|------------|---------|
| **Conductor** | Netflix/Orkes | JSON | Yes (native LLM, human approval) | DAG + gates + retry + audit |
| **Prefect + ControlFlow** | Prefect | No (Python) | Yes (ControlFlow) | Retry, logging, observability |
| **Windmill** | Windmill Labs (YC) | Yes | Yes (AI agent steps) | YAML + DAG + AI agents |
| **Airflow** | Apache | No (Python) | Minimal | Conceptual ancestor of DAG model |
| **Flyte 2.0** | Union.ai | No (Python) | Checkpoint/retry for agents | Crash-proof workflows |
| **Dagster** | Dagster Labs | No (Python) | MCP server bridge | Asset-centric lineage |
| **n8n** | n8n GmbH | No (visual) | Yes (LangChain nodes) | Visual DAG + HITL |
| **AWS Step Functions** | AWS | JSON (ASL) | Yes (Bedrock) | State machines + retry |

---

## Tier 7: Research & Emerging

| Project | Focus | Relevance |
|---------|-------|-----------|
| **GitHub Agentic Workflows** | YAML frontmatter -> GitHub Actions DAGs for AI agents | YAML + DAG for agents in CI/CD (Feb 2026, very new) |
| **AgentCoder** | Programmer/Tester/Executor three-agent loop | Iterative refinement with feedback (research) |
| **MapCoder** | Retrieval/Planning/Coding/Debugging four-agent cycle | Multi-agent coding pipeline (ACL 2024) |
| **SWE-EVO** | Benchmark for long-horizon multi-agent software evolution | 21 files/task average (Dec 2025) |
| **StateFlow** | FSM-controlled LLM with Verify state | State machine + verification gate (research) |
| **AuditableLLM** | Hash-chain audit trail with rollback checkpoints | Audit logging with integrity (research) |
| **Stately Agent** | XState-based state machine LLM agents | Formal state machine + agents |
| **Burr** | Apache project, state machine framework for agents | State machine + telemetry + persistence |
| **Loki Mode** | Multi-provider, checkpoint every 5s, circuit breakers | Retry/checkpoint closest to agentrelay pattern |

---

## Key Takeaway

**No single project combines all of agentrelay's design elements** (YAML-declarative specs + DAG execution + explicit state machines + verification gates + retry-with-context-accumulation + sentinel-file signaling + audit logging) in a purpose-built package for Claude Code agents.

The closest projects by different dimensions:
- **YAML workflows**: Kestra, Julep, Microsoft Agent Framework, Windmill
- **Gates/checkpoints**: LangGraph, Temporal, Conductor
- **Claude Code-specific**: claude-flow, OMC, Agent Teams
- **Retry with context**: Temporal, Loki Mode, Hatchet
- **Lightweight/exploratory**: smolagents, Stately Agent, Burr
- **Spec-driven verification**: Zencoder Zenflow (commercial)

The market is massive and growing fast (Gartner: 1,445% surge in multi-agent system inquiries Q1 2024 -> Q2 2025), but agentrelay's specific niche -- a lightweight, study-oriented framework treating multi-agent Claude Code coordination as a first-class concern with explicit YAML-defined verification gates -- remains unoccupied.

---

## Strategic Analysis: Build vs. Buy, and Pluggability

### 1. Should you use an existing tool instead of building agentrelay?

**Short answer: No — and the reasoning is stronger than "no good alternatives exist."**

#### The gap argument

From the landscape survey, no existing tool delivers the specific combination:
- Lightweight Python (not Java, not TypeScript/WASM, not a hosted service)
- Declarative YAML workflow specs (not code-first graphs)
- Explicit verification gates as first-class vocabulary (not bolt-on conditionals)
- Claude Code-native (not model-agnostic with Claude as a plugin)
- Exploratory/research orientation (not production enterprise tooling)

The closest candidates all have disqualifying properties:
- **LangGraph**: Code-first Python. Every routing decision is either a Python function or an LLM API call. No YAML. Actively fast-moving codebase with reported breaking changes.
- **Kestra**: Java, 500+ plugins, data-pipeline-first. Heavyweight in the extreme.
- **claude-flow**: 250,000+ lines of TypeScript and WASM. Exactly the opposite of "lightweight."
- **Temporal**: Requires Elasticsearch, a database, multiple worker processes. Massive infrastructure dependency.

#### The "simplicity scales" argument

The user's instinct is well-founded and historically validated. Simple, file-based, text-readable workflows (think Makefiles, shell scripts, YAML CI configs) outlast frameworks with heavy abstractions because:
- They're debuggable by reading files in a text editor
- They have no runtime surprise from third-party version bumps
- They can be understood and modified without framework expertise
- Their failure modes are visible (a file exists or it doesn't; a JSON is valid or it isn't)

agentrelay's sentinel-file signaling and YAML specs fit this pattern. A `.workflow/signals/step-2-complete.json` either exists or it doesn't. You don't need a LangGraph debugger to understand the state of the system.

#### The "landscape velocity" argument

The agentic AI tooling space is evolving faster than almost any software domain in history. Every tool in this landscape is a moving target. The strategic question is: **what is the most durable foundation?**

- Python + files + YAML: Stable for 20+ years, will remain stable
- Claude Code (`claude -p` headless mode): Likely stable — it's Anthropic's own CLI
- LangGraph, CrewAI, AutoGen: Fast-moving, breaking changes documented, may be significantly different or superseded in 12 months
- claude-flow, OMC: Individual developers, unknown longevity

**Verdict: Building agentrelay on Python + files + YAML + Claude Code is the most durable foundation available. Adding any third-party framework increases the surface area exposed to the landscape's velocity.**

---

### 2. The pluggability question

The user identified a key architectural insight: **even if you build your own now, designing for swappability protects you later.**

#### The three layers of agentrelay

agentrelay has three separable concerns that map to three potential swap points:

```
┌─────────────────────────────────────────────────────┐
│  Layer 1: WORKFLOW SPEC                             │
│  (YAML schema, vocabulary: Steps/Gates/Signals)     │
│  What should happen, in what order, with what rules │
├─────────────────────────────────────────────────────┤
│  Layer 2: ORCHESTRATION ENGINE                      │
│  (state machine, retry, gate evaluation, audit log) │
│  How to manage the execution of the spec            │
├─────────────────────────────────────────────────────┤
│  Layer 3: AGENT EXECUTION                           │
│  (runs `claude -p`, reads CLAUDE.md, writes files)  │
│  Who does the actual work                           │
└─────────────────────────────────────────────────────┘
```

#### Where agentrelay's unique value lives

The **Workflow Spec (Layer 1)** is the intellectual contribution. The vocabulary — Steps, Gates, Signals, Reviewers, retry-context-accumulation — is the durable, transferable artifact. It's agentrelay's "API."

The Orchestration Engine and Agent Execution are implementation details underneath the spec.

#### The elegant insight: the YAML spec IS the pluggability layer

If the YAML spec is well-designed, it becomes the stable interface:
- **Today**: agentrelay's Python interpreter runs the spec by launching `claude -p` instances
- **Tomorrow**: Someone could write a LangGraph-backed interpreter that reads the same YAML spec
- **Later**: Someone could run the spec on Temporal for large-scale production use

The spec format outlasts any particular execution engine. You don't need to explicitly "make things pluggable" — a well-designed spec is pluggable by definition.

#### Should Claude Code itself be swappable?

This is the harder question. Two possible stances:

**Stance A: Claude Code is a fixed assumption**
- agentrelay is explicitly a "framework for Claude Code workflows"
- The CLAUDE.md pattern, the `claude -p` invocation, the file-based I/O are core assumptions
- Making Claude Code swappable adds abstraction for a replacement that may never come
- Simpler, less over-engineered

**Stance B: Runner abstraction makes Claude Code one implementation**
- Define a thin `Runner` protocol: `run(step: Step, context: RunContext) -> StepResult`
- The default implementation calls `claude -p`
- Alternative implementations (Cline, OpenHands, a future competitor) require only a new class
- The abstraction cost is minimal: one interface file + one concrete implementation
- Protection against: Claude Code price changes, capability regressions, or a better tool emerging

**Recommended stance: Start with Stance A (concrete, no abstraction), then define a Generic interface once the Claude Code runner is stable.**

Phase 1: Write `runner.py` as a single, clean concrete module with a well-defined input/output boundary. No abstraction yet — just good boundaries.

Phase 2: Once the concrete runner is stable and the input/output contract is well-understood, introduce a `Generic`-based interface. Prefer `Generic` over `Protocol` because:
- Covariance/contravariance issues (the common `Protocol` headache) don't arise with `Generic`
- `Generic` encourages composition over inheritance, which improves clarity
- Type-hinting tends to be cleaner and more ergonomic

Example shape (after the concrete runner is stable):

```python
from typing import Generic, TypeVar

StepT = TypeVar("StepT")
ResultT = TypeVar("ResultT")

class Runner(Generic[StepT, ResultT]):
    def run(self, step: StepT, context: RunContext) -> ResultT:
        raise NotImplementedError
```

This gives you the benefit of Stance B with none of the upfront abstraction cost — and avoids designing the interface before the concrete implementation teaches you what the interface should look like.

#### Practical summary

| Layer | Swap target | Cost of making swappable | Recommendation |
|-------|------------|--------------------------|----------------|
| Workflow spec format | Convert YAML to another orchestrator's format | Minimal (spec is already an interface) | Already done — spec IS the interface |
| Orchestration engine | Replace Python state machine with LangGraph, Temporal, etc. | Medium (redesign state/runner/gates) | Not now; agentrelay Python is the right default |
| Agent execution | Replace `claude -p` with another coding agent | Low (isolate in runner.py) | Keep runner.py clean and well-bounded now; once stable, introduce Generic-based interface (prefer Generic over Protocol — no covariance headaches, promotes composition) |

---

## Deep Dive: LangGraph for the agentrelay Use Case

**Question:** Can LangGraph orchestrate a flow where a primary orchestrator (Claude Code) tracks workflow state, delegates test-writing and code implementation, and verifies tests pass?

### Short Answer: Yes, mostly — but with important caveats.

---

### What LangGraph can do for this use case

**1. Orchestrator pattern**

LangGraph's Supervisor pattern places one agent in charge of routing work to specialized subagents. The orchestrator can be:
- **LLM-based**: A Claude model decides which agent to route to (flexible but adds latency + cost per routing decision)
- **Deterministic**: You write Python routing functions based on state (fast, predictable, no extra LLM calls)

For agentrelay's use case, deterministic routing is the better fit — you know the workflow steps up front.

**2. State tracking**

LangGraph uses `TypedDict`-based state objects persisted at every step via a checkpointer (SQLite, Postgres, Redis, or in-memory). You can track exactly where the workflow is:

```python
class WorkflowState(TypedDict):
    current_step: int           # e.g., 3
    total_steps: int            # e.g., 5
    step_name: str              # e.g., "run_tests"
    test_code: str
    implementation_code: str
    test_results: str
    retry_count: int
    messages: Annotated[list, add]   # accumulating history
```

**3. Conditional routing based on test pass/fail**

This is LangGraph's core strength:

```python
def route_on_test_result(state) -> Literal["implementer", "end"]:
    if "FAILED" in state["test_results"]:
        if state["retry_count"] >= 3:
            return "human_review"   # escalate
        return "implementer"        # retry with context
    return "end"                    # tests pass

workflow.add_conditional_edges("test_verifier", route_on_test_result)
```

**4. Retry with context accumulation**

You can implement agentrelay's retry-context-accumulation pattern manually:

```python
def implement_with_context(state):
    if state.get("last_error"):
        # Enrich the agent's input with failure history
        state["messages"].append({
            "role": "user",
            "content": f"Previous attempt failed: {state['last_error']}. Fix it."
        })
    # ... generate implementation
```

**5. Human-in-the-loop gates**

LangGraph's `interrupt()` pauses the workflow and frees resources. The workflow can be resumed later with human input — directly analogous to agentrelay's `reviewer: human` gate level:

```python
def gate_node(state):
    interrupt(f"Review required:\n{state['implementation_code']}")
    return state

# Resume later:
graph.invoke(None, config)
```

---

### The Claude Code CLI question

LangGraph does **not** have native Claude Code CLI support. To use `claude -p` headless mode, you'd wrap it as a subprocess tool:

```python
@tool
def run_claude_code(task: str) -> str:
    result = subprocess.run(["claude", "-p", task], capture_output=True, text=True, timeout=300)
    return result.stdout
```

This works but means:
- Each Claude Code "agent" is just a tool call, not a proper subagent with its own context window
- You lose LangGraph's native agent introspection for that subprocess
- Timeout handling, output parsing, and error recovery are on you

A hybrid approach: use LangGraph for the **orchestration logic** (state, routing, checkpointing), and use Claude Code CLI calls as tool nodes in the graph.

---

### What LangGraph does NOT do well here

| Need | LangGraph reality |
|------|-------------------|
| Declarative YAML workflow spec | No — workflows are Python code |
| Native Claude Code subprocess management | No — manual subprocess wrapper |
| Sentinel-file-based signaling | No — you'd build this yourself |
| Lightweight, just-Python | Somewhat — LangGraph is a sizeable dependency |
| Stable API | Historically fast-moving; breaking changes reported |

---

### Verdict

LangGraph is a **strong foundation** if you want Python-code-defined agent orchestration with good state management and human-in-the-loop support. It covers ~60-70% of what agentrelay aims to provide.

What it doesn't give you: the declarative YAML spec philosophy, Claude Code process orchestration natively, sentinel-file signaling, or the specific Gate/Signal vocabulary. Those are exactly the gaps agentrelay is designed to fill in the Claude Code-specific context.

**agentrelay could in theory use LangGraph as an underlying execution engine**, swapping the custom Python runner/state modules for LangGraph primitives — but that would significantly increase complexity and couple the project to the LangGraph API surface.
