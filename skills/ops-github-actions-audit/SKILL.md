---
name: ops-github-actions-audit
description: Audit `.github/workflows/*` for security (pinned actions, permissions, secret exposure), speed (caching, matrix bloat, redundant runs), and correctness (concurrency, path filters). Use when the user asks to review CI, speed up builds, or audit workflow security.
---

# ops-github-actions-audit

CI is code. Review it like code.

## Security

- **Every third-party action pinned to a full SHA**, not a tag. `actions/checkout@v4` is a tag; `actions/checkout@11bd7192...` is a SHA. Tags can be moved.
- **First-party actions** (`actions/*`) can use tags with less risk, but pinning is still better for reproducibility.
- **`permissions:` block** at workflow OR job level. Default should be `contents: read`; escalate per-job only when needed.
- **Never `pull_request_target`** unless you know exactly what secrets you're exposing to fork PRs.
- **Secrets in logs**: grep for `echo ${{ secrets.` — always a red flag.
- **Fork PR triggers** should not have access to secrets; require label approval or environment gate.

## Speed

- Are dependency setups cached?
  - `actions/setup-node@vX` with `cache: 'pnpm'` (or npm/yarn).
  - `actions/setup-python@vX` with `cache: 'pip'` / `'poetry'`.
  - `Swatinem/rust-cache@vX`.
  - `actions/cache@vX` for anything custom.
- **Matrix explosion**: N OS × M version × K feature-flag → cost N·M·K. Trim per real coverage need.
- **Redundant jobs**: lint + typecheck often run in the same setup — merge.
- **`fetch-depth: 0`** is expensive on big repos; only if the job needs full history.
- **Parallel test sharding** for slow suites (`--shard 1/4` etc.).

## Correctness

- **`concurrency:`** block with `cancel-in-progress: true` on PR workflows — otherwise old commits waste minutes.
- **Path filters** on `on: push:` for monorepos — don't run frontend tests on backend-only commits.
- **`workflow_dispatch:`** with typed `inputs:` for manual triggers, not free-form.
- **Timeout per job** (`timeout-minutes:`) — default 6h is too generous.
- **`if: always()`** used correctly for cleanup steps; not accidentally on required checks.

## Deploy safety

- Environments (`environment: production`) require reviewers.
- Rolling deploys check the previous status; failed job should not deploy.
- Secrets scoped to environment, not to repo, when possible.

## Report

```
SECURITY
- .github/workflows/ci.yml:14  third-party action pinned to tag `v3` (should be SHA)
- .github/workflows/deploy.yml:6  `permissions: write-all` (needs scoping)
- .github/workflows/release.yml:22  echoes ${{ secrets.NPM_TOKEN }} in a run step

SPEED
- pnpm cache missing on 3 workflows — est. 90s/run savings
- concurrency block missing on 2 PR workflows

CORRECTNESS
- ci.yml has no path filter — runs on doc-only changes
- release.yml timeout-minutes: 360 (excessive)
```

## Hard rules

- Never rewrite `permissions:` without listing every step's needed scope.
- Never remove a matrix cell without checking test coverage.
- Never propose caching a directory that contains secrets or per-build state.
