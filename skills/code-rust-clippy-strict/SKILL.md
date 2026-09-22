---
name: code-rust-clippy-strict
description: Run an MSRV-aware clippy sweep on a Rust crate or workspace with the right lint set, apply fixes only where safe, and never silently raise the MSRV. Use for Rust cleanup passes, pre-release audits, or when the user says "clean up clippy".
---

# code-rust-clippy-strict

Clippy the strict way — no MSRV drift, no cosmetic churn, no `--all-targets` false alarms.

## Preflight (mandatory)

1. Read `rust-toolchain*` and every `Cargo.toml` for `rust-version`.
2. If `rust-version` is missing at workspace or crate level, **add it first** — pin to the current CI floor. Clippy is MSRV-aware only when this field is set.
3. Read `[lints]` sections; do not fight the project's existing lint policy.

## Lint set

Start with a conservative sweep:

```
cargo clippy --lib --tests --benches --examples -- \
  -W clippy::pedantic \
  -W clippy::nursery \
  -A clippy::module_name_repetitions \
  -A clippy::missing_errors_doc \
  -A clippy::missing_panics_doc
```

Measure **lib-only first** — `--all-targets` on test/bench code produces noise that isn't a real defect.

## Landmine lints (never auto-fix without diff review)

- `manual_is_multiple_of` (bumps MSRV to 1.87).
- `manual_repeat_n` (bumps MSRV to 1.82).
- `single_call_fn` (kills legitimate testability seams).
- `used_underscore_binding` (breaks intentional API shape).
- `needless_pass_by_value` (changes public signature).

If clippy suggests a fix, verify the target Rust version doesn't jump. Grep the suggestion against a known table before applying.

## Apply strategy

- `cargo clippy --fix --allow-dirty --allow-staged` for the safe subset only.
- Anything touching public API or MSRV → present a diff, do not auto-apply.
- Re-verify MSRV after every sweep: `cargo +<msrv> check --lib`.

## Post-sweep

- Emit a table: crate → lints fixed vs. deferred, with reason for defers.
- Update CHANGELOG only if the fixes are user-observable (never from memory — grep the diff).
- If any fix changes public API, bump per SemVer minimum (additive→patch on 0.x line; breaking→minor/major).

## Hard rules

- Never `--fix` on a dirty tree without a stash.
- Never fight the project's `#[allow]` — respect intent.
- Never bump MSRV without asking.
