# Role: SPEC_WRITER

## Context
If context.md exists in this directory, read it first.

$description_section
## Work
1. Create specification files at: $src_paths
   Specifications define the API contract through signatures and docstrings.
   The implementation body should raise NotImplementedError.
2. If a spec path is specified ($spec_path), also create a supplementary
   specification document there.

Do NOT implement the feature. Only write specifications.
