## Change

Describe the problem and resulting behavior. Link the issue (use `Fixes #N` when complete).

## Regression coverage

- [ ] Added a reproducer to `tests/regressions/` and its contract to `cases.json`, or named the existing automated test below.
- [ ] For a known-failure fix: kept the reproducer, removed `known_failure`, and verified PASS on every affected supported target.
- [ ] Memory/runtime changes cover allocation boundaries, pool reset/ownership and relevant Linux behavior.

Test(s):

## Validation

List the checks run. The required `CI` check must pass before merging.
