---
name: dev-stack-installer
description: Scan the current repo, detect its stack (frontend / backend / mobile / infra / data / product signals), and recommend the matching Claude Code skills + plugins + hooks. Use when the user says "set up claude for this project", "what skills should I install", "audit my claude setup", or invokes /dev-stack-install.
---

# dev-stack-installer

You are configuring Claude Code for a repo the user just opened. Job: detect what's in the tree, map it to skill bundles, present a ranked install plan, then install what the user approves.

## 1. Detect (read-only, no execution)

Glob and Read only. Never run project code during detection.

**Frontend**: `package.json`, `next.config.*`, `vite.config.*`, `tailwind.config.*`, `astro.config.*`, `svelte.config.*`, `nuxt.config.*`, `angular.json`, `remix.config.*`, `**/*.tsx`, `**/*.vue`, `**/*.svelte`.

**Backend**: `pyproject.toml`, `requirements*.txt`, `Cargo.toml`, `go.mod`, `pom.xml`, `build.gradle*`, `Gemfile`, `composer.json`, `mix.exs`, `*.csproj`, `deno.json`.

**Mobile / desktop**: `android/`, `ios/`, `*.xcodeproj`, `Podfile`, `pubspec.yaml`, `tauri.conf.json`, `electron*.json`, `capacitor.config.*`, `react-native.config.*`.

**Infra / ops**: `Dockerfile*`, `docker-compose*`, `.github/workflows/**`, `.gitlab-ci.yml`, `terraform/**`, `*.tf`, `k8s/**`, `charts/**`, `serverless.yml`, `vercel.json`, `netlify.toml`, `fly.toml`.

**Data / ML**: `**/*.ipynb`, `dbt_project.yml`, requirements matching `torch|tensorflow|sklearn|pandas|polars|numpy`, `airflow/`, `dagster/`, `prefect/`.

**Product / growth signals**: `README.md` mentions of "SaaS/B2B/e-commerce"; `**/landing*.{tsx,jsx,vue,svelte}`; `**/pricing*.*`; `**/checkout*.*`; dependencies `stripe|paddle|lemonsqueezy|posthog|amplitude|mixpanel|segment|ga4|plausible`.

## 2. Score & bundle

Emit a table like this (do not skip — even a small repo gets it):

| Bundle       | Trigger found              | Skills to install                                                | Priority |
|--------------|----------------------------|------------------------------------------------------------------|----------|
| always-on    | (every repo)               | setup-claude, claude-api, docs, morning, schedule                | must     |
| code-quality | any code file              | code-review, simplify, security-review, claude-md-improver       | must     |
| design       | tailwind, tsx, vue, svelte | design-figma-handoff, design-tokens, design-ui-audit             | high     |
| ops          | Dockerfile / .github/wf    | ops-docker-slim, ops-github-actions-audit                        | high     |
| data         | *.ipynb / dbt / torch      | dataviz, xlsx, pdf                                               | med      |
| growth       | README + landing/pricing   | copywriting, seo-audit, ai-seo, cro, emails                      | med      |

## 3. Present

Output in this exact shape (terse — user is expert):

```
STACK DETECTED
- frontend: next 15, tailwind 4, tsx (94 files)
- backend:  python 3.12, fastapi, sqlalchemy
- ops:      Dockerfile (multi-stage ✓), github-actions (3 workflows)
- growth:   pricing page + stripe + posthog → SaaS

RECOMMENDED (18 skills across 5 bundles)

MUST  code-quality      code-review · simplify · security-review · claude-md-improver
MUST  always-on         setup-claude · docs · morning
HIGH  design            design-figma-handoff · design-tokens · design-ui-audit
HIGH  ops               ops-docker-slim · ops-github-actions-audit
MED   growth (SaaS)     copywriting · seo-audit · ai-seo · cro · emails
MED   code-python       code-python-typing-uplift · code-api-contract-check · code-test-gap-finder

ALREADY INSTALLED: code-review, simplify (from claude-code-plugin pack)
MISSING:           16 skills · 2 hooks · 1 MCP server

Install all? [Y/n/pick]
```

## 4. Install

- **Skills in this plugin pack**: point to `skills/<name>` inside the current plugin folder.
- **Skills from Anthropic marketplace**: `claude plugin install anthropic-skills`, note which are needed.
- **Missing entirely**: offer to scaffold via `skill-creator` — do NOT auto-scaffold without confirmation.
- **Hooks**: propose `.claude/settings.json` additions (fmt/lint on Stop for detected language) — show the diff first, apply on yes.
- **MCP servers**: name candidates (github, sentry, postgres) but never auto-add — user must approve each.

## 5. Post-install

Append a short block to `CLAUDE.md` at repo root:

```md
## Claude Code stack
Installed via dev-stack-installer on <YYYY-MM-DD>. Stack: <one-liner>.
Skills active: <count>. See `.claude/settings.json` for hooks.
```

## Hard rules

- **Never** install without a printed preview + explicit user yes.
- **Never** modify `.claude/settings.json` without showing the diff first.
- **Never** invent skills that don't exist; if a bundle names a skill you can't verify, mark it `(scaffold)` and require confirmation.
- **Never** run `npm install`, `pip install`, `cargo build`, or anything that mutates the project during detection.
