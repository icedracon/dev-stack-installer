"""Remotive public API (aggregator): remotive.com/api/remote-jobs?category=...

Lower trust: listings are delayed ~24h, apply links go through Remotive, and the ToS
asks for a low polling frequency. Useful mainly for `candidate_required_location`."""
from __future__ import annotations

from .base import RawJob, as_list, iso_date

API = "https://remotive.com/api/remote-jobs"


def parse_job(j: dict, board: dict) -> RawJob | None:
    if not isinstance(j, dict) or not j.get("id") or not j.get("title"):
        return None
    loc = j.get("candidate_required_location") or ""
    salary = {"text": j["salary"]} if j.get("salary") else None
    return RawJob(
        source="remotive",
        board=board["token"],
        native_id=str(j["id"]),
        company=j.get("company_name") or "unknown",
        title=j["title"],
        url=j.get("url"),
        apply_url=j.get("url"),
        locations=[f"Remote - {loc}" if loc else "Remote"],
        remote_hint="remote",
        posted_at=iso_date(j.get("publication_date")),
        description=j.get("description") or "",
        salary=salary,
        department=j.get("category"),
        aggregator=True,
    )


def parse(payload: dict, board: dict) -> list[RawJob]:
    return [r for r in (parse_job(j, board) for j in as_list((payload or {}).get("jobs"))) if r]


def fetch(board: dict, http) -> list[RawJob]:
    return parse(http.get_json(API, {"category": board["token"]}), board)
