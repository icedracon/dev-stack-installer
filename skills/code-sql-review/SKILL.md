---
name: code-sql-review
description: Review SQL queries or ORM-generated SQL for correctness, N+1, missing indexes, unsafe patterns, and portability issues. Use when the user asks to review a query, explain slow SQL, or audit database access in a codebase.
---

# code-sql-review

Read the query in context of its schema and its call site.

## Inputs

- Raw SQL (`.sql` files, migrations).
- ORM callsites: SQLAlchemy, Django ORM, Prisma, Drizzle, TypeORM, ActiveRecord, GORM, sqlx.
- The schema — always look it up first. Reviewing a query without the schema is guessing.

## Detection pass

Grep for common footguns:

- `SELECT *` in production paths.
- `WHERE column LIKE '%foo%'` (leading wildcard → seq scan).
- `OFFSET N LIMIT M` at large N (keyset pagination instead).
- Correlated subqueries where a JOIN would work.
- ORM `.all()` inside a loop → N+1.
- `.filter(...)` chains that build a query and then `len()` on the result → count-then-fetch bug.
- Missing `LIMIT` on user-facing lists.
- Time-zone naive `datetime` comparisons.
- String concatenation into raw SQL (injection).
- Transactions that span external I/O (holds row locks during HTTP calls).

## Index review

For each hot query, check:
- Does an index exist on the predicate columns?
- Is column order correct for the WHERE + ORDER BY pattern?
- Is it a covering index for the SELECT list?
- Is any index unused (bloat)? Suggest checking `pg_stat_user_indexes` etc.

Do not propose a migration unless the user asks. Propose the index text and let them decide.

## Portability

- Note dialect-specific syntax (`RETURNING`, window `RANGE BETWEEN`, `ILIKE`, `JSONB`, `LATERAL`) if the schema targets multiple engines.
- Flag NULLS FIRST/LAST assumptions (MySQL vs. Postgres differ).

## Correctness

- Non-deterministic aggregates over unordered sets.
- `LEFT JOIN` + `WHERE right.col = X` = accidentally an inner join.
- Aggregate over an outer-joined table without `COALESCE`.
- Grouping without every non-aggregate column.

## Report shape

```
FILE:LINE  <query snippet>
CORRECTNESS: <blocker | ok>
PERFORMANCE: <estimated cost basis: seq scan / index scan / …>
FIX:         <one concrete suggestion>
```

## Hard rules

- Never propose a schema change without the user asking.
- Never run `EXPLAIN ANALYZE` against production.
- Never rewrite ORM code without confirming the resulting SQL is equivalent.
