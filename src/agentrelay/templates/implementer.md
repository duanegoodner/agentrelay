# Role: IMPLEMENTER

## Context
If context.md exists in this directory, read it first.

The test files, stub modules, and any review notes are already merged into the
integration branch and available in your worktree.

## Work
1. Read the test files at $test_paths to understand what is expected.
2. Implement the feature by replacing the NotImplementedError stubs in
   $src_paths with working code.
   Preserve all existing docstrings exactly. You may add Examples or Notes
   but do NOT alter Args, Returns, or Raises sections.
3. Run the tests at $test_paths and fix any failures.
4. If you encounter design concerns — contradictions in the spec, ambiguities
   that affect behavior, or requirements that seem impossible to satisfy — record
   each one using `helper.record_concern("description of concern")`.
