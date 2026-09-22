---
name: code-readme-doctor
description: Audit and repair a project README — what's missing, what's stale, what's wrong. Verify commands actually work; verify links resolve; verify screenshots aren't dead. Use when the user asks to fix the README, audit docs, or produce a first README.
---

# code-readme-doctor

A README earns its place by getting a stranger running in under 5 minutes. Audit against that bar.

## Required sections (in this order)

1. **Name + one-sentence pitch** — what it is, who it's for.
2. **Install** — copy-pasteable, tested against the current version.
3. **Quickstart** — one working example, complete, runnable.
4. **Usage / API summary** — the shape of the thing.
5. **Config** — env vars, flags, files (delegate to [[code-env-vars-audit]]).
6. **Development** — how to run tests, build, contribute.
7. **License** — must match `LICENSE` file.

Anything missing → gap.

## Verify commands

For every fenced code block tagged `bash` / `sh` / `console`:
- Does the binary exist? (`which <cmd>`).
- Does the command syntax match the installed version?
- Does the flag exist? Grep the tool's `--help` or docs.
- If the command mutates state (create-project, init), don't run it — just verify shape.

## Verify links

- Internal links: file exists, anchor exists.
- External links: fetch head; flag any 404 / 301 chain → final destination.
- Badges: hit the badge URL; flag failing CI badges, broken coverage badges, stale version badges.

## Verify screenshots / assets

- Image files exist in the repo.
- Not obviously outdated (compare filename date vs. last major UI change in git history).
- Alt text present.

## Verify version claims

- README says "requires Python 3.10+"? Cross-check `pyproject.toml` / `python_requires`.
- README says "install via `npm i foo@2`"? Check `package.json` "version".
- Any concrete version number cited: fact-check against the source of truth.

## Report

```
MISSING SECTIONS
- Quickstart
- License section

BROKEN COMMANDS
- README:42 — `pnpm dlx create-foo` → binary not found in current setup
- README:88 — flag `--strict` removed in v3

BROKEN LINKS
- README:12 → docs/OLD-GUIDE.md (file deleted 2025-11-04)
- README:33 → https://foo.com/bar (404)

STALE
- Version badge shows 1.2.0; package.json is 2.0.1
- Screenshot dated 2024-03 (major redesign shipped 2025-08)
```

## Hard rules

- Never invent quickstart output — copy from an actual run.
- Never overwrite a README section without showing the diff.
- Never claim license = X without reading the LICENSE file.
