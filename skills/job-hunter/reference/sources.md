# Sources: what is automated and why

| Source | Method | Status | Notes |
|---|---|---|---|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | implemented | Public JSON, one request per board. Content is HTML-escaped. |
| Lever | `api.lever.co/v0/postings/{co}?mode=json` (EU: `api.eu.lever.co`) | implemented | Has `workplaceType` and sometimes `salaryRange`. |
| Ashby | `api.ashbyhq.com/posting-api/job-board/{board}` | implemented | Has `isRemote`, `workplaceType`, compensation summary. No single-job endpoint. |
| Workable | `apply.workable.com/api/v1/widget/accounts/{acct}?details=true` | implemented, **least certain** | Widget API; whether `details=true` returns descriptions for every account is unverified. Jobs without text get low confidence. |
| SmartRecruiters | `api.smartrecruiters.com/v1/companies/{id}/postings` | implemented | The list has no description; details are fetched **only** for titles that pass the filter. |
| Remotive | `remotive.com/api/remote-jobs?category=…` | implemented (aggregator) | ~24h delayed, apply links go via Remotive, ToS asks for low polling. Deduped against ATS copies. |
| LinkedIn | — | **not automated** | ToS forbids scraping; the guest endpoints are brittle; accounts get restricted. Use `jh add <url> --title … --company … --text-file jd.txt`. If the LinkedIn post links to an ATS, add *that* URL. |
| Wellfound | — | **not automated** | Heavy bot protection. Same manual path. |
| Workday / iCIMS / Taleo | — | not implemented | Per-tenant HTML, CSRF tokens, no stable public JSON. Many big security vendors (CrowdStrike, Palo Alto, Tenable) are here. Phase 2 at best. |
| Security job boards (infosec-jobs etc.) | — | not implemented | No stable API known to the author; would need HTML scraping. |

## The discovery problem (read this)

ATS APIs return only the companies you list. **Coverage equals the quality of
`companies.toml`.** The bundled seed list (~40 boards) was written without network access,
so tokens are unverified. Run `jh sources verify` first.

Ways to grow coverage cheaply:
1. When you find a good job elsewhere, `jh add <ats-url>` prints the `jh sources add …` command for that board.
2. Occasionally use web search (not per run) for `site:jobs.lever.co "red team"`,
   `site:job-boards.greenhouse.io "offensive security"`, `site:jobs.ashbyhq.com "application security"`,
   then add the boards. This is where an LLM/search tool actually earns its cost: finding boards, not
   reading job descriptions.

## Politeness and account safety

- One request per board per run, throttled per host (`request_delay_seconds`), with backoff on 429/5xx
  honouring `Retry-After`. No cookies, logins or user-agent rotation.
- HTTP 403/401 is treated as "not allowed" and never retried around.
- Boards failing 3 runs in a row are skipped until `jh find --source <token>` succeeds.
- Running `find` more than a few times a day gains little. Most boards change slowly.

## Adding an adapter

Create `scripts/jobhunter/sources/<name>.py` with `parse(payload, board) -> list[RawJob]` (pure,
tested with a fixture) and `fetch(board, http)`. Optionally add `fetch_one(board, job_id, http)`.
Register it in `sources/__init__.py` and add a fixture test in `tests/`.
