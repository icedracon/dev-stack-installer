---
name: code-ts-strict-migrate
description: Migrate a TypeScript project to `strict: true` (or tighten it further) without breaking the build — flag-by-flag, file-by-file. Use when the user asks to enable strict, fix noImplicitAny, or tighten TS config.
---

# code-ts-strict-migrate

Enable strictness gradually. Never flip everything at once.

## Preflight

- Read every `tsconfig*.json` in the tree (root, per-package, `tsconfig.build.json`).
- Note current flags: `strict`, `noImplicitAny`, `strictNullChecks`, `strictFunctionTypes`, `strictBindCallApply`, `strictPropertyInitialization`, `noImplicitThis`, `useUnknownInCatchVariables`, `alwaysStrict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`.
- Baseline error count: `tsc --noEmit` at current config.

## Flag order (least → most disruptive)

1. `noImplicitAny` — usually the biggest, do first.
2. `strictNullChecks` — the second big rock; enables `X | null | undefined` unions.
3. `strictFunctionTypes` — variance fixes.
4. `strictBindCallApply` — cheap.
5. `noImplicitThis` — cheap.
6. `useUnknownInCatchVariables` — narrow-per-use.
7. `alwaysStrict` — free.
8. `strictPropertyInitialization` — needs constructor discipline (or `!` markers).
9. `noUncheckedIndexedAccess` — cascading, do last, expect churn in array/record access.
10. `exactOptionalPropertyTypes` — often deferred; only if the codebase carefully distinguishes "missing" vs "explicit undefined".

For each flag: enable, run tsc, fix, commit, next.

## File-level opt-in trick

Big monorepo? Use `// @ts-check` in JS files and per-file `// @ts-expect-error` only for genuine bugs. Never `// @ts-ignore` — it hides new errors silently.

## Common fix patterns

- `foo?.bar ?? default` for possibly-undefined chains.
- `if (!x) throw new Error(...)` narrows better than `x!`.
- `satisfies` over `as` — preserves narrowing without lying.
- `unknown` in catch → `if (err instanceof Error) …`.
- `Record<K, V>` accesses now return `V | undefined` — guard once, then use.

## Third-party friction

- Stale `@types/*` packages → check for newer typings; sometimes the lib now ships its own.
- Widely-any'd libs → wrap them in a typed facade module, not scattered `any` casts.

## Report

Per-flag: files touched, errors resolved, errors deferred (with reason). Do not enable the next flag until the current one is at zero errors (or every remaining error has a filed issue).
