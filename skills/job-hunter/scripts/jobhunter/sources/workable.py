"""Workable public widget API: apply.workable.com/api/v1/widget/accounts/{account}?details=true"""
from __future__ import annotations

from .base import RawJob, as_list, iso_date

API = "https://apply.workable.com/api/v1/widget/accounts/{token}"


def parse_job(j: dict, board: dict, company: str | None = None) -> RawJob | None:
    if not isinstance(j, dict) or not j.get("shortcode") or not j.get("title"):
        return None
    locs = []
    for loc in as_list(j.get("locations")):
        if isinstance(loc, dict) and not loc.get("hidden"):
            text = ", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x)
            if text and text not in locs:
                locs.append(text)
    if not locs:
        text = ", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x)
        if text:
            locs.append(text)
    remote = "remote" if j.get("telecommuting") is True else None
    if remote is None and str(j.get("workplace") or "").lower() in ("hybrid", "on_site", "onsite"):
        remote = "hybrid" if j["workplace"].lower() == "hybrid" else "onsite"
    return RawJob(
        source="workable",
        board=board["token"],
        native_id=str(j["shortcode"]),
        company=board.get("company") or company or board["token"],
        title=j["title"],
        url=j.get("url") or j.get("shortlink"),
        apply_url=j.get("application_url") or j.get("url"),
        locations=locs,
        remote_hint=remote,
        posted_at=iso_date(j.get("published_on") or j.get("created_at")),
        description=j.get("description") or "",
        department=j.get("department"),
    )


def parse(payload: dict, board: dict) -> list[RawJob]:
    payload = payload or {}
    return [r for r in (parse_job(j, board, payload.get("name")) for j in as_list(payload.get("jobs"))) if r]


def fetch(board: dict, http) -> list[RawJob]:
    return parse(http.get_json(API.format(token=board["token"]), {"details": "true"}), board)


def fetch_one(board: dict, job_id: str, http) -> RawJob | None:
    return next((j for j in fetch(board, http) if j.native_id == job_id), None)
