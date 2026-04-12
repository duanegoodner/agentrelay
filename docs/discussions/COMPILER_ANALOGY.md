# Task Graph Lowering as Compilation — Design Discussion

> **Status: Conceptual discussion.** Captures the analogy between compiler
> pipelines and progressive task graph refinement. Not tied to a specific
> sprint or implementation plan. Intended as a framing document for future
> work on automated graph generation and multi-resolution execution.

## Core Idea

There is a structural analogy between what compilers do and what agentrelay
does. A compiler lowers from a high-level language through intermediate
representations down to machine code. agentrelay lowers from a high-level
work intent through task graphs down to actual code commits across merged PRs.

Today, agentrelay has a single graph representation — the execution-ready
TaskGraph that the orchestrator runs directly. The lowering from intent to
that graph is done entirely by the human author, in one step, outside the
system. There is no automated lowering and no sequence of progressively
refined intermediate representations.

The analogy suggests a direction: that single representation could become a
family of representations at different abstraction levels, and the manual
one-shot lowering could become a multi-pass pipeline — partially or fully
automated. The rest of this document explores what that would look like,
drawing on how compilers solve the analogous problem.

In that framing, the representation would be uniform at every level: it's
TaskGraphs all the way down. A single-node graph expressing pure intent
("build me a web scraper that does X") and a fully specified graph with
file paths, roles, and dependency edges would both be valid TaskGraphs —
differing only in abstraction level.

## The Lowering Pipeline

| Compiler stage | Task graph analog |
|---|---|
| Source code | "Build me a tool that does X" |
| AST / HIR | Single-node TaskGraph (pure intent) |
| MIR | Architectural TaskGraph (modules, responsibilities, dep edges) |
| LIR | Implementation TaskGraph (specific files, roles, tagged_paths) |
| Machine code | Committed code across merged PRs |

Each "pass" takes a TaskGraph at one level and produces a more detailed
TaskGraph at the next. This mirrors how compiler IRs work: each stage has the
same fundamental structure (basic blocks, instructions, control flow) but with
progressively lower-level operations.

## Optimization Passes

Compilers don't just lower — they optimize between lowering steps. The task
graph analog: after an architectural decomposition, a pass could analyze the
dependency structure and extract parallelism, merge tasks that are too small,
split tasks that are too large, or reorder workstreams for better throughput.

Today this is done by hand when authoring graph YAML. An automated
optimization pass could do things like: "these three tasks all touch the same
module and have no other dependents — fuse them."

## Semantic Preservation

A compiler must preserve program semantics through each lowering. The task
graph analog: each refinement must preserve the original intent. This gives a
verification criterion at each level — does this more detailed graph still
accomplish what the less detailed one described?

This is hard to check mechanically, but it's the right question to ask, and
a verification agent whose job is exactly that is a plausible component of the
pipeline.

## Front-End / Back-End Separation

Compilers separate language-specific parsing (front-end) from target-specific
code generation (back-end). agentrelay could separate intent-understanding
(what to build) from execution mechanics (how to orchestrate agents).

The current system is almost entirely back-end — it takes a concrete TaskGraph
and executes it. The front-end (going from intent to executable graph) is
currently the human. The compiler analogy suggests this is a natural place to
add automation.

## NP-Hardness and Heuristic Divergence

Several core compiler optimization problems are NP-hard or NP-complete:
register allocation (graph coloring), instruction scheduling, optimal loop
tiling, and the phase ordering problem (the order you apply optimizations
affects the outcome, and finding the optimal ordering is itself intractable).

So compilers use heuristics, and different heuristics produce different but
correct output. GCC, Clang, and MSVC generate meaningfully different machine
code from the same C source. Even within a single compiler, `-O1` vs `-O2`
vs `-O3` produce different code — all correct, different tradeoff profiles.

The invariant across all of them is **semantic preservation**, not output
identity. The correctness contract is: "this machine code does the same thing
as the source program." How it does it is a heuristic judgment call.

This narrows the gap with agent-driven lowering. The difference isn't really
"deterministic vs non-deterministic." It's more precise to say: compilers use
heuristics that happen to be deterministic (same heuristic, same input, same
output), while agents use heuristics that are stochastic. But in both cases,
the meaningful invariant is the same — does the output preserve the intent of
the input? The specific decomposition is a judgment call, not a uniquely
correct answer.

This suggests the right way to evaluate task graph lowering quality isn't "did
it produce the right graph" but "did it produce a correct graph with good
tradeoff characteristics" — exactly how we evaluate compiler output.

## Variable Lowering Depth

This is where the analogy reveals a genuinely novel property of the system.

A compiler *must* lower all the way to machine code before anything executes.
There is no option to hand the MIR to the CPU and say "figure it out." But an
agent can take a vague task description and produce working code. The agent
itself is a general-purpose lowering engine that can bridge an arbitrary
abstraction gap in a single step.

So the question isn't "how do we lower all the way down" — it's **how far
down should we lower before handing off to execution?** The answer is probably
not fixed. It likely depends on:

- **Task complexity.** A simple bug fix might be fine as a single-node graph.
  A multi-module feature probably benefits from architectural decomposition
  before execution.
- **Confidence in the decomposition.** If the architecture is well understood,
  lowering further before execution reduces agent judgment variance. If the
  right decomposition is unclear, letting an agent explore from a higher level
  might produce a better result than a premature human decomposition would.
- **Cost of getting it wrong.** More lowering = more human oversight before
  resources are spent. Less lowering = faster but higher risk of wasted work.

Compilers can't reason about this tradeoff at all, because their execution
cost is trivial — compiling the wrong way is cheap, just recompile. Agent
execution is expensive (time, tokens, API cost), so the optimal lowering depth
is an economic question, not just a correctness question.

## Transparency and the Black Box Problem

There is a subtler argument for deeper lowering that goes beyond correctness
and cost: **legibility of the build process itself.** This connects to a
broader concern: as organizations rely more heavily on AI-generated code,
there is a real risk that no human fully understands the codebase — or at
least significant parts of it. Some projects have likely already hit this
problem. The speed at which agents produce code is genuinely valuable, but
that speed can outrun human comprehension if there is no structured process
making the build legible.

When an agent executes a high-level, loosely specified graph, the lowering
still happens — the agent still makes decomposition decisions, architectural
choices, and implementation tradeoffs. But those decisions are made inside the
agent's context window and are invisible to the humans responsible for the
project. A larger portion of the software creation process becomes black-boxed.

When the TaskGraph is lowered to a more granular level before execution —
regardless of whether a human or an agent did the lowering — the intermediate
representations serve as legible artifacts. They record *what decisions were
made and why* in a form that humans can inspect, question, and learn from.
This has consequences beyond the immediate build:

- **Maintainability.** A codebase produced by a transparent, well-documented
  decomposition is easier to reason about after the fact. The graph artifacts
  explain the module boundaries, responsibility assignments, and dependency
  structure that shaped the code.
- **Extendability.** When new features need to be added, the existing graph
  history shows how prior work was decomposed, making it easier to decide
  where new work fits.
- **Reliability.** Explicit decomposition forces architectural decisions to be
  made deliberately rather than emerging as side effects of an agent's local
  choices. Deliberate decisions tend to be more consistent.

Two products built from the same high-level intent — one via a shallow graph
and one via a deeply lowered graph — might be nearly identical in initial
functionality. But the latter has a more transparent build history, and that
transparency compounds over the life of the project.

This benefit holds regardless of who performs the lowering. An especially
interesting scenario: a human provides only the highest-level graph, but
instructs the system to lower through a specified number of intermediate
levels (or down to a particular abstraction level) before beginning execution.
The human retains none of the decomposition burden but gains full visibility
into the decomposition the agent produced — and can review or redirect it
before any execution cost is incurred.

A tool like agentrelay — with explicit task graphs, dependency structure,
and intermediate artifacts — provides a framework for keeping humans in the
loop on *what is being built and why*, without sacrificing the speed at which
agents can do the actual building. The graph artifacts become the shared
understanding layer: agents generate code at machine speed, but the
decomposition that governs that generation remains human-legible.

## Mixed-Resolution Graphs

The variable lowering depth insight extends further: the "right" depth might
vary *within a single graph*. Some subtrees you understand well and can
specify precisely. Others are exploratory and benefit from giving the agent
more latitude. A mixed-resolution graph — some nodes fully specified, others
intentionally vague — might be the most practical operating point.

## Who Does the Lowering

Each pass in the lowering pipeline is parameterized by who performs it:

- **Fully manual**: human writes all levels of TaskGraph (the current workflow)
- **Fully automated**: agent performs all lowering from intent to executable graph
- **Hybrid**: human provides architectural decomposition, agent refines to
  implementation-level detail
- **Collaborative**: agent proposes each lowering, human approves or edits
  before the next pass

This mirrors how compilers evolved. Early compilers were simple one-pass
translators. Then multi-pass architectures emerged. Then optimization passes.
Then JITs that adapt at runtime. agentrelay could follow a similar trajectory
— start with well-defined manual passes, then automate the ones where agent
judgment is reliable enough.

## Implications for agentrelay

If this analogy is taken seriously, it suggests a few things:

1. **Abstraction level as a first-class concept.** The TaskGraph schema might
   benefit from a notion of abstraction level — a graph knows whether it's a
   high-level intent graph, an architectural graph, or an execution-ready
   graph. Each level would have different validation rules (an intent graph
   doesn't need `tagged_paths`; an execution graph does).

2. **Typed lowering passes.** The passes could be typed transformations:
   `TaskGraph[Intent] -> TaskGraph[Architecture] -> TaskGraph[Implementation]`.
   Each pass has a defined input/output contract.

3. **The optimal lowering depth is TBD.** Finding the right tradeoff between
   human specification effort, agent autonomy, and execution cost is an open
   empirical question. The system should be designed to support varying depths
   rather than hardcoding a single pipeline.
