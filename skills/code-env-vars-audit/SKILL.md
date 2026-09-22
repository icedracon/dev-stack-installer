---
name: code-env-vars-audit
description: Audit environment variable usage — missing from .env.example, hardcoded fallbacks that shouldn't exist, secrets committed by accident, and undocumented required vars. Use when the user asks to audit env vars, check secrets, or set up .env.example.
---

# code-env-vars-audit

Every `process.env.X` / `os.environ["X"]` / `std::env::var("X")` is a contract. Find broken ones.

## Discover the ground truth

Grep across the codebase for every env-var read:

- JS/TS: `process.env.\w+`, `import.meta.env.\w+`, `Deno.env.get("...")`, `Bun.env.\w+`.
- Python: `os.environ\[?"?\w+"?\]?`, `os.getenv("...")`, `settings.\w+` in Django, `Config.\w+`.
- Rust: `env::var("...")`, `env!("...")`.
- Go: `os.Getenv("...")`, `os.LookupEnv("...")`.
- Ruby / Rails: `ENV\["\w+"\]`, `ENV.fetch("...")`.
- Shell / Dockerfile / compose: `${VAR}`, `ARG`, `ENV`.
- CI: `.github/workflows/**` `${{ secrets.X }}`, `${{ vars.X }}`.

Deduplicate → the canonical list.

## Check against docs

- `.env.example` / `.env.sample` / `.env.template` — every real var should appear.
- `README.md` / `CONTRIBUTING.md` — required vars documented?
- Docker `ENV` defaults — do they match `.env.example`?
- CI secrets referenced — declared in the repo's environment?

## Findings

**Missing from example**
- Var used in code, not in `.env.example`.

**Undocumented required vars**
- Read with `.fetch()` / no default → deploy-blocking if missing → must be documented.

**Dangerous fallbacks**
- `process.env.SECRET || "changeme"` → hardcoded secret fallback.
- `os.getenv("API_KEY", "test-key")` → test key leaking to prod.

**Committed secrets**
- Grep `.env`, `*.env.local`, `secrets*.yml` in tracked files. Cross-check `.gitignore`.
- Grep for common patterns: `sk_live_`, `ghp_`, `xoxb-`, `AKIA`, `-----BEGIN PRIVATE KEY-----`.

**Unused vars in example**
- Declared in `.env.example`, never read → stale doc.

## Report

```
BLOCKER
- STRIPE_SECRET_KEY: used at api/billing.ts:14, not in .env.example
- committed secret: .env at repo root (untracked = false)

HIGH
- REDIS_URL: no default, no README mention

LOW
- LEGACY_FLAG: in .env.example, no code reads it
```

## Hard rules

- Never write a secret value into `.env.example` — placeholders only (`sk_XXXXXXXX`).
- Never suggest rotating a secret by writing the new value into any tracked file.
- Never `git rm` a committed secret without warning the user to rotate first.
