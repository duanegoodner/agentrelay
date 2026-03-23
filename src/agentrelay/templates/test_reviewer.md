**Scope: review tests only.** Assess the tests for correctness, coverage, and clarity. Do not implement the feature.
If the tests pass review, complete without a PR — you are not expected to have code changes.

$concerns_note

1. Read the source stubs at $src_paths and the test files at $test_paths
   to understand what is being tested.
2. Assess the tests for correctness, coverage, and clarity.
   Check that the tests are consistent with the docstrings in the source stubs.
   If you notice any docstrings that contradict each other, or if the tests assume
   behavior that conflicts with the documented API, record each issue as a design
   concern if not already recorded.
