"""DISCOVERY -> TITLE PREFILTER -> NORMALISE -> HARD FILTERS -> SCORE -> DEDUP -> persist.

Cost model: everything here is local CPU. The only network cost is one request per
board (plus per-posting detail calls for SmartRecruiters survivors). No LLM calls."""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import extract, geo, sanitize, scoring
from .config import Config
from .db import DB, now
from .http import FetchError, Http
from .sources import ADAPTERS, SOURCE_PRIORITY
from .sources.base import RawJob
from .urls import canonical_url, strip_tracking

ELIG_RANK = {"yes": 0, "uncertain": 1, "no": 2, None: 3}
DISABLE_AFTER_FAILURES = 3


@dataclass
class RunStats:
    boards_ok: int = 0
    boards_failed: list = field(default_factory=list)
    boards_skipped: list = field(default_factory=list)
    fetched: int = 0
    title_filtered: int = 0
    unchanged: int = 0
    new: int = 0
    updated: int = 0
    hard_filtered: int = 0
    closed: int = 0
    duplicates: int = 0
    inherited: int = 0
    requests: int = 0

    def funnel(self) -> str:
        relevant = self.fetched - self.title_filtered
        return (f"{self.fetched} fetched → {relevant} relevant titles → {self.new} new, {self.updated} changed, "
                f"{self.unchanged} unchanged → {self.hard_filtered} hard-filtered · {self.closed} closed · "
                f"{self.duplicates} dupes · {self.boards_ok} boards ok, {len(self.boards_failed)} failed")


def raw_hash(r: RawJob) -> str:
    blob = json.dumps([r.title, r.locations, r.remote_hint, r.description, r.salary, r.apply_url], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:20]


def fingerprint(company: str, title: str) -> str:
    return hashlib.sha1(f"{extract.company_key(company)}|{extract.title_key(title)}".encode()).hexdigest()[:16]


class Pipeline:
    def __init__(self, cfg: Config, db: DB, http: Http | None = None, today: date | None = None):
        self.cfg, self.db = cfg, db
        self.http = http or Http(cfg.search.get("run", {}))
        self.today = today or date.today()
        self.ctx = cfg.scoring_hash()
        self.classifier = extract.TitleClassifier(cfg.search, db.rules("title"))
        self.blocked = {extract.company_key(c) for c in cfg.profile.get("companies", {}).get("blocked", [])}
        self.blocked |= {extract.company_key(c) for c in db.rules("company")}

    # ---------- discovery ----------
    def fetch_all(self, only: str | None = None) -> tuple[RunStats, list[tuple[dict, list[RawJob]]]]:
        stats = RunStats()
        boards = [b for b in self.cfg.boards if b.get("ats") in ADAPTERS]
        if only:
            o = only.lower()
            boards = [b for b in boards if o in (b["ats"], str(b["token"]).lower(), str(b.get("company", "")).lower())]
        active = []
        for b in boards:
            state = self.db.source(f"{b['ats']}:{b['token']}")
            if state.get("consecutive_failures", 0) >= DISABLE_AFTER_FAILURES and not only:
                stats.boards_skipped.append(f"{b['ats']}:{b['token']}")
            else:
                active.append(b)
        # one worker per API host; sequential (throttled) within a host
        groups: dict[str, list[dict]] = defaultdict(list)
        for b in active:
            groups[b["ats"] + (b.get("region") or "")].append(b)

        def run_group(bs):
            out = []
            for b in bs:
                try:
                    out.append((b, ADAPTERS[b["ats"]].fetch(b, self.http), None))
                except FetchError as e:
                    out.append((b, None, str(e)))
                except Exception as e:  # malformed payloads must not kill the run
                    out.append((b, None, f"{type(e).__name__}: {e}"))
            return out

        results = []
        with ThreadPoolExecutor(max_workers=max(1, min(6, len(groups)))) as ex:
            for group_result in ex.map(run_group, groups.values()):
                results.extend(group_result)
        ok = [(b, jobs) for b, jobs, err in results if not err]
        # If every board failed, the problem is our network, not the boards: don't count it
        # towards auto-disabling (otherwise one offline run could disable every source).
        count_failures = bool(ok) or len(results) == 1
        for b, jobs, err in results:
            if err:
                key = f"{b['ats']}:{b['token']}"
                if count_failures:
                    self.db.source_fail(key, err)
                stats.boards_failed.append(f"{key} ({err[:100]})")
        stats.requests = self.http.requests
        return stats, ok

    # ---------- per-job processing ----------
    def _prefilter(self, r: RawJob) -> str | None:
        if extract.company_key(r.company) in self.blocked:
            return "blocked company"
        hit = self.classifier.excluded_by(r.title)
        if hit:
            return f"excluded title /{hit}/"
        cat, _ = self.classifier.category(r.title)
        if not cat:
            return "not a target role"
        if scoring.tier_for(cat, self.cfg.profile) is None:
            return f"category {cat} not in targets"
        return None

    def normalise(self, r: RawJob) -> tuple[dict, str]:
        text = sanitize.html_to_text(r.description)
        title = sanitize.one_line(r.title, 200)
        company = sanitize.one_line(r.company, 100)
        locations = [sanitize.one_line(x, 120) for x in r.locations if x]
        el = geo.assess(locations, text, remote_hint=r.remote_hint, profile=self.cfg.profile,
                        loc_cfg=self.cfg.search.get("location", {}))
        sk = extract.extract_skills(text, self.cfg.skills)
        salary = r.salary
        if salary and salary.get("text") and not salary.get("max"):
            salary = extract.parse_salary(salary["text"]) or salary
        salary = salary or extract.parse_salary(text)
        cat, _ = self.classifier.category(title)
        rec = {
            "id": r.id, "source": r.source, "board": r.board, "aggregator": int(r.aggregator),
            "company": company, "company_key": extract.company_key(company),
            "title": title, "title_key": extract.title_key(title), "fingerprint": fingerprint(company, title),
            "url": canonical_url(sanitize.safe_url(r.url)), "apply_url": strip_tracking(sanitize.safe_url(r.apply_url or r.url)),
            "locations": locations, "remote": el.remote, "regions": el.regions,
            "eligible": el.status, "eligibility_reason": el.reason,
            "clearance": el.clearance, "visa": el.visa, "concerns": el.concerns,
            "category": cat, "tier": scoring.tier_for(cat, self.cfg.profile),
            "seniority": extract.seniority(title), "experience_min": sk["years"],
            "skills_required": sk["required"], "skills_preferred": sk["preferred"], "certs": sk["certs"],
            "salary": salary, "salary_usd": extract.annual_usd(salary, self.cfg.search.get("fx", {})),
            "department": sanitize.one_line(r.department, 80) or None, "posted_at": r.posted_at,
            "injection_flags": sanitize.injection_flags(text) or None,
            "_text_len": len(text),
        }
        return rec, text

    def hard_filter(self, rec: dict) -> str | None:
        f = self.cfg.search.get("filters", {})
        if rec["eligible"] == "no" and not self.cfg.search.get("location", {}).get("show_ineligible", False):
            return f"ineligible: {rec['eligibility_reason']}"
        if rec["seniority"] in f.get("exclude_seniority", []):
            return f"seniority {rec['seniority']}"
        if rec.get("experience_min") and rec["experience_min"] > f.get("max_experience_years", 12):
            return f"asks {rec['experience_min']}+ years"
        max_age = self.cfg.run("max_age_days", 60)
        if rec.get("posted_at") and max_age:
            try:
                if date.fromisoformat(rec["posted_at"][:10]) < self.today - timedelta(days=max_age):
                    return f"posted > {max_age} days ago"
            except ValueError:
                pass
        return None

    def ingest(self, raws: list[RawJob], stats: RunStats, ts: str) -> set[str]:
        touched_fps: set[str] = set()
        for r in raws:
            stats.fetched += 1
            h = raw_hash(r)
            known = self.db.raw_hash(r.id)
            if known and known[0] == h and known[1] == self.ctx:
                self.db.touch(r.id, ts)
                stats.unchanged += 1
                continue
            # content or config changed -> full local re-processing (cheap; no LLM involved)
            pre = self._prefilter(r)
            if pre:
                stats.title_filtered += 1
                self.db.upsert({"id": r.id, "source": r.source, "board": r.board, "company": sanitize.one_line(r.company, 100),
                                "company_key": extract.company_key(r.company), "title": sanitize.one_line(r.title, 200),
                                "title_key": extract.title_key(r.title), "fingerprint": fingerprint(r.company, r.title),
                                "url": canonical_url(sanitize.safe_url(r.url)), "first_seen": ts, "last_seen": ts,
                                "closed_at": None, "raw_hash": h, "filtered_reason": pre, "score_ctx": self.ctx})
                continue
            if r.source == "smartrecruiters" and ADAPTERS["smartrecruiters"].needs_detail(r):
                try:
                    r = ADAPTERS["smartrecruiters"].fetch_detail(r, self.http)
                except FetchError:
                    pass  # score on title/location only; confidence will be low
            rec, text = self.normalise(r)
            rec.update(self._score_fields(rec))
            rec.update({"first_seen": ts, "last_seen": ts, "closed_at": None, "raw_hash": h,
                        "filtered_reason": self.hard_filter(rec), "score_ctx": self.ctx, "dup_of": None})
            rec.pop("_text_len", None)
            if rec["filtered_reason"]:
                stats.hard_filtered += 1
            if known and known[0] != h:
                stats.updated += 1
            elif known:
                stats.unchanged += 1  # same content, re-scored under new config
            else:
                stats.new += 1
                stats.inherited += self._inherit_state(rec)
            self.db.upsert(rec, text)
            touched_fps.add(rec["fingerprint"])
        return touched_fps

    def _score_fields(self, rec: dict) -> dict:
        s = scoring.score(rec, self.cfg.profile, self.cfg.search, self.today)
        return {"score": s["score"], "label": s["label"], "confidence": s["confidence"], "overlap": s["overlap"],
                "breakdown": s["breakdown"]}

    def rescore(self, job_id: str):
        """Profile/config changed: re-score from stored fields (no refetch, no LLM)."""
        rec = self.db.get(job_id)
        if not rec or rec.get("category") is None:
            if rec and rec.get("filtered_reason"):  # title filtered under old config: re-check title
                self.db.update_fields(job_id, score_ctx=self.ctx)
            return
        rec["tier"] = scoring.tier_for(rec["category"], self.cfg.profile)
        rec["_text_len"] = len(self.db.text(job_id))
        fields = self._score_fields(rec)
        fields["tier"] = rec["tier"]
        fields["filtered_reason"] = self.hard_filter(rec) or (None if rec["tier"] else "category not in targets")
        self.db.update_fields(job_id, score_ctx=self.ctx, **fields)

    def _inherit_state(self, rec: dict) -> int:
        """A reposted job (new id, same company+title) inherits rejected/applied state."""
        for other in self.db.by_fingerprint(rec["fingerprint"], rec["id"]):
            st = other.get("user_status")
            if st in ("rejected", "applied", "interviewing", "offer", "declined"):
                self.db.set_state(rec["id"], st, reason=f"inherited from repost of {other['id']}")
                return 1
        return 0

    def dedupe(self, fps: set[str]) -> int:
        dupes = 0
        for fp in fps:
            rows = [self.db.decode(r) for r in self.db.conn.execute(
                "SELECT * FROM jobs WHERE fingerprint=? AND closed_at IS NULL AND filtered_reason IS NULL", (fp,))]
            if len(rows) < 2:
                for r in rows:
                    self.db.update_fields(r["id"], dup_of=None)
                continue
            rows.sort(key=lambda r: (SOURCE_PRIORITY.get(r["source"], 3), ELIG_RANK.get(r["eligible"], 3),
                                     -(r["score"] or 0), r["first_seen"]))
            rep = rows[0]["id"]
            self.db.update_fields(rep, dup_of=None)
            for r in rows[1:]:
                self.db.update_fields(r["id"], dup_of=rep)
                dupes += 1
        return dupes

    # ---------- orchestration ----------
    def run(self, only: str | None = None) -> RunStats:
        ts = now()
        stats, results = self.fetch_all(only)
        fps: set[str] = set()
        for board, jobs in results:
            key = f"{board['ats']}:{board['token']}"
            payload_hash = hashlib.sha256(json.dumps([raw_hash(j) for j in jobs]).encode()).hexdigest()[:20]
            fps |= self.ingest(jobs, stats, ts)
            stats.closed += self.db.close_missing(board["ats"], board["token"], {j.id for j in jobs}, ts)
            self.db.source_ok(key, len(jobs), payload_hash)
            stats.boards_ok += 1
        for jid in self.db.all_ids_for_rescore(self.ctx):
            self.rescore(jid)
        stats.duplicates = self.dedupe(fps)
        self.db.log("run", None, stats.funnel())
        self.db.commit()
        return stats

    def ingest_manual(self, raw: RawJob) -> str:
        ts = now()
        stats = RunStats()
        fps = self.ingest([raw], stats, ts)
        # manual additions bypass the title prefilter's "not a target role" (the user chose it)
        if stats.title_filtered:
            rec, text = self.normalise(raw)
            rec.update(self._score_fields(rec))
            rec.pop("_text_len", None)
            rec.update({"first_seen": ts, "last_seen": ts, "closed_at": None, "raw_hash": raw_hash(raw),
                        "filtered_reason": None, "score_ctx": self.ctx})
            self.db.upsert(rec, text)
            fps.add(rec["fingerprint"])
        self.dedupe(fps)
        self.db.commit()
        return raw.id


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:40]
