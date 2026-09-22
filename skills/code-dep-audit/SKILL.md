---
name: code-dep-audit
description: Audit project dependencies for outdated versions, known CVEs, license conflicts, and duplicate lockfile entries — across any ecosystem (npm/pnpm/yarn, pip/uv/poetry, cargo, go mod, bundler, composer, gradle). Use when the user asks to audit deps, check for CVEs, or update dependencies.
---

# code-dep-audit

One pass, all ecosystems. Prioritize by risk × reachability, not just by version delta.

## Detect ecosystems

Grep for lockfiles: `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lockb`, `poetry.lock`, `uv.lock`, `Pipfile.lock`, `Cargo.lock`, `go.sum`, `Gemfile.lock`, `composer.lock`, `gradle.lockfile`.

Each lockfile → its own tool. Never mix.

## Audit checks

**Security**
- Native tool per ecosystem (`pnpm audit`, `pip-audit`, `cargo audit`, `bundle audit`, `govulncheck`, `composer audit`).
- Cross-reference GHSA advisories where the native tool misses.
- For each CVE: is the vulnerable path actually reachable from your code? Grep for the affected symbol before recommending an urgent bump.

**Freshness**
- Direct deps: how far behind latest (major/minor/patch).
- Transitive deps: only flag if pinned or if bump would be non-trivial.

**Duplicates**
- Multiple versions of the same package in the tree (npm hoist misses, cargo duplicates on version resolution). This is bloat + potential correctness bugs.

**Licenses**
- Grep for GPL / AGPL in a non-GPL project.
- Flag deps without a resolvable license.

**Abandoned**
- Last publish > 2 years and no successor → flag; user decides.

## Report

```
CRITICAL (CVE, reachable)
- <pkg>@<ver>  →  <fixed-in>   CVE-YYYY-NNNN   reached via <call site>

HIGH (CVE, not reached)
- ...

STALE MAJORS
- <pkg>: 3.2.1 → 6.0.0 (breaking changes: <link>)

DUPLICATES
- <pkg>: 1.4.0 (via <deep dep>), 2.1.0 (direct)

LICENSE
- <pkg>@<ver>: <license> — incompatible with project <license>
```

## Fix strategy

- Group updates by risk: patches first (safe), minors next (usually safe), majors last (per-package).
- Use `<pm> update <pkg>@<target>` per package — never a global bump.
- Re-run tests after each group.
- Update lockfile in the same commit that updates the manifest.

## Hard rules

- Never bump a major without reading its changelog.
- Never remove a dep because it's stale — it may be intentional.
- Never auto-run `<pm> update` without a scoped list.
