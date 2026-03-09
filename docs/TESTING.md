# Testing

`agentrelay` has test coverage for both the current architecture layer and the
v01 prototype layer.

## Scope

- `test/` - tests for `src/agentrelay/` (current architecture)
- `test/prototypes/v01/` - tests for `src/agentrelay/prototypes/v01/`

## Commands

Run all tests:

```bash
pixi run test
```

Run format + typecheck + tests:

```bash
pixi run check
```

Show collected test cases without executing:

```bash
pixi run pytest --collect-only -q
```

At present, collection reports **500 tests**.
