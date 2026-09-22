---
name: ops-migration-writer
description: Write a safe, reversible database migration (schema or data) for any migration framework (Alembic, Django, Prisma, Drizzle, Rails, Flyway, Liquibase, sqlx-migrate). Use when the user asks to add a column, rename, backfill, or write a migration.
---

# ops-migration-writer

Every migration is either reversible or a promise you'll fix forward. Say which.

## Detect the framework

- Alembic (`alembic.ini`, `migrations/versions/`).
- Django (`<app>/migrations/`).
- Prisma (`prisma/migrations/`, `schema.prisma`).
- Drizzle (`drizzle.config.*`, `drizzle/`).
- Rails (`db/migrate/`, `schema.rb` / `structure.sql`).
- Flyway (`db/migration/V<ver>__<name>.sql`).
- Liquibase (`changelog.xml` / `.yaml`).
- sqlx / diesel (Rust conventions).

Match the framework's file naming exactly.

## Safety tiers (state which one this migration is)

**Tier 1 — always safe on a live table**
- Add nullable column.
- Add new index CONCURRENTLY (Postgres) / ONLINE (MySQL 8+).
- Add new table.
- Add a check constraint NOT VALID → later VALIDATE.

**Tier 2 — safe with care**
- Rename column: two-step (add new + backfill + swap reads/writes + drop old across releases). Never single-step rename in prod.
- Change column type: same two-step.
- Drop a column: two-step (stop-reading release + drop release).

**Tier 3 — dangerous, needs downtime or online-DDL tooling**
- Add NOT NULL to existing column without a default (blocks writes on rewrite).
- Add a foreign key without `NOT VALID` first.
- Long-running data backfill in a single transaction on a hot table.

Flag the tier at the top of the generated migration.

## Backfills

- **Batched** — never `UPDATE ... WHERE ...` a whole hot table. Loop in chunks of a few thousand with an id cursor.
- **Idempotent** — safe to re-run if a batch fails.
- **Under an explicit lock discipline** — statement_timeout, lock_timeout set for each batch (Postgres).
- **Separate migration from schema change** — schema change is fast, backfill is slow.

## Reversibility

- Provide a `down()` / `-- rollback` unless the change is data-lossy.
- If not reversible, explicit comment: `-- IRREVERSIBLE: rolling forward is the only path`.
- For destructive down migrations (`DROP COLUMN`), require operator confirmation in a separate step.

## Test discipline

- Migration runs against a snapshot of prod schema (not just dev's empty tables).
- Roundtrip test: apply, revert, apply — schemas identical.
- Include a fixture that exercises the new shape before deploying.

## Output shape

Generate:
1. The migration file(s) in the framework's exact format.
2. A short markdown note (`docs/migrations/<name>.md` or PR description block) covering: tier, expected duration, lock impact, rollback plan.
3. A pre-deploy checklist.

## Hard rules

- Never generate a Tier-3 migration without explicit confirmation of the outage plan.
- Never combine schema change + backfill in one transaction on a live table.
- Never rely on ORM `create_all()` / `db push` for production changes — always a versioned file.
