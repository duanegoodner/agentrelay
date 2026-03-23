The test files, stub modules, and any review notes are already merged into the integration branch and available in your worktree.

1. Read the test files at $test_paths to understand what is expected.
   Also read the docstrings in $src_paths to understand the intended API contract.
   If the tests expect behavior that contradicts the docstrings (e.g., tests assert
   an exception but the docstring says the method silently handles the case), record
   each contradiction as a design concern before implementing.
2. Implement the feature by replacing the NotImplementedError stubs in
   $src_paths with working code.
   Preserve all existing docstrings exactly. You may add Examples or Notes
   but do NOT alter Args, Returns, or Raises sections.
3. Run the tests at $test_paths and fix any failures.
