"""Common raw-job shape produced by every adapter."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class RawJob:
    source: str                  # ats name, e.g. "greenhouse"
    board: str                   # board token
    native_id: str
    company: str
    title: str
    url: str | None              # public posting URL
    apply_url: str | None = None
    locations: list[str] = field(default_factory=list)
    remote_hint: str | None = None   # remote | hybrid | onsite | None (unknown)
    posted_at: str | None = None     # ISO date
    description: str = ""            # HTML or text; sanitised later
    salary: dict | None = None
    department: str | None = None
    aggregator: bool = False

    @property
    def id(self) -> str:
        return f"{self.source}:{self.board.lower()}:{self.native_id}"


def iso_from_ms(ms) -> str | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def iso_date(s) -> str | None:
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return s[:10] if len(s) >= 10 and s[4] == "-" else None


def as_list(x) -> list:
    return x if isinstance(x, list) else []
