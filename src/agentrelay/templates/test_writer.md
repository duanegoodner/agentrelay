**Scope: write tests only.** The source files at $src_paths contain signatures and docstrings for an API that has not yet been implemented. Write pytest tests that can be used to verify the implementation, which another agent will write next. Do not modify the source files or add implementations.

1. Read the source stubs at $src_paths to understand the API contract.
   The docstrings are the authoritative spec.
2. Write pytest test files at: $test_paths
3. Verify tests collect without import errors.
