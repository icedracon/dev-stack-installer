# dev-stack-installer

**One skill scans your repo, detects the stack, and recommends the whole matching pack: design, code-quality, ops, and growth skills.**

Ships with 18 skills across 4 domains. Install the plugin once — the meta-installer figures out what your project actually needs.

## What's in the box

### The meta-skill
| Skill | Does |
|---|---|
| `dev-stack-installer` | Scans repo → detects stack → prints ranked install plan → installs on approval |

### Design (4)
| Skill | Does |
|---|---|
| `design-figma-handoff` | Figma frame → semantic-token component spec + scaffold in the project's framework |
| `design-tokens` | Extract scattered CSS/Tailwind/SCSS values into W3C DTCG tokens |
| `design-ui-audit` | Static + browser a11y audit; responsive & dark-mode parity check |
| `design-component-doc` | Component source → props/variants/a11y doc + optional CSF3 story |

### Code quality (10)
| Skill | Does |
|---|---|
| `code-rust-clippy-strict` | MSRV-aware clippy sweep; blocks silent MSRV bumps |
| `code-python-typing-uplift` | Incremental type-hint uplift, module by module |
| `code-ts-strict-migrate` | `strict: true` migration, one flag at a time |
| `code-sql-review` | Query review: N+1, missing indexes, unsafe patterns |
| `code-api-contract-check` | OpenAPI / tRPC / GraphQL / proto drift vs. server |
| `code-dep-audit` | Cross-ecosystem: CVEs, staleness, duplicates, license issues |
| `code-test-gap-finder` | Highest-risk untested code paths, ranked |
| `code-env-vars-audit` | Missing / undocumented / dangerously-defaulted env vars, committed secrets |
| `code-readme-doctor` | Verify commands, links, versions, badges; propose missing sections |
| `code-perf-budget` | Bundle + Lighthouse + Core Web Vitals budgets, then wire the CI gate |

### Ops (3)
| Skill | Does |
|---|---|
| `ops-docker-slim` | Dockerfile audit: size, security, cache, reproducibility |
| `ops-github-actions-audit` | Workflow security (pinning, permissions), speed (caching, matrix), correctness (concurrency, path filters) |
| `ops-migration-writer` | Safe reversible migrations for any framework; explicit safety tier |

## Install

```bash
# From Claude Code:
/plugin marketplace add icedracon/dev-stack-installer
/plugin install dev-stack-installer
```

Or manually clone into your `.claude/plugins/`:

```bash
git clone https://github.com/icedracon/dev-stack-installer.git \
  ~/.claude/plugins/dev-stack-installer
```

## Use

Open any project and run:

```
/dev-stack-install
```

The installer will:

1. **Detect** — glob-only, no code execution. Scans for frontend / backend / mobile / infra / data signals plus product signals (README + landing + Stripe/PostHog → "this is a SaaS").
2. **Rank** — bundles the matching skills by priority (must / high / med).
3. **Preview** — prints the plan, marks what's already installed vs. missing.
4. **Install on approval** — nothing writes without a `Y`.

Every write (settings.json diffs, CLAUDE.md hint block, hook additions) is shown as a diff first.

## Design principles

- **Detection is read-only.** No `npm install`, no `cargo build`, no side effects during scan.
- **Skills are opt-in.** The installer proposes, never auto-runs the recommended skills against your code.
- **Every recommendation is verifiable.** If a bundle names a skill the installer can't find, it's marked `(scaffold)` — the installer offers to create a stub via `skill-creator`, but only with confirmation.
- **No hidden bumps.** No skill silently changes MSRV, TS strictness, package majors, or config files.
- **Bundles override single skills.** The installer treats them as coherent packs — you approve or skip the bundle, not each item.

## Directory layout

```
dev-stack-installer/
├── .claude-plugin/plugin.json    # plugin manifest
├── skills/
│   ├── dev-stack-installer/      # the meta-installer
│   ├── design-*/                 # 4 design skills
│   ├── code-*/                   # 10 code-quality skills
│   └── ops-*/                    # 3 ops skills
├── commands/
│   └── dev-stack-install.md      # the /command
├── LICENSE                        # MIT
└── README.md
```

## Contributing new skills

Each skill is a folder under `skills/` with a single `SKILL.md`:

```
---
name: your-skill
description: When to invoke it, one sentence.
---

# Body: exact playbook, hard rules at the bottom.
```

Follow the pattern of existing skills:

- Detection pass first (read-only).
- Concrete report shape.
- Explicit hard rules at the end.
- Cross-link related skills with `[[name]]`.

Open a PR — no formal template yet.

## License

MIT. See `LICENSE`.
