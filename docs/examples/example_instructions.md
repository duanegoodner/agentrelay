# Instructions for Task ${TaskID}

## Role: You are a SPEC_WRITER tasked with writing specifications for part of a software project. Follow the instructions below to complete the task.

## Tools

- **pixi**: Use `pixi run` to execute all Python commands, tests, and scripts. Do not use bare `python`, `pytest`, or `pip` — always prefix with `pixi run`.

## What to Do

**Scope: write API stubs only.** Define class, function, and method signatures with type hints and docstrings. Function and method bodies should be `raise NotImplementedError`. Do not write working logic.

1. Create specification file(s) at: src/agentrelaydemos/bounded_queue.py
   In these files, create class signatures and docstrings that define the API contract for the items described in the Task Details section below.
   The implementation body of each method should be `raise NotImplementedError`.

As you work, record any concerns you encounter:
- **Design concerns** (spec contradictions, ambiguities): `agentrelay-concern --message "..."`
- **Ops concerns** (build errors, missing deps, tooling friction): `agentrelay-ops-concern --message "..."`

## Submitting Your Work

After completing the work above:

1. **Commit and push** all changes to branch `agentrelay/role-pipeline/spec_bounded_queue`.
2. **Complete the task** (creates PR and signals the orchestrator):
   ```bash
   agentrelay-complete --title "short summary of changes" --body "## Summary

   - what was done"
   ```
   Provide a meaningful PR title (concise) and body (markdown with a ## Summary section).
   Any recorded concerns are automatically appended to the PR body.

If you made no code changes (e.g., review-only work), complete without a PR:
   ```bash
   agentrelay-complete-no-pr
   ```

If you cannot complete the work, signal failure instead:
   ```bash
   agentrelay-failed --reason "reason for failure"
   ```

**Important**: The orchestrator is waiting for the signal. Do not skip step 2.


## Task Details

Create the specification for BoundedQueue[T] class — a generic, fixed-capacity FIFO queue.

Constructor:
- __init__(capacity: int) — capacity must be a positive integer
  (raise ValueError if capacity <= 0).


Core operations:
- push(item: T) -> None — Add item to the back of the queue. If the
  queue is at capacity, the oldest item is automatically evicted to
  make room for the new item.

- pop() -> T — Remove and return the front item. Raise IndexError
  if the queue is empty.

- peek() -> T — Return the front item without removing it. Raise
  IndexError if the queue is empty.


Query methods:
- is_full() -> bool — True when the current length equals capacity.
- __len__() -> int — Current number of items in the queue.
- capacity (read-only property) -> int — The maximum number of items.

Error handling:
All mutating methods must validate preconditions and raise appropriate exceptions. push() raises OverflowError when the queue has reached capacity. pop() and peek() raise IndexError when the queue is empty.
