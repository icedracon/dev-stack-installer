"""Source adapter registry. Each module exposes parse(payload, board) and fetch(board, http);
ATS adapters also expose fetch_one(board, job_id, http) for `jh add <url>`."""
from . import ashby, greenhouse, lever, remotive, smartrecruiters, workable

ADAPTERS = {
    "greenhouse": greenhouse,
    "lever": lever,
    "ashby": ashby,
    "workable": workable,
    "smartrecruiters": smartrecruiters,
    "remotive": remotive,
}

# Lower number = preferred when the same job appears in several sources.
SOURCE_PRIORITY = {"greenhouse": 0, "lever": 0, "ashby": 0, "workable": 0, "smartrecruiters": 0,
                   "manual": 1, "remotive": 5}
