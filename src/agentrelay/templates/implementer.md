The test files, stub modules, and any review notes are already merged into the integration branch and available in your worktree.

$concerns_note

**Task paths:**

$paths_by_category

1. Read the test files (category: test) to understand what is expected.
   Also read the docstrings in the source files (category: src) to understand the intended API contract.
   If you notice that the tests expect behavior that contradicts the docstrings
   (e.g., tests assert an exception but the docstring says the method silently
   handles the case), record each contradiction as a design concern if not already
   recorded.
2. Implement the feature by replacing the NotImplementedError stubs in
   the source files (category: src) with working code.
   Preserve all existing docstrings exactly. You may add Examples or Notes
   but do NOT alter Args, Returns, or Raises sections.
3. Run the tests (category: test) and fix any failures.
