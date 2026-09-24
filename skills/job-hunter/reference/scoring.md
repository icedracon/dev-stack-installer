# Eligibility, scoring and labels

## Pipeline

```
fetch boards (1 req each) → title prefilter (regex; drops SOC L1, GRC, managers, non-security)
→ [SmartRecruiters detail only for survivors] → HTML→text, sanitise
→ eligibility (geo.py) + extraction (extract.py) → hard filters → additive score → dedup → SQLite
```
Unchanged postings (same `raw_hash` and same config hash) are only touched (`last_seen`), not re-processed.
Editing config triggers a local re-score. No network or LLM needed.

## Eligibility (`yes | no | uncertain`)

"no" needs explicit evidence. "yes" needs explicit evidence. Everything else is "uncertain".

- **yes**: location lists Armenia/Yerevan, remote + worldwide/"anywhere", or remote + the posting mentions Armenia.
- **no**: clearance required (TS/SCI, SC, DV, public trust…); citizenship required; "must be based/located in X",
  or "authorized to work in X", where X excludes Armenia (EU, UK, US…); onsite/hybrid outside Armenia;
  remote restricted to named countries.
- **uncertain**: remote EMEA/Europe/CIS/Middle East (Armenia is *often* but not always included, and many
  "Europe" roles hire only through EU/UK entities); bare "Remote" (often means HQ country); no data.

Known weak spots: negation handling is a 50-char look-back; country lists inside prose are only partly
parsed; "EU" and "Europe" are distinguished, but employers use them loosely.

## Score (sum of components; `why <n>` shows each)

| Component | Default | Rule |
|---|---|---|
| role | 25 / 14 | primary / secondary target category (from title) |
| skills | 0–40 | 40 × weighted overlap. Overlap = Σ w·min(level,3)/3 ÷ Σ w, with w=1 for required skills and 0.5 for preferred ones |
| location | 12 / 5 | eligible yes / uncertain |
| experience | 10 … −12 | 10 − 4 × (years short). 5 if unknown |
| seniority | −8 / −3 | staff/principal or lead when you have < 8 years |
| salary | +3 / −12 | meets / below `min_salary_usd_year` (approximate FX) |
| fresh | +3 / +1 | posted ≤ 7 / ≤ 30 days |
| company | +5 | in `companies.preferred` |

Labels: eligibility "no" → **Ineligible**; low data confidence → **Needs verification**; gap ≥ 3 years with
overlap ≥ 55%, or staff/principal → **Stretch**; ≥ 65 and overlap ≥ 50% → **Strong match**; ≥ 50 →
**Reasonable match**; ≥ 35 → **Stretch**; else **Poor match**.

"Data confidence" (low/medium/high) measures how much could be extracted: description length, remote
known, eligibility decided, years found, ≥ 3 skills. It says nothing about the quality of the match.

## Calibrating

The weights are guesses. After about 30 decisions, compare what you shortlisted with what you rejected
(`jh stats`, `jh show rejected`) and adjust `[scoring]` in `~/.job-hunter/config/search.toml`, then run
`jh rescore`. The score is a ranking aid. It is not a hiring probability.

Keyword stuffing is the main way to game the score: a posting listing every buzzword gets high overlap.
Skills are only counted once each, so the effect is bounded, but it isn't eliminated.
