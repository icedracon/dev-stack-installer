---
name: code-test-gap-finder
description: Find the highest-value untested code paths — public API without tests, error branches, complex functions with zero assertions. Use when the user asks where to add tests, how to improve coverage, or which code is under-tested.
---

# code-test-gap-finder

Coverage % is a lagging metric. Rank by risk, not by percentage.

## Detect test runner

`vitest.config`, `jest.config`, `pytest.ini` / `pyproject.toml [tool.pytest]`, `Cargo.toml [[test]]`, `go test` (built-in), `spec_helper.rb`, `phpunit.xml`.

## Ranking pass

For every source file, score by:

1. **Public API surface** — exported functions, HTTP handlers, CLI commands, event handlers.
2. **Cyclomatic complexity** — branches, loops, early returns.
3. **Error branches** — `try/catch`, `Result::Err`, `if err != nil`, `raise`.
4. **Change frequency** — `git log --oneline --since=6.months -- <file>` count.
5. **Bug history** — `git log --grep=fix -- <file>` count.

Highest score × zero test file → top of the list.

## Detect test coverage per unit

Rather than "% lines covered", look at **which exported symbols have no direct test**:

- Grep for `export function foo` → search test files for `import { foo }` or `foo(`.
- Rails / Django: routes/actions without matching request specs.
- Rust: `pub fn` without a `#[test]` that calls it (any tree).

## Error-branch coverage

For each `catch` / `except` / `Err` arm, is there a test that triggers it? Grep is enough — precise coverage tools miss the intent.

## Report

```
TOP GAPS (rank = risk × complexity × frequency, none tested)

1. src/payments/refund.ts:refundOrder      score 42   0 tests   3 branches, 2 error arms
2. api/handlers/webhooks.py:stripe_hook     score 38   0 tests   validates external input
3. crates/kerbcore/src/asrep.rs:parse       score 35   1 test    doesn't cover len-mismatch branch
```

Followed by a suggested test skeleton per top-3 (do NOT commit — user reviews first).

## What this skill does NOT do

- Compute exact line/branch coverage — delegate to the project's coverage tool.
- Write full test suites — write minimal skeletons per top item and stop.
- Delete existing tests — even the ones that look useless.
