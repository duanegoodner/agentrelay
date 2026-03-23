**Scope: write API stubs only.** Define class, function, and method signatures with type hints and docstrings. Function and method bodies should be `raise NotImplementedError`. Do not write working logic.

$concerns_note

1. Create specification file(s) at: $src_paths.
   In this/these file(s), create class signatures and docstrings that define the API contract for the items described in the Task Details section below.
   The implementation body of each method should be `raise NotImplementedError`.
2. As a final check, re-read the Task Details and cross-check against your stubs.
   If any requirements contradict each other (e.g., a method is described with two
   incompatible behaviors), record each contradiction as a design concern if not
   already recorded.
