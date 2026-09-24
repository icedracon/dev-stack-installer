"""Lever Postings API (public): api.lever.co/v0/postings/{company}?mode=json (EU: api.eu.lever.co)"""
from __future__ import annotations

from .base import RawJob, as_list, iso_from_ms

_WORKPLACE = {"remote": "remote", "hybrid": "hybrid", "onsite": "onsite", "on-site": "onsite"}


def _api(board: dict) -> str:
    host = "api.eu.lever.co" if board.get("region") == "eu" else "api.lever.co"
    return f"https://{host}/v0/postings/{board['token']}"


def parse_job(j: dict, board: dict) -> RawJob | None:
    if not isinstance(j, dict) or not j.get("id") or not j.get("text"):
        return None
    cats = j.get("categories") or {}
    locs = [x for x in as_list(cats.get("allLocations")) if isinstance(x, str)]
    if cats.get("location") and cats["location"] not in locs:
        locs.insert(0, cats["location"])
    parts = [j.get("descriptionPlain") or j.get("description") or ""]
    for block in as_list(j.get("lists")):
        if isinstance(block, dict):
            parts.append(f"\n{block.get('text', '')}:\n{block.get('content', '')}")
    parts.append(j.get("additionalPlain") or j.get("additional") or "")
    salary = None
    sr = j.get("salaryRange")
    if isinstance(sr, dict) and sr.get("min") and sr.get("max"):
        interval = str(sr.get("interval") or "").lower()
        salary = {"min": sr["min"], "max": sr["max"], "currency": sr.get("currency"),
                  "period": "hour" if "hour" in interval else "month" if "month" in interval else "year",
                  "text": f"{sr.get('currency', '')} {sr['min']}-{sr['max']} {interval}".strip()}
    return RawJob(
        source="lever",
        board=board["token"],
        native_id=str(j["id"]),
        company=board.get("company") or board["token"],
        title=j["text"],
        url=j.get("hostedUrl"),
        apply_url=j.get("applyUrl") or j.get("hostedUrl"),
        locations=locs,
        remote_hint=_WORKPLACE.get(str(j.get("workplaceType") or "").lower()),
        posted_at=iso_from_ms(j.get("createdAt")),
        description="\n".join(p for p in parts if p),
        salary=salary,
        department=cats.get("team") or cats.get("department"),
    )


def parse(payload, board: dict) -> list[RawJob]:
    return [r for r in (parse_job(j, board) for j in as_list(payload)) if r]


def fetch(board: dict, http) -> list[RawJob]:
    out, skip = [], 0
    while True:  # Lever paginates with skip/limit; most boards fit in one page
        page = http.get_json(_api(board), {"mode": "json", "skip": skip, "limit": 250})
        out.extend(parse(page, board))
        if not isinstance(page, list) or len(page) < 250:
            return out
        skip += 250


def fetch_one(board: dict, job_id: str, http) -> RawJob | None:
    return parse_job(http.get_json(f"{_api(board)}/{job_id}", {"mode": "json"}), board)
