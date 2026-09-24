# CLI reference

```
jh init                         create ~/.job-hunter/{config,state,cv,applications}
jh find [N] [--source X]        fetch all boards (or one ats/token/company) and show unseen jobs
jh fetch [--source X]           fetch + process only (e.g. from cron)
jh new [N]                      unseen jobs from the DB, no network
jh show <words> [N]             best | all | appsec | red team | research | cloud | detection | tooling
                                | emea | eligible | stretch | shortlist | applied | rejected | <free text>
jh why <n|id>                   score breakdown + extracted fields
jh reject <n> [reason] [--company]   hide; --company also blocks the employer
jh shortlist <n> | applied <n> [--cv NAME] | status <n> interviewing|offer|declined|ghosted
jh undo <n>                     clear your status for a job
jh apply <n>                    application pack (see application.md)
jh digest [N]                   compact JSONL of top un-assessed jobs (for LLM review)
jh assess <n> --label L --note T     cache a verdict; shown until the posting changes
jh add <url> [--title --company --location --text-file]
jh block <company> | block --title <regex> | block --remove ...
jh sources [list|verify|add <ats>:<token> [Name]]
jh rescore                      re-score stored jobs after config edits (no network)
jh stats | jh export [path]
```

## Files

```
~/.job-hunter/
  config/profile.toml     your facts, skill levels, targets, CV variants   (copy of profile.example.toml)
  config/search.toml      optional overrides of bundled search.toml (filters, weights, fx)
  config/companies.toml   extra boards; [settings] include_bundled = false to use only yours
  config/skills.toml      optional taxonomy additions
  state/jobs.db           SQLite: jobs, job_text, user_state, rules, sources, events
  cv/*.pdf                CV variants referenced by [[cv]] entries
  applications/…/pack.md  per-application workspaces
```

## Scheduling

`jh fetch` is safe to run from cron once or twice a day. `jh new` then shows the results without
network access. Remotive's ToS asks for low polling frequency, so don't run it hourly.

## Tests

`cd tests && python3 -m unittest` (stdlib unittest; pytest also works). All tests are offline and use fixtures.
