## Change

Describe the problem and resulting behavior. Link the issue: `Fixes #N` when this PR completes it and targets `main`; `Part of #N` otherwise (stacked PRs, partial steps).

Spec (Tin 1 work): `design/design_____.md §__`

## Touches hot files

List any of `toolchain/compiler/check.tin`, `lower.tin`, `region.tin`, `parse.tin`, `gen.tin`, `gen_x64.tin`, `inline.tin`, `toolchain/runtime/runtime*.tin`, `packages/anvil/anvil*.tin`, or write "none".

## Depends on / unblocks

Needs #__ (merged, or stacked on #__). Unblocks #__.

## Regression coverage

- [ ] Added a reproducer to `toolchain/tests/regressions/` and its contract to `cases.json`, or named the existing automated test below.
- [ ] For a known-failure fix: kept the reproducer, removed `known_failure`, and verified PASS on every affected supported target.
- [ ] Memory/runtime changes cover allocation boundaries, pool reset/ownership and relevant Linux behavior.

Test(s):

## Validation

- [ ] Strict suite, regressions, `tools/ci` checks, `make bootstrap` fixed point (compiles with the checked-in seeds).
- [ ] Linux numbers (bench-linux run link) if a hot path changed; macOS numbers are never results (AGENTS.md).
- [ ] Docs updated (LANGUAGE.md / RUNTIME.md / STDLIB.md regenerated), or why not.

The required `CI` check must pass before merging.
