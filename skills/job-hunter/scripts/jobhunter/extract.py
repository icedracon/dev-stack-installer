"""Deterministic extraction from title + description text. No LLM involved."""
from __future__ import annotations

import re
from functools import lru_cache

# ---- title ----

_SENIORITY = [
    ("executive", r"\b(chief|ciso|cso|vp|vice president|head of|director)\b"),
    ("manager", r"\bmanager\b"),
    ("principal", r"\b(principal|distinguished|fellow)\b"),
    ("staff", r"\bstaff\b|\b(iv|v)\s*$"),
    ("lead", r"\b(lead|tech lead)\b"),
    ("senior", r"\b(senior|sr\.?|snr)\b|\biii\b"),
    ("junior", r"\b(junior|jr\.?|entry[- ]level|associate|graduate|new grad)\b|\bi\s*$"),
    ("mid", r"\bii\b|\bmid[- ]?level\b"),
]


def seniority(title: str) -> str:
    for level, pat in _SENIORITY:
        if re.search(pat, title or "", re.I):
            return level
    return "unspecified"


def title_key(title: str) -> str:
    """Normalised title for dedup: drops location suffixes and punctuation, keeps seniority."""
    t = (title or "").lower()
    t = re.sub(r"\s*[\(\[][^)\]]*[\)\]]", " ", t)                    # (Remote, EMEA)
    t = re.sub(r"\s+[-–—|@]\s+(remote|hybrid|onsite|[a-z .]+,\s*[a-z .]+)$", " ", t)
    t = re.sub(r"\bsr\.?\b", "senior", t)
    t = re.sub(r"\bjr\.?\b", "junior", t)
    t = t.replace("&", " and ")
    t = re.sub(r"[^a-z0-9+#]+", " ", t)
    return " ".join(t.split())


def company_key(name: str) -> str:
    n = (name or "").lower()
    n = re.sub(r"\b(inc|llc|ltd|limited|gmbh|corp|corporation|co|plc|s\.?a|b\.?v|ag|oy|ab|technologies|labs?|hq)\b\.?", " ", n)
    return re.sub(r"[^a-z0-9]+", "", n)


class TitleClassifier:
    def __init__(self, search_cfg: dict, extra_excludes: list[str] | None = None):
        self.categories = [
            (c["key"], c.get("tier", "secondary"), [re.compile(p, re.I) for p in c.get("title_patterns", [])])
            for c in search_cfg.get("categories", [])
        ]
        excl = list(search_cfg.get("filters", {}).get("exclude_title_patterns", [])) + list(extra_excludes or [])
        self.exclude = [re.compile(p, re.I) for p in excl]

    def excluded_by(self, title: str) -> str | None:
        for rx in self.exclude:
            if rx.search(title or ""):
                return rx.pattern
        return None

    def category(self, title: str) -> tuple[str | None, str | None]:
        for key, tier, pats in self.categories:
            if any(p.search(title or "") for p in pats):
                return key, tier
        return None, None


# ---- description sections ----

_PREF_HEAD = re.compile(
    r"(nice[- ]to[- ]have|preferred|bonus|plus|desired|good to have|would be (great|nice)|extra credit|"
    r"not required|ideally|we'?d love|it'?s a plus|pluses)", re.I)
_REQ_HEAD = re.compile(
    r"(requirements|qualifications|what you('ll)? (need|bring)|must[- ]have|you have|about you|you should have|"
    r"we'?re looking for|minimum|required|who you are|what we look for|skills)", re.I)


def split_sections(text: str) -> tuple[str, str]:
    """Split description into (required-ish, preferred) text by heading heuristics."""
    req, pref, mode = [], [], "req"
    for line in (text or "").split("\n"):
        stripped = line.strip()
        is_heading = 0 < len(stripped) <= 80 and not stripped.startswith("- ") and (
            stripped.endswith(":") or len(stripped.split()) <= 6)
        if is_heading and _PREF_HEAD.search(stripped):
            mode = "pref"
        elif is_heading and _REQ_HEAD.search(stripped):
            mode = "req"
        elif stripped.startswith("- ") and _PREF_HEAD.search(stripped[:40]):
            pref.append(line)  # single inline "Bonus: ..." bullet
            continue
        elif mode == "pref" and stripped and not stripped.startswith("- ") and len(stripped.split()) > 8:
            mode = "req"  # a prose paragraph ends a bullet-list "nice to have" section
        (pref if mode == "pref" else req).append(line)
    return "\n".join(req), "\n".join(pref)


# ---- years of experience ----

_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "twelve": 12, "fifteen": 15}
_YEARS_RE = re.compile(
    r"(?P<a>\d{1,2}|" + "|".join(_WORDNUM) + r")\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*(?P<b>\d{1,2})\s*)?"
    r"(?:\+\s*)?(?:years?|yrs?)(?:'|’)?\b(?P<tail>[^.\n]{0,80})",
    re.I,
)
_EXP_CONTEXT = re.compile(r"experience|background|working|professional|industry|hands[- ]on|track record|in (a|an|the)? ?\w+ (role|position)", re.I)


def years_required(required_text: str) -> int | None:
    """Largest plausible 'N+ years' requirement in the required section.

    Uses the max because postings typically state total experience first and
    sub-requirements second ("7+ years ... including 3+ years in security")."""
    found = []
    for m in _YEARS_RE.finditer(required_text or ""):
        a = m.group("a").lower()
        n = int(a) if a.isdigit() else _WORDNUM.get(a)
        if n is None or not (1 <= n <= 20):
            continue
        # only look inside the current sentence/bullet; neighbouring sentences cause false hits
        sent_start = max(required_text.rfind(".", 0, m.start()), required_text.rfind("\n", 0, m.start())) + 1
        window = required_text[max(sent_start, m.start() - 80): m.end()]
        if not _EXP_CONTEXT.search(window):
            continue
        if re.search(r"\b(founded|old|history|anniversary|we have been|in business|around for)\b", window, re.I):
            continue
        found.append(n)
    return max(found) if found else None


# ---- skills ----

@lru_cache(maxsize=8)
def _compile_aliases(items: tuple) -> list[tuple[str, re.Pattern]]:
    out = []
    for key, aliases in items:
        pat = "|".join(f"(?:{a})" for a in aliases)
        out.append((key, re.compile(r"(?<![\w])(?:" + pat + r")(?![\w])", re.I)))
    return out


def find_skills(text: str, aliases: dict) -> list[str]:
    compiled = _compile_aliases(tuple((k, tuple(v)) for k, v in sorted(aliases.items())))
    return [key for key, rx in compiled if rx.search(text or "")]


def extract_skills(text: str, skills_cfg: dict) -> dict:
    req_text, pref_text = split_sections(text)
    aliases = skills_cfg.get("aliases", {})
    certs = skills_cfg.get("certs", {})
    req = find_skills(req_text, aliases)
    pref = [s for s in find_skills(pref_text, aliases) if s not in req]
    return {
        "required": req,
        "preferred": pref,
        "certs": find_skills(text, certs),
        "years": years_required(req_text) or years_required(text),
    }


# ---- salary ----

_CUR = {"$": "USD", "usd": "USD", "€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP", "chf": "CHF", "cad": "CAD",
        "aud": "AUD", "pln": "PLN", "amd": "AMD", "֏": "AMD", "ils": "ILS", "sek": "SEK"}
_SAL_RE = re.compile(
    r"(?P<c1>[$€£֏]|usd|eur|gbp|chf|cad|aud|pln|amd|ils|sek)\s?(?P<a>\d[\d,.\s]*\d|\d)\s?(?P<ka>k)?"
    r"\s*(?:-|–|to)\s*(?P<c2>[$€£֏]|usd|eur|gbp|chf|cad|aud|pln|amd|ils|sek)?\s?(?P<b>\d[\d,.\s]*\d|\d)\s?(?P<kb>k)?"
    r"(?P<tail>[^\n]{0,30})",
    re.I,
)


def _num(s: str, k: bool) -> float | None:
    s = re.sub(r"[\s,]", "", s)
    if s.count(".") > 1:
        s = s.replace(".", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return v * 1000 if k else v


def parse_salary(text: str) -> dict | None:
    for m in _SAL_RE.finditer(text or ""):
        cur = _CUR.get(m.group("c1").lower())
        lo, hi = _num(m.group("a"), bool(m.group("ka") or m.group("kb"))), _num(m.group("b"), bool(m.group("kb")))
        if not lo or not hi:
            continue
        tail = m.group("tail").lower()
        period = "hour" if re.search(r"hour|/h|hr\b", tail) else "month" if re.search(r"month|/mo", tail) else "year"
        if period == "year" and hi < 1000:  # "$60-80" with no k is almost certainly hourly or junk
            continue
        return {"min": lo, "max": hi, "currency": cur, "period": period, "text": m.group(0)[:60].strip()}
    return None


def annual_usd(sal: dict | None, fx: dict) -> float | None:
    if not sal or not sal.get("max") or not sal.get("currency"):
        return None
    rate = fx.get(sal["currency"])
    if rate is None:
        return None
    mult = {"year": 1, "month": 12, "hour": 2000}.get(sal.get("period") or "year", 1)
    return float(sal["max"]) * mult * rate
