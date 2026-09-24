"""Greenhouse Job Board API (public, no auth): boards-api.greenhouse.io/v1/boards/{token}/jobs"""
from __future__ import annotations

from .base import RawJob, as_list, iso_date

API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def parse_job(j: dict, board: dict) -> RawJob | None:
    if not isinstance(j, dict) or not j.get("id") or not j.get("title"):
        return None
    locs = []
    loc = (j.get("location") or {}).get("name") if isinstance(j.get("location"), dict) else None
    if loc:
        locs.append(loc)
    for office in as_list(j.get("offices")):
        name = office.get("name") if isinstance(office, dict) else None
        if name and name not in locs:
            locs.append(name)
    depts = [d.get("name") for d in as_list(j.get("departments")) if isinstance(d, dict) and d.get("name")]
    return RawJob(
        source="greenhouse",
        board=board["token"],
        native_id=str(j["id"]),
        company=board.get("company") or j.get("company_name") or board["token"],
        title=j["title"],
        url=j.get("absolute_url"),
        apply_url=j.get("absolute_url"),
        locations=locs,
        posted_at=iso_date(j.get("first_published") or j.get("updated_at")),
        description=j.get("content") or "",
        department=", ".join(depts) or None,
    )


def parse(payload: dict, board: dict) -> list[RawJob]:
    return [r for r in (parse_job(j, board) for j in as_list((payload or {}).get("jobs"))) if r]


def fetch(board: dict, http) -> list[RawJob]:
    return parse(http.get_json(API.format(token=board["token"]), {"content": "true"}), board)


def fetch_one(board: dict, job_id: str, http) -> RawJob | None:
    return parse_job(http.get_json(f"{API.format(token=board['token'])}/{job_id}"), board)
