"""SQLite persistence. One file (state/jobs.db) replaces seen/applied/rejected/preferences
JSON files: atomic writes, indexed queries, and no need to load everything into memory
(or into an LLM context) to answer "have I seen this?"."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,                -- {source}:{board}:{native_id}
    source TEXT NOT NULL, board TEXT NOT NULL, aggregator INTEGER DEFAULT 0,
    company TEXT NOT NULL, company_key TEXT NOT NULL,
    title TEXT NOT NULL, title_key TEXT NOT NULL, fingerprint TEXT NOT NULL,
    url TEXT, apply_url TEXT,
    locations TEXT,                     -- JSON list
    remote TEXT, regions TEXT, eligible TEXT, eligibility_reason TEXT,
    clearance TEXT, visa TEXT, concerns TEXT,
    category TEXT, tier TEXT, seniority TEXT, experience_min INTEGER,
    skills_required TEXT, skills_preferred TEXT, certs TEXT,
    salary TEXT, salary_usd REAL,
    department TEXT, posted_at TEXT,
    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, closed_at TEXT,
    raw_hash TEXT NOT NULL,             -- hash of source content; unchanged => skip re-extraction
    injection_flags TEXT,
    filtered_reason TEXT,               -- non-null => dropped by hard filter
    dup_of TEXT,
    score REAL, label TEXT, breakdown TEXT, confidence TEXT, overlap REAL,
    score_ctx TEXT,                     -- config hash used for the score
    llm_label TEXT, llm_note TEXT, llm_hash TEXT,  -- cached LLM verdict, valid while llm_hash == raw_hash
    shown_count INTEGER DEFAULT 0, last_shown TEXT
);
CREATE INDEX IF NOT EXISTS ix_jobs_fp ON jobs(fingerprint);
CREATE INDEX IF NOT EXISTS ix_jobs_board ON jobs(source, board);
CREATE INDEX IF NOT EXISTS ix_jobs_rank ON jobs(closed_at, filtered_reason, dup_of, score);

CREATE TABLE IF NOT EXISTS job_text (id TEXT PRIMARY KEY, text TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS user_state (      -- never touched by ingestion
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,                     -- shortlisted|rejected|applied|interviewing|offer|declined|ghosted|preparing
    reason TEXT, cv_variant TEXT, applied_at TEXT, notes TEXT, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (ts TEXT NOT NULL, job_id TEXT, action TEXT NOT NULL, detail TEXT);

CREATE TABLE IF NOT EXISTS rules (           -- learned preferences: block company / title pattern
    kind TEXT NOT NULL, value TEXT NOT NULL, reason TEXT, created_at TEXT NOT NULL,
    PRIMARY KEY (kind, value)
);

CREATE TABLE IF NOT EXISTS sources (
    key TEXT PRIMARY KEY,                     -- {ats}:{token}
    last_ok TEXT, last_error TEXT, last_count INTEGER, payload_hash TEXT,
    consecutive_failures INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS last_list (pos INTEGER PRIMARY KEY, job_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

JSON_COLS = {"locations", "regions", "concerns", "skills_required", "skills_preferred", "certs", "salary",
             "injection_flags", "breakdown"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DB:
    def __init__(self, path: Path | str):
        path = Path(path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self.conn.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
        self.conn.commit()

    # ---- helpers ----
    @staticmethod
    def decode(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        d = dict(row)
        for k in JSON_COLS & d.keys():
            if d[k]:
                try:
                    d[k] = json.loads(d[k])
                except (TypeError, json.JSONDecodeError):
                    d[k] = None
        return d

    def commit(self):
        self.conn.commit()

    def log(self, action: str, job_id: str | None = None, detail: str | None = None):
        self.conn.execute("INSERT INTO events VALUES (?,?,?,?)", (now(), job_id, action, detail))

    # ---- jobs ----
    def get(self, job_id: str) -> dict | None:
        return self.decode(self.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def raw_hash(self, job_id: str) -> tuple[str, str] | None:
        r = self.conn.execute("SELECT raw_hash, score_ctx FROM jobs WHERE id=?", (job_id,)).fetchone()
        return (r[0], r[1]) if r else None

    def upsert(self, rec: dict, text: str | None = None):
        rec = {k: (json.dumps(v) if k in JSON_COLS and v is not None else v) for k, v in rec.items()}
        cols = list(rec)
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in ("id", "first_seen", "shown_count", "last_shown",
                                                                           "llm_label", "llm_note", "llm_hash"))
        self.conn.execute(
            f"INSERT INTO jobs ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            [rec[c] for c in cols],
        )
        if text is not None:
            self.conn.execute("INSERT INTO job_text VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET text=excluded.text",
                              (rec["id"], text))

    def touch(self, job_id: str, ts: str):
        self.conn.execute("UPDATE jobs SET last_seen=?, closed_at=NULL WHERE id=?", (ts, job_id))

    def update_fields(self, job_id: str, **fields):
        fields = {k: (json.dumps(v) if k in JSON_COLS and v is not None else v) for k, v in fields.items()}
        sets = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE jobs SET {sets} WHERE id=?", [*fields.values(), job_id])

    def text(self, job_id: str) -> str:
        r = self.conn.execute("SELECT text FROM job_text WHERE id=?", (job_id,)).fetchone()
        return r[0] if r else ""

    def close_missing(self, source: str, board: str, seen_ids: set[str], ts: str) -> int:
        """Mark jobs from a SUCCESSFULLY fetched board that were not in the response as closed."""
        rows = self.conn.execute(
            "SELECT id FROM jobs WHERE source=? AND lower(board)=lower(?) AND closed_at IS NULL", (source, board)).fetchall()
        gone = [r[0] for r in rows if r[0] not in seen_ids]
        self.conn.executemany("UPDATE jobs SET closed_at=? WHERE id=?", [(ts, g) for g in gone])
        return len(gone)

    def by_fingerprint(self, fp: str, exclude_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT j.*, u.status AS user_status FROM jobs j LEFT JOIN user_state u ON u.job_id=j.id "
            "WHERE fingerprint=? AND id<>?", (fp, exclude_id)).fetchall()
        return [self.decode(r) for r in rows]

    def all_ids_for_rescore(self, ctx: str) -> list[str]:
        return [r[0] for r in self.conn.execute(
            "SELECT id FROM jobs WHERE closed_at IS NULL AND (score_ctx IS NULL OR score_ctx<>?)", (ctx,))]

    # ---- user state ----
    def state(self, job_id: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM user_state WHERE job_id=?", (job_id,)).fetchone()
        return dict(r) if r else None

    def set_state(self, job_id: str, status: str, **extra):
        cur = self.state(job_id) or {}
        row = {"job_id": job_id, "status": status, "reason": extra.get("reason", cur.get("reason")),
               "cv_variant": extra.get("cv_variant", cur.get("cv_variant")),
               "applied_at": extra.get("applied_at", cur.get("applied_at")),
               "notes": extra.get("notes", cur.get("notes")), "updated_at": now()}
        self.conn.execute(
            "INSERT INTO user_state VALUES (:job_id,:status,:reason,:cv_variant,:applied_at,:notes,:updated_at) "
            "ON CONFLICT(job_id) DO UPDATE SET status=excluded.status, reason=excluded.reason, "
            "cv_variant=excluded.cv_variant, applied_at=excluded.applied_at, notes=excluded.notes, "
            "updated_at=excluded.updated_at", row)
        self.log(status, job_id, extra.get("reason"))

    # ---- rules ----
    def add_rule(self, kind: str, value: str, reason: str | None = None):
        self.conn.execute("INSERT OR REPLACE INTO rules VALUES (?,?,?,?)", (kind, value, reason, now()))

    def rules(self, kind: str) -> list[str]:
        return [r[0] for r in self.conn.execute("SELECT value FROM rules WHERE kind=?", (kind,))]

    def remove_rule(self, kind: str, value: str) -> int:
        return self.conn.execute("DELETE FROM rules WHERE kind=? AND value=?", (kind, value)).rowcount

    # ---- sources ----
    def source(self, key: str) -> dict:
        r = self.conn.execute("SELECT * FROM sources WHERE key=?", (key,)).fetchone()
        return dict(r) if r else {"key": key, "consecutive_failures": 0, "payload_hash": None}

    def source_ok(self, key: str, count: int, payload_hash: str):
        self.conn.execute(
            "INSERT INTO sources (key,last_ok,last_error,last_count,payload_hash,consecutive_failures) "
            "VALUES (?,?,NULL,?,?,0) ON CONFLICT(key) DO UPDATE SET last_ok=excluded.last_ok, last_error=NULL, "
            "last_count=excluded.last_count, payload_hash=excluded.payload_hash, consecutive_failures=0",
            (key, now(), count, payload_hash))

    def source_fail(self, key: str, error: str):
        self.conn.execute(
            "INSERT INTO sources (key,last_error,consecutive_failures) VALUES (?,?,1) "
            "ON CONFLICT(key) DO UPDATE SET last_error=excluded.last_error, "
            "consecutive_failures=consecutive_failures+1", (key, error[:300]))

    def sources_all(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM sources ORDER BY key")]

    # ---- list positions ("reject 4") ----
    def set_last_list(self, ids: list[str]):
        self.conn.execute("DELETE FROM last_list")
        self.conn.executemany("INSERT INTO last_list VALUES (?,?)", list(enumerate(ids, 1)))

    def resolve(self, ref: str) -> str | None:
        ref = str(ref).strip().lstrip("#")
        if ref.isdigit():
            r = self.conn.execute("SELECT job_id FROM last_list WHERE pos=?", (int(ref),)).fetchone()
            return r[0] if r else None
        if self.conn.execute("SELECT 1 FROM jobs WHERE id=?", (ref,)).fetchone():
            return ref
        rows = self.conn.execute("SELECT id FROM jobs WHERE id LIKE ? LIMIT 2", (f"%{ref}%",)).fetchall()
        return rows[0][0] if len(rows) == 1 else None

    def mark_shown(self, ids: list[str]):
        ts = now()
        self.conn.executemany("UPDATE jobs SET shown_count=shown_count+1, last_shown=? WHERE id=?", [(ts, i) for i in ids])
