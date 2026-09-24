"""`jh` command line. Every command is deterministic; the only LLM-facing outputs are
the compact listing, `digest`, and the `apply` pack."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from . import config as cfgmod
from . import cvroute, extract, render, sanitize
from .db import DB
from .http import FetchError, Http
from .pipeline import Pipeline, slug
from .sources import ADAPTERS
from .sources.base import RawJob
from .urls import parse_ats_url

CLOSED_STATUSES = ("rejected", "applied", "interviewing", "offer", "declined", "ghosted")
VIEW_WORDS = {
    "appsec": ("category IN ('appsec')", None), "prodsec": ("category IN ('appsec')", None),
    "product": ("category IN ('appsec')", None),
    "red": ("category IN ('redteam','offensive','pentest')", None), "redteam": ("category IN ('redteam','offensive','pentest')", None),
    "offensive": ("category IN ('redteam','offensive','pentest')", None), "pentest": ("category IN ('pentest','offensive')", None),
    "research": ("category IN ('research')", None), "cloud": ("category IN ('cloudsec')", None),
    "cloudsec": ("category IN ('cloudsec')", None), "detection": ("category IN ('detection')", None),
    "tooling": ("category IN ('tooling')", None), "infra": ("category IN ('infrasec')", None),
    "emea": ("(regions LIKE '%emea%' OR regions LIKE '%europe%' OR eligible='yes')", None),
    "eligible": ("eligible='yes'", None), "armenia": ("eligible='yes'", None),
    "stretch": ("label='Stretch'", None),
    "shortlist": (None, "shortlisted"), "shortlisted": (None, "shortlisted"), "applied": (None, "applied"),
    "rejected": (None, "rejected"), "interviewing": (None, "interviewing"),
}
IGNORED_WORDS = {"remote", "team", "jobs", "job", "show", "me", "the", "only", "best", "top", "security", "roles"}


def out(s: str = ""):
    sys.stdout.write(s + "\n")


def ctx():
    cfg = cfgmod.load()
    db = DB(cfg.db_path)
    return cfg, db


def _header(cfg) -> list[str]:
    return [f"⚠ {w}" for w in cfg.warnings]


def query_jobs(db: DB, where: list[str], params: list, limit: int, include_closed_user=False, order="score DESC") -> list[dict]:
    base = ["j.closed_at IS NULL", "j.filtered_reason IS NULL", "j.dup_of IS NULL"]
    if not include_closed_user:
        base.append(f"(u.status IS NULL OR u.status NOT IN ({','.join('?' * len(CLOSED_STATUSES))}))")
        params = [*CLOSED_STATUSES, *params]
    sql = ("SELECT j.*, u.status AS user_status FROM jobs j LEFT JOIN user_state u ON u.job_id=j.id WHERE "
           + " AND ".join(base + where) + f" ORDER BY {order} LIMIT ?")
    return [db.decode(r) for r in db.conn.execute(sql, [*params, limit])]


def show_list(cfg, db, jobs, header=None, footer=None, mark=True):
    db.set_last_list([j["id"] for j in jobs])
    if mark:
        db.mark_shown([j["id"] for j in jobs])
    db.commit()
    out(render.listing(jobs, _header(cfg) + (header or []), footer))


def _count(args_words: list[str], default: int) -> tuple[int, list[str]]:
    words, n = [], default
    for w in args_words:
        if w.isdigit():
            n = int(w)
        else:
            words.append(w.lower())
    return n, words


def _good_labels() -> str:
    return "j.label NOT IN ('Poor match','Ineligible')"


# ---------------- commands ----------------

def cmd_init(a):
    created = cfgmod.init_home()
    home = cfgmod.home_dir()
    out(f"JOB_HUNTER_HOME = {home}")
    out("\n".join(f"created {c}" for c in created) or "already initialised")
    out("Next: edit config/profile.toml (years, skill levels, certs; set verified = true), put CVs in cv/, "
        "then run `jh sources verify` and `jh find`.")


def cmd_fetch(a, show_after=False):
    cfg, db = ctx()
    pipe = Pipeline(cfg, db)
    stats = pipe.run(only=a.source)
    header = [f"Run: {stats.funnel()} · {stats.requests} HTTP requests"]
    if stats.inherited:
        header.append(f"{stats.inherited} reposts inherited your earlier reject/applied decision")
    if stats.boards_failed and not stats.boards_ok:
        header.append(f"ALL {len(stats.boards_failed)} boards failed. Likely no network access or a proxy blocking "
                      f"these hosts, not a problem with the boards. First error: {stats.boards_failed[0]}")
    elif stats.boards_failed:
        header.append("Failed boards: " + "; ".join(stats.boards_failed[:6]) + (" …" if len(stats.boards_failed) > 6 else ""))
    if stats.boards_skipped:
        header.append(f"Skipped {len(stats.boards_skipped)} boards after repeated failures (`jh sources` to review)")
    if not show_after:
        out("\n".join(_header(cfg) + header))
        return
    n = a.count or cfg.run("default_count", 10)
    jobs = query_jobs(db, ["j.shown_count=0", _good_labels()], [], n)
    footer = []
    if len(jobs) < n:
        seen = query_jobs(db, ["j.shown_count>0", _good_labels()], [], n - len(jobs))
        if seen:
            footer.append(f"\n({len(seen)} more good jobs were shown before; `jh show best` lists everything open.)")
    show_list(cfg, db, jobs, header + [f"Showing {len(jobs)} new jobs, best first."], footer)


def cmd_find(a):
    if a.no_fetch:
        return cmd_new(a)
    cmd_fetch(a, show_after=True)


def cmd_new(a):
    cfg, db = ctx()
    n = a.count or cfg.run("default_count", 10)
    show_list(cfg, db, query_jobs(db, ["j.shown_count=0", _good_labels()], [], n), ["Unseen jobs, best first."])


def cmd_show(a):
    cfg, db = ctx()
    n, words = _count(a.words, cfg.run("default_count", 10))
    where, params, status = [], [], None
    include_poor = "all" in words
    for w in words:
        if w in VIEW_WORDS:
            clause, st = VIEW_WORDS[w]
            if clause:
                where.append(clause)
            status = st or status
        elif w not in IGNORED_WORDS | {"all"}:
            where.append("(lower(j.title) LIKE ? OR lower(j.company) LIKE ?)")
            params += [f"%{w}%", f"%{w}%"]
    if status:
        rows = db.conn.execute(
            "SELECT j.*, u.status AS user_status FROM jobs j JOIN user_state u ON u.job_id=j.id WHERE u.status=? "
            "ORDER BY u.updated_at DESC LIMIT ?", (status, n)).fetchall()
        jobs = [db.decode(r) for r in rows]
    else:
        if not include_poor:
            where.append(_good_labels())
        jobs = query_jobs(db, where, params, n)
    show_list(cfg, db, jobs, [f"View: {' '.join(words) or 'best'}"], mark=not status)


def _resolve(db, ref) -> str:
    jid = db.resolve(ref)
    if not jid:
        sys.exit(f"Unknown job reference '{ref}'. Use the number from the last list or a job id.")
    return jid


def cmd_why(a):
    cfg, db = ctx()
    jid = _resolve(db, a.ref)
    j = db.get(jid)
    st = db.state(jid)
    j["user_status"] = st and st["status"]
    out(render.why(j, len(db.text(jid))))


def _set(a, status, **extra):
    cfg, db = ctx()
    jid = _resolve(db, a.ref)
    db.set_state(jid, status, **extra)
    j = db.get(jid)
    msg = f"{status}: {j['company']} — {j['title']}"
    if status == "rejected" and getattr(a, "company", False):
        db.add_rule("company", j["company"], "rejected via jh reject --company")
        msg += f"  (+ blocked company {j['company']})"
    db.commit()
    out(msg)


def cmd_reject(a):
    _set(a, "rejected", reason=" ".join(a.reason) or None)


def cmd_shortlist(a):
    _set(a, "shortlisted")


def cmd_applied(a):
    _set(a, "applied", applied_at=date.today().isoformat(), **({"cv_variant": a.cv} if a.cv else {}))


def cmd_status(a):
    _set(a, a.status, notes=" ".join(a.note) or None)


def cmd_undo(a):
    cfg, db = ctx()
    jid = _resolve(db, a.ref)
    db.conn.execute("DELETE FROM user_state WHERE job_id=?", (jid,))
    db.log("undo", jid)
    db.commit()
    out(f"cleared status for {jid}")


_FLAG_PATTERNS = {
    "work authorization / right-to-work question": r"authori[sz]ed to work|right to work|work permit|visa",
    "citizenship": r"citizen",
    "security clearance": r"clearance",
    "relocation / onsite expectation": r"relocat|on-?site|in[- ]office",
    "salary expectation question": r"salary expectation|expected compensation|desired salary",
    "background / reference checks": r"background check|references",
    "specific certification demanded": r"\b(oscp|osep|oswe|osed|crto|cissp|gpen|gxpn)\b[^.\n]{0,40}(required|must)",
    "degree requirement": r"(bachelor|master|degree)[^.\n]{0,40}(required|must|in computer)",
}


def cmd_apply(a):
    cfg, db = ctx()
    jid = _resolve(db, a.ref)
    j = db.get(jid)
    text = db.text(jid)
    bd = j.get("breakdown") or {}
    cv = cvroute.route(j, cfg.profile, cfg.cv_dir)
    cand = cfg.profile.get("candidate", {})
    flags = [name for name, pat in _FLAG_PATTERNS.items() if re.search(pat, text, re.I)]
    max_chars = int(cfg.run("apply_text_max_chars", 14000))
    lines = [
        f"APPLICATION PACK — {j['company']} — {j['title']}  ({jid})",
        *(f"⚠ {w}" for w in cfg.warnings),
        f"Label: {j.get('label')} · score {j.get('score')} · eligibility {j.get('eligible')} ({j.get('eligibility_reason')})",
        f"Posting live as of: {str(j.get('last_seen'))[:10]}{' · CLOSED' if j.get('closed_at') else ''}",
        "",
        "CV ROUTING",
        f"  {cv['name']} → {cv['file']} ({'found' if cv['exists'] else 'FILE MISSING'})\n  why: {cv['reason']}" if cv else "  no [[cv]] variants configured",
        "",
        "DETERMINISTIC GAP ANALYSIS",
        f"  experience: asks {j.get('experience_min') or '?'} yrs; profile says {cand.get('years_experience', -1) if cand.get('years_experience', -1) >= 0 else 'UNKNOWN'}",
        f"  required skills not in profile: {', '.join(bd.get('missing_required') or []) or 'none recognised'}",
        f"  matched skills: {', '.join(bd.get('matched') or []) or 'none'}",
        f"  certs mentioned but not held: {', '.join(bd.get('cert_gaps') or []) or 'none'}",
        "",
        "QUESTIONS TO ANSWER TRUTHFULLY (flag if the profile cannot support an answer)",
        *(f"  - {f}" for f in flags or ["none detected"]),
        "",
        "PROFILE FACTS (the ONLY facts that may be claimed; never invent more)",
        f"  location: {cand.get('location_city', '')}, {cand.get('location_country')} · citizenships: {', '.join(cand.get('citizenships', []))}"
        f" · work authorization: {', '.join(cand.get('work_authorization', []))} · clearance: {cand.get('has_clearance')}",
        f"  certifications: {', '.join(cand.get('certifications', [])) or 'none listed'} · profile verified: {cand.get('verified', False)}",
        "",
        "SUBMISSION: human only. Open the link, review every field, submit yourself.",
        f"  {j.get('apply_url') or j.get('url')}",
        "",
        sanitize.fence(sanitize.clean_text(text, max_chars), jid),
    ]
    pack = "\n".join(lines)
    folder = cfg.home / "applications" / f"{date.today().isoformat()}-{slug(j['company'])}-{slug(j['title'])}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "pack.md").write_text(pack, encoding="utf-8")
    st = db.state(jid)
    if not st or st["status"] not in CLOSED_STATUSES:
        db.set_state(jid, "preparing", cv_variant=cv and cv["name"])
    db.commit()
    out(pack)
    out(f"\n(saved to {folder / 'pack.md'}; write answers/cover letter next to it)")


def cmd_digest(a):
    cfg, db = ctx()
    n = a.count or cfg.run("llm_digest_count", 15)
    jobs = query_jobs(db, [_good_labels(), "(j.llm_hash IS NULL OR j.llm_hash<>j.raw_hash)"], [], n)
    db.set_last_list([j["id"] for j in jobs])
    db.commit()
    out(render.digest([(i, j, db.text(j["id"])) for i, j in enumerate(jobs, 1)]) if jobs else "Nothing new to assess.")


def cmd_assess(a):
    cfg, db = ctx()
    jid = _resolve(db, a.ref)
    j = db.get(jid)
    db.update_fields(jid, llm_label=sanitize.one_line(a.label, 40), llm_note=sanitize.one_line(a.note, 300),
                     llm_hash=j["raw_hash"])
    db.log("assess", jid, a.label)
    db.commit()
    out(f"stored assessment for {j['company']} — {j['title']} (valid until the posting changes)")


def cmd_add(a):
    cfg, db = ctx()
    info = parse_ats_url(a.url)
    http = Http(cfg.search.get("run", {}))
    raw = None
    if info and info["token"] and info["job_id"] and info["ats"] in ADAPTERS and hasattr(ADAPTERS[info["ats"]], "fetch_one"):
        board = next((b for b in cfg.boards if b["ats"] == info["ats"] and str(b["token"]).lower() == info["token"].lower()),
                     {"ats": info["ats"], "token": info["token"], "company": a.company or info["token"], "region": info["region"]})
        try:
            raw = ADAPTERS[info["ats"]].fetch_one(board, info["job_id"], http)
        except FetchError as e:
            out(f"Could not fetch from {info['ats']} API: {e}")
        if raw and not any(b["ats"] == info["ats"] and str(b["token"]).lower() == info["token"].lower() for b in cfg.boards):
            out(f"Tip: `jh sources add {info['ats']}:{info['token']} \"{raw.company}\"` to poll this board regularly.")
    if raw is None:
        if not (a.title and a.company):
            sys.exit("Not a recognised ATS URL (or fetch failed). Provide --title and --company "
                     "(and --text-file with the pasted description) to add it manually.")
        text = Path(a.text_file).read_text(encoding="utf-8", errors="replace") if a.text_file else ""
        raw = RawJob(source="manual", board=extract.company_key(a.company) or "manual",
                     native_id=re.sub(r"\W+", "", a.url)[-40:], company=a.company, title=a.title, url=a.url,
                     apply_url=a.url, locations=[a.location] if a.location else [], description=text)
    jid = Pipeline(cfg, db, http).ingest_manual(raw)
    j = db.get(jid)
    j["user_status"] = (db.state(jid) or {}).get("status")
    show_list(cfg, db, [j], [f"Added {jid}"])


def cmd_block(a):
    cfg, db = ctx()
    kind = "title" if a.title else "company"
    value = " ".join(a.value)
    if kind == "title":
        re.compile(value)  # validate
    if a.remove:
        out(f"removed {db.remove_rule(kind, value)} rule(s)")
    else:
        db.add_rule(kind, value)
        out(f"blocked {kind}: {value} (applies on next fetch/rescore)")
    db.commit()


def cmd_sources(a):
    cfg, db = ctx()
    if a.action == "add":
        if not a.spec or ":" not in a.spec:
            sys.exit("usage: jh sources add <ats>:<token> [Company Name]")
        ats, token = a.spec.split(":", 1)
        if ats not in ADAPTERS:
            sys.exit(f"unknown ats '{ats}'. Known: {', '.join(ADAPTERS)}")
        path = cfg.home / "config" / "companies.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        name = " ".join(a.name) or token
        safe = lambda s: re.sub(r'[\\"\r\n]', "", s)  # noqa: E731  (keep the TOML well-formed)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f'\n[[boards]]\nats = "{safe(ats)}"\ntoken = "{safe(token)}"\ncompany = "{safe(name)}"\n')
        out(f"added {ats}:{token} to {path}")
        return
    if a.action == "verify":
        http = Http({**cfg.search.get("run", {}), "request_delay_seconds": 0.5})
        for b in cfg.boards:
            key = f"{b['ats']}:{b['token']}"
            try:
                jobs = ADAPTERS[b["ats"]].fetch(b, http)
                db.source_ok(key, len(jobs), "")
                out(f"ok    {key:<40} {len(jobs)} postings")
            except FetchError as e:
                db.source_fail(key, str(e))
                out(f"FAIL  {key:<40} {e}")
            except Exception as e:
                db.source_fail(key, repr(e))
                out(f"FAIL  {key:<40} parse error: {e!r}")
        db.commit()
        return
    health = {s["key"]: s for s in db.sources_all()}
    for b in cfg.boards:
        key = f"{b['ats']}:{b['token']}"
        s = health.get(key, {})
        state = "never fetched" if not s else (f"ok {str(s.get('last_ok'))[:10]} ({s.get('last_count')} jobs)" if not s.get("last_error")
                                             else f"FAILING x{s.get('consecutive_failures')}: {s.get('last_error', '')[:70]}")
        out(f"{key:<40} {b.get('company', ''):<20} {state}")


def cmd_rescore(a):
    cfg, db = ctx()
    pipe = Pipeline(cfg, db)
    ids = [r[0] for r in db.conn.execute("SELECT id FROM jobs WHERE closed_at IS NULL AND category IS NOT NULL")]
    for jid in ids:
        pipe.rescore(jid)
    pipe.dedupe({r[0] for r in db.conn.execute("SELECT DISTINCT fingerprint FROM jobs WHERE closed_at IS NULL")})
    db.commit()
    out(f"re-scored {len(ids)} open jobs under current config (no network, no LLM)")


def cmd_stats(a):
    cfg, db = ctx()
    q = lambda sql: db.conn.execute(sql).fetchone()[0]  # noqa: E731
    out(f"jobs stored: {q('SELECT count(*) FROM jobs')} · open: {q('SELECT count(*) FROM jobs WHERE closed_at IS NULL')}"
        f" · open & relevant: {q('SELECT count(*) FROM jobs WHERE closed_at IS NULL AND filtered_reason IS NULL AND dup_of IS NULL')}")
    for row in db.conn.execute("SELECT label, count(*) FROM jobs WHERE closed_at IS NULL AND filtered_reason IS NULL "
                               "AND dup_of IS NULL GROUP BY label ORDER BY 2 DESC"):
        out(f"  {row[0]}: {row[1]}")
    for row in db.conn.execute("SELECT status, count(*) FROM user_state GROUP BY status"):
        out(f"  you → {row[0]}: {row[1]}")
    out("Top hard-filter reasons:")
    for row in db.conn.execute("SELECT substr(filtered_reason,1,50) r, count(*) c FROM jobs WHERE filtered_reason IS NOT NULL "
                               "GROUP BY r ORDER BY c DESC LIMIT 8"):
        out(f"  {row[1]:>5}  {row[0]}")
    last = db.conn.execute("SELECT ts, detail FROM events WHERE action='run' ORDER BY ts DESC LIMIT 1").fetchone()
    if last:
        out(f"Last run {last[0]}: {last[1]}")


def cmd_export(a):
    cfg, db = ctx()
    rows = db.conn.execute("SELECT j.id, j.company, j.title, j.apply_url, j.label, j.score, u.status, u.cv_variant, "
                           "u.applied_at, u.reason FROM user_state u JOIN jobs j ON j.id=u.job_id ORDER BY u.updated_at").fetchall()
    data = [dict(r) for r in rows]
    path = Path(a.path or cfg.home / "state" / f"export-{date.today().isoformat()}.json")
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    out(f"exported {len(data)} tracked jobs to {path}")


# ---------------- parser ----------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jh", description="Cybersecurity job hunter (deterministic pipeline).")
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("init", help="create ~/.job-hunter and a profile to edit").set_defaults(fn=cmd_init)
    for name, fn, hlp in (("find", cmd_find, "fetch all sources, then show new jobs"),
                          ("fetch", lambda a: cmd_fetch(a), "fetch + process only")):
        s = sp.add_parser(name, help=hlp)
        s.add_argument("count", nargs="?", type=int)
        s.add_argument("--source", help="only this ats / token / company")
        s.add_argument("--no-fetch", action="store_true")
        s.set_defaults(fn=fn)
    s = sp.add_parser("new", help="unseen jobs from the database (no fetch)")
    s.add_argument("count", nargs="?", type=int)
    s.set_defaults(fn=cmd_new)
    s = sp.add_parser("show", help="show best | appsec | red team | research | cloud | emea | shortlist | applied | all [N]")
    s.add_argument("words", nargs="*")
    s.set_defaults(fn=cmd_show)
    for name, fn in (("why", cmd_why), ("shortlist", cmd_shortlist), ("apply", cmd_apply), ("undo", cmd_undo)):
        s = sp.add_parser(name)
        s.add_argument("ref")
        s.set_defaults(fn=fn)
    s = sp.add_parser("reject")
    s.add_argument("ref")
    s.add_argument("reason", nargs="*")
    s.add_argument("--company", action="store_true", help="also block this company")
    s.set_defaults(fn=cmd_reject)
    s = sp.add_parser("applied")
    s.add_argument("ref")
    s.add_argument("--cv")
    s.set_defaults(fn=cmd_applied)
    s = sp.add_parser("status", help="set interviewing|offer|declined|ghosted|shortlisted|rejected|applied")
    s.add_argument("ref")
    s.add_argument("status", choices=["shortlisted", "rejected", "applied", "interviewing", "offer", "declined", "ghosted", "preparing"])
    s.add_argument("note", nargs="*")
    s.set_defaults(fn=cmd_status)
    s = sp.add_parser("digest", help="compact JSONL of top un-assessed jobs for LLM review")
    s.add_argument("count", nargs="?", type=int)
    s.set_defaults(fn=cmd_digest)
    s = sp.add_parser("assess", help="store an LLM/your verdict for a job (cached by content hash)")
    s.add_argument("ref")
    s.add_argument("--label", required=True)
    s.add_argument("--note", default="")
    s.set_defaults(fn=cmd_assess)
    s = sp.add_parser("add", help="add a job by URL (ATS URLs are fetched via API)")
    s.add_argument("url")
    s.add_argument("--title")
    s.add_argument("--company")
    s.add_argument("--location")
    s.add_argument("--text-file")
    s.set_defaults(fn=cmd_add)
    s = sp.add_parser("block", help="block a company (or --title REGEX)")
    s.add_argument("value", nargs="+")
    s.add_argument("--title", action="store_true")
    s.add_argument("--remove", action="store_true")
    s.set_defaults(fn=cmd_block)
    s = sp.add_parser("sources", help="list | verify | add <ats>:<token> [name]")
    s.add_argument("action", nargs="?", default="list", choices=["list", "verify", "add"])
    s.add_argument("spec", nargs="?")
    s.add_argument("name", nargs="*")
    s.set_defaults(fn=cmd_sources)
    sp.add_parser("rescore", help="re-score stored jobs after editing config").set_defaults(fn=cmd_rescore)
    sp.add_parser("stats").set_defaults(fn=cmd_stats)
    s = sp.add_parser("export")
    s.add_argument("path", nargs="?")
    s.set_defaults(fn=cmd_export)
    return p


def main(argv: list[str] | None = None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # "find 20" / "show red team" style is already supported; allow "new jobs" too
    if argv[:2] == ["new", "jobs"]:
        argv = ["new", *argv[2:]]
    args = build_parser().parse_args(argv)
    try:
        args.fn(args)
    except BrokenPipeError:
        pass
