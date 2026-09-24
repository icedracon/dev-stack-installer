"""Ashby public Job Posting API: api.ashbyhq.com/posting-api/job-board/{board}"""
from __future__ import annotations

from .base import RawJob, as_list, iso_date

API = "https://api.ashbyhq.com/posting-api/job-board/{token}"
_WORKPLACE = {"remote": "remote", "hybrid": "hybrid", "onsite": "onsite", "on-site": "onsite"}


def parse_job(j: dict, board: dict) -> RawJob | None:
    if not isinstance(j, dict) or not j.get("id") or not j.get("title"):
        return None
    if j.get("isListed") is False:
        return None
    locs = [j["location"]] if isinstance(j.get("location"), str) and j.get("location") else []
    for sec in as_list(j.get("secondaryLocations")):
        name = sec.get("location") if isinstance(sec, dict) else None
        if name and name not in locs:
            locs.append(name)
    country = (((j.get("address") or {}).get("postalAddress") or {}).get("addressCountry"))
    if country and not any(country.lower() in l.lower() for l in locs):
        locs.append(country)
    remote = _WORKPLACE.get(str(j.get("workplaceType") or "").lower())
    if remote is None and j.get("isRemote") is True:
        remote = "remote"
    comp = j.get("compensation") or {}
    salary = None
    summary = comp.get("compensationTierSummary") or comp.get("scrapeableCompensationSalarySummary")
    if summary:
        salary = {"text": summary}
    return RawJob(
        source="ashby",
        board=board["token"],
        native_id=str(j["id"]),
        company=board.get("company") or board["token"],
        title=j["title"],
        url=j.get("jobUrl"),
        apply_url=j.get("applyUrl") or j.get("jobUrl"),
        locations=locs,
        remote_hint=remote,
        posted_at=iso_date(j.get("publishedAt")),
        description=j.get("descriptionHtml") or j.get("descriptionPlain") or "",
        salary=salary,
        department=j.get("department") or j.get("team"),
    )


def parse(payload: dict, board: dict) -> list[RawJob]:
    return [r for r in (parse_job(j, board) for j in as_list((payload or {}).get("jobs"))) if r]


def fetch(board: dict, http) -> list[RawJob]:
    return parse(http.get_json(API.format(token=board["token"]), {"includeCompensation": "true"}), board)


def fetch_one(board: dict, job_id: str, http) -> RawJob | None:
    # No public single-posting endpoint: fetch the board and pick the job.
    return next((j for j in fetch(board, http) if j.native_id == job_id), None)
