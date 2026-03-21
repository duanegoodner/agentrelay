# E2E Test Graphs

Task graphs organized by testing category. Each subdirectory contains YAML graph
definitions and a README with run instructions and verification notes.

## Categories

| Directory | Purpose |
|---|---|
| `smoke/` | Quick validation of core execution paths (chained, parallel) |
| `concerns/` | Agent concern capture mechanism (concerns.log → orchestrator result) |
| `roles/` | Role-specific templates and multi-role pipeline handoff |

## Adding a new category

1. Create `graphs/<category>/`
2. Add graph YAML files
3. Add a `README.md` explaining the graphs, how to run, and what to verify
4. Update this index
