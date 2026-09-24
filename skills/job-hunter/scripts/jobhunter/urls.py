"""Canonical URLs (for dedup and stable links) and ATS URL recognition."""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {
    "gh_src", "source", "src", "ref", "referrer", "referer", "lever-source", "lever-origin",
    "lever-via", "trk", "trackingid", "refid", "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid",
    "_hsenc", "_hsmi", "iis", "iisn", "utm", "ashby_jid_src",
    "ebp", "pagenum", "trkinfo", "lipi", "eid", "sourceid", "rx_source",
}


def strip_tracking(url: str | None) -> str | None:
    """Remove tracking params only; keep path (e.g. /apply) so the link still works."""
    if not url:
        return None
    p = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False)
             if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(query), ""))


def canonical_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/{2,}", "/", p.path or "/")
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False)
             if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS]

    if host in ("boards.greenhouse.io", "job-boards.greenhouse.io"):
        host = "job-boards.greenhouse.io"
    elif host in ("boards.eu.greenhouse.io", "job-boards.eu.greenhouse.io"):
        host = "job-boards.eu.greenhouse.io"
    if host.endswith("lever.co"):
        path = re.sub(r"/apply/?$", "", path)
    if host == "jobs.ashbyhq.com":
        path = re.sub(r"/application/?$", "", path)
    if host.endswith("linkedin.com"):
        jid = dict(query).get("currentJobId")
        m = re.search(r"/jobs/view/(?:[^/]*-)?(\d+)", path)
        if jid or m:
            return f"https://linkedin.com/jobs/view/{jid or m.group(1)}"
    if host == "apply.workable.com":
        path = re.sub(r"/apply/?$", "", path)

    path = path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, urlencode(sorted(query)), ""))


# (ats, token, job_id, region) from a public job URL; job_id may be None for board URLs.
_PATTERNS = [
    ("greenhouse", re.compile(r"^(?:job-)?boards(?:\.eu)?\.greenhouse\.io$"), re.compile(r"^/(?:embed/job_app\?for=)?([\w-]+)(?:/jobs/(\d+))?")),
    ("lever", re.compile(r"^jobs(?:\.eu)?\.lever\.co$"), re.compile(r"^/([\w.-]+)(?:/([0-9a-f-]{36}))?")),
    ("ashby", re.compile(r"^jobs\.ashbyhq\.com$"), re.compile(r"^/([^/]+)(?:/([0-9a-f-]{36}))?")),
    ("workable", re.compile(r"^apply\.workable\.com$"), re.compile(r"^/([\w-]+)(?:/j/([0-9A-Z]+))?")),
    ("smartrecruiters", re.compile(r"^(?:jobs|careers)\.smartrecruiters\.com$"), re.compile(r"^/([\w-]+)(?:/(\d+))?")),
]


def parse_ats_url(url: str) -> dict | None:
    p = urlsplit(url if "://" in url else "https://" + url)
    host = (p.hostname or "").lower()
    for ats, host_re, path_re in _PATTERNS:
        if host_re.match(host):
            m = path_re.match(p.path)
            if not m:
                return None
            region = "eu" if ".eu." in host else None
            return {"ats": ats, "token": m.group(1), "job_id": m.group(2), "region": region}
    # Company career page embedding Greenhouse: ?gh_jid=123 (board token unknown).
    q = dict(parse_qsl(p.query))
    if "gh_jid" in q:
        return {"ats": "greenhouse", "token": None, "job_id": q["gh_jid"], "region": None}
    return None
