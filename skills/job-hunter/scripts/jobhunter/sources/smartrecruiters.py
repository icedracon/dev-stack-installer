"""SmartRecruiters Posting API (public): api.smartrecruiters.com/v1/companies/{id}/postings

The list endpoint has no description, so details are fetched ONLY for postings whose
title survives the cheap title filter (see `needs_detail` in pipeline)."""
from __future__ import annotations

from .base import RawJob, as_list, iso_date

API = "https://api.smartrecruiters.com/v1/companies/{token}/postings"
PAGE = 100
MAX_PAGES = 20


def parse_job(j: dict, board: dict) -> RawJob | None:
    if not isinstance(j, dict) or not j.get("id") or not j.get("name"):
        return None
    loc = j.get("location") or {}
    text = loc.get("fullLocation") or ", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x)
    remote = "remote" if loc.get("remote") is True else ("hybrid" if loc.get("hybrid") is True else None)
    desc = ""
    sections = ((j.get("jobAd") or {}).get("sections") or {})
    for key in ("jobDescription", "qualifications", "additionalInformation"):
        sec = sections.get(key) or {}
        if sec.get("text"):
            desc += f"<h3>{sec.get('title', '')}</h3>{sec['text']}"
    token = board["token"]
    return RawJob(
        source="smartrecruiters",
        board=token,
        native_id=str(j["id"]),
        company=board.get("company") or (j.get("company") or {}).get("name") or token,
        title=j["name"],
        url=j.get("postingUrl") or f"https://jobs.smartrecruiters.com/{token}/{j['id']}",
        apply_url=j.get("applyUrl") or f"https://jobs.smartrecruiters.com/{token}/{j['id']}",
        locations=[text] if text else [],
        remote_hint=remote,
        posted_at=iso_date(j.get("releasedDate")),
        description=desc,
        department=(j.get("department") or {}).get("label") if isinstance(j.get("department"), dict) else None,
    )


def parse(payload: dict, board: dict) -> list[RawJob]:
    return [r for r in (parse_job(j, board) for j in as_list((payload or {}).get("content"))) if r]


def fetch(board: dict, http) -> list[RawJob]:
    out = []
    for page in range(MAX_PAGES):
        payload = http.get_json(API.format(token=board["token"]), {"limit": PAGE, "offset": page * PAGE})
        batch = parse(payload, board)
        out.extend(batch)
        if len(batch) < PAGE or len(out) >= int(payload.get("totalFound") or 0):
            break
    return out


def needs_detail(job: RawJob) -> bool:
    return not job.description


def fetch_detail(job: RawJob, http) -> RawJob:
    full = parse_job(http.get_json(f"{API.format(token=job.board)}/{job.native_id}"), {"token": job.board, "company": job.company})
    return full or job


def fetch_one(board: dict, job_id: str, http) -> RawJob | None:
    return parse_job(http.get_json(f"{API.format(token=board['token'])}/{job_id}"), board)
