"""Location parsing and home-country eligibility (default home: Armenia).

Output is a three-way verdict (yes / no / uncertain) plus a human-readable reason.
The rules are deliberately conservative about "yes": a false "yes" wastes an
application; a false "no" hides a job, so "no" requires explicit evidence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

COUNTRIES = {
    # name/alias -> canonical country name
    **{c: c for c in [
        "afghanistan", "albania", "algeria", "andorra", "angola", "argentina", "armenia", "australia", "austria",
        "azerbaijan", "bahrain", "bangladesh", "belarus", "belgium", "bolivia", "bosnia and herzegovina", "brazil",
        "bulgaria", "cambodia", "cameroon", "canada", "chile", "china", "colombia", "costa rica", "croatia", "cyprus",
        "czechia", "denmark", "dominican republic", "ecuador", "egypt", "estonia", "ethiopia", "finland", "france",
        "georgia", "germany", "ghana", "greece", "guatemala", "hungary", "iceland", "india", "indonesia", "iran",
        "iraq", "ireland", "israel", "italy", "japan", "jordan", "kazakhstan", "kenya", "kosovo", "kuwait",
        "kyrgyzstan", "latvia", "lebanon", "lithuania", "luxembourg", "malaysia", "malta", "mexico", "moldova",
        "monaco", "mongolia", "montenegro", "morocco", "nepal", "netherlands", "new zealand", "nigeria",
        "north macedonia", "norway", "oman", "pakistan", "panama", "paraguay", "peru", "philippines", "poland",
        "portugal", "qatar", "romania", "russia", "rwanda", "saudi arabia", "serbia", "singapore", "slovakia",
        "slovenia", "south africa", "south korea", "spain", "sri lanka", "sweden", "switzerland", "taiwan",
        "tajikistan", "tanzania", "thailand", "tunisia", "turkey", "turkmenistan", "uganda", "ukraine",
        "united arab emirates", "united kingdom", "united states", "uruguay", "uzbekistan", "venezuela", "vietnam",
    ]},
    "usa": "united states", "u.s.": "united states", "u.s.a.": "united states", "united states of america": "united states",
    "america": "united states", "uk": "united kingdom", "u.k.": "united kingdom", "great britain": "united kingdom",
    "england": "united kingdom", "scotland": "united kingdom", "wales": "united kingdom", "northern ireland": "united kingdom",
    "czech republic": "czechia", "the netherlands": "netherlands", "holland": "netherlands", "uae": "united arab emirates",
    "korea": "south korea", "türkiye": "turkey", "turkiye": "turkey", "deutschland": "germany", "hayastan": "armenia",
}

CITIES = {
    "yerevan": "armenia", "gyumri": "armenia", "vanadzor": "armenia",
    "san francisco": "united states", "new york": "united states", "nyc": "united states", "seattle": "united states",
    "austin": "united states", "boston": "united states", "chicago": "united states", "los angeles": "united states",
    "denver": "united states", "atlanta": "united states", "washington, dc": "united states", "washington dc": "united states",
    "arlington": "united states", "mountain view": "united states", "palo alto": "united states", "sunnyvale": "united states",
    "san jose": "united states", "san diego": "united states", "reston": "united states", "raleigh": "united states",
    "miami": "united states", "dallas": "united states", "herndon": "united states", "columbia, md": "united states",
    "fort meade": "united states", "portland": "united states", "salt lake city": "united states", "pittsburgh": "united states",
    "toronto": "canada", "vancouver": "canada", "montreal": "canada", "ottawa": "canada",
    "london": "united kingdom", "manchester": "united kingdom", "edinburgh": "united kingdom", "cheltenham": "united kingdom",
    "dublin": "ireland", "berlin": "germany", "munich": "germany", "hamburg": "germany", "frankfurt": "germany",
    "paris": "france", "amsterdam": "netherlands", "madrid": "spain", "barcelona": "spain", "lisbon": "portugal",
    "warsaw": "poland", "krakow": "poland", "kraków": "poland", "wroclaw": "poland", "prague": "czechia", "brno": "czechia",
    "bucharest": "romania", "cluj": "romania", "sofia": "bulgaria", "belgrade": "serbia", "zurich": "switzerland",
    "zürich": "switzerland", "geneva": "switzerland", "stockholm": "sweden", "copenhagen": "denmark", "oslo": "norway",
    "helsinki": "finland", "tallinn": "estonia", "riga": "latvia", "vilnius": "lithuania", "vienna": "austria",
    "brussels": "belgium", "milan": "italy", "rome": "italy", "athens": "greece", "istanbul": "turkey",
    "tel aviv": "israel", "herzliya": "israel", "haifa": "israel", "jerusalem": "israel", "dubai": "united arab emirates",
    "abu dhabi": "united arab emirates", "riyadh": "saudi arabia", "doha": "qatar", "tbilisi": "georgia", "baku": "azerbaijan",
    "bangalore": "india", "bengaluru": "india", "hyderabad": "india", "pune": "india", "chennai": "india", "gurgaon": "india",
    "singapore": "singapore", "tokyo": "japan", "sydney": "australia", "melbourne": "australia", "canberra": "australia",
    "auckland": "new zealand", "sao paulo": "brazil", "são paulo": "brazil", "mexico city": "mexico", "buenos aires": "argentina",
    "kyiv": "ukraine", "kiev": "ukraine", "lviv": "ukraine", "limassol": "cyprus", "nicosia": "cyprus", "belfast": "united kingdom",
}

US_STATE_CODES = set(
    "al ak az ar ca co ct de fl ga hi id il in ia ks ky la me md ma mi mn ms mo mt ne nv nh nj nm ny nc nd oh ok or pa "
    "ri sc sd tn tx ut vt va wa wv wi wy dc".split()
)
US_STATES = [
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware", "florida",
    "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine", "maryland",
    "massachusetts", "michigan", "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota", "tennessee", "texas", "utah", "vermont",
    "virginia", "west virginia", "wisconsin", "wyoming",
]
CODES = {"us": "united states", "usa": "united states", "uk": "united kingdom", "gb": "united kingdom",
         "fr": "france", "nl": "netherlands", "es": "spain", "pt": "portugal", "pl": "poland", "ie": "ireland",
         "au": "australia", "ch": "switzerland", "ro": "romania", "se": "sweden", "sg": "singapore", "ua": "ukraine"}
# Deliberately absent: codes that collide with US state codes (DE, IN, IL, CA, GA, AM is not a state but
# "AM" appears in times like "9 AM") — those are resolved via the ", ST" pattern instead.

# Regions -> does it plausibly include the home country? (True = plausible, False = excludes)
REGIONS = {
    "emea": True, "europe": True, "eastern europe": True, "cis": True, "caucasus": True, "middle east": True,
    "asia": True, "west asia": True, "cee": True, "central and eastern europe": True, "mena": True,
    "european union": False, "eu": False, "eea": False, "schengen": False, "western europe": False,
    "north america": False, "americas": False, "latam": False, "latin america": False, "south america": False,
    "apac": False, "asia pacific": False, "anz": False, "dach": False, "nordics": False, "benelux": False,
    "uk&i": False, "ukie": False, "africa": False,
}
WORLDWIDE = ["worldwide", "anywhere", "global", "globally", "work from anywhere", "any location", "all locations", "international"]

_REMOTE_WORD = re.compile(r"\b(remote|anywhere|work from home|wfh|distributed|telecommut\w*)\b", re.I)
_HYBRID_WORD = re.compile(r"\bhybrid\b", re.I)


def _wb(term: str) -> str:
    return r"(?<![\w])" + re.escape(term) + r"(?![\w])"


_COUNTRY_RE = re.compile("|".join(_wb(k) for k in sorted(COUNTRIES, key=len, reverse=True)), re.I)
_CITY_RE = re.compile("|".join(_wb(k) for k in sorted(CITIES, key=len, reverse=True)), re.I)
_STATE_RE = re.compile("|".join(_wb(s) for s in US_STATES), re.I)
_REGION_RE = re.compile("|".join(_wb(k) for k in sorted(REGIONS, key=len, reverse=True)), re.I)
_WORLD_RE = re.compile("|".join(_wb(k) for k in WORLDWIDE), re.I)
_STATE_CODE_RE = re.compile(r",\s*([A-Z]{2})\b")


@dataclass
class Place:
    raw: str
    remote: bool = False
    hybrid: bool = False
    worldwide: bool = False
    countries: set = field(default_factory=set)
    regions: set = field(default_factory=set)

    @property
    def empty(self) -> bool:
        return not (self.worldwide or self.countries or self.regions)


def parse_place(raw: str) -> Place:
    s = raw or ""
    p = Place(raw=s, remote=bool(_REMOTE_WORD.search(s)), hybrid=bool(_HYBRID_WORD.search(s)))
    p.worldwide = bool(_WORLD_RE.search(s))
    for m in _CITY_RE.finditer(s):
        p.countries.add(CITIES[m.group(0).lower()])
    for m in _COUNTRY_RE.finditer(s):
        p.countries.add(COUNTRIES[m.group(0).lower()])
    for m in _REGION_RE.finditer(s):
        term = m.group(0).lower()
        # "Georgia" is ambiguous (US state vs country) — prefer the US when a US signal is present.
        p.regions.add(term)
    if _STATE_RE.search(s):
        if "georgia" in p.countries and not re.search(r"tbilisi|batumi", s, re.I):
            p.countries.discard("georgia")
        p.countries.add("united states")
    for m in _STATE_CODE_RE.finditer(s):
        if m.group(1).lower() in US_STATE_CODES:
            p.countries.add("united states")
    for tok in re.split(r"[\s,;:/|()\-–—]+", s):
        t = tok.strip(".").lower()
        if t in CODES and tok.isupper():
            p.countries.add(CODES[t])
    return p


def split_locations(values: list[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        for piece in re.split(r"\s*(?:;|\||\s/\s|\bor\b)\s*", v or ""):
            piece = piece.strip(" ,")
            if piece and piece.lower() not in {x.lower() for x in out}:
                out.append(piece)
    return out


# ---- description text rules ----
_RESTRICT_RE = re.compile(
    r"(?:must|required to|need to|needs to|should|will need to|have to)\s+(?:currently\s+)?(?:be\s+)?"
    r"(?:based|located|reside|residing|live|living|resident|a resident)\s+(?:in|within|of)\s+(?:the\s+)?"
    r"(?P<where>[^.;\n]{2,70})"
    r"|(?:only|exclusively)\s+(?:open|available|considering)\s+(?:to\s+)?(?:candidates|applicants|residents|people)?\s*"
    r"(?:who are\s+)?(?:based\s+|located\s+|residing\s+|living\s+)?in\s+(?:the\s+)?(?P<where2>[^.;\n]{2,70})"
    r"|(?:candidates|applicants)\s+(?:must be|need to be)\s+(?:based|located)\s+in\s+(?:the\s+)?(?P<where3>[^.;\n]{2,70})",
    re.I,
)
_AUTH_RE = re.compile(
    r"(?:legally\s+)?(?:authori[sz]ed|eligible|permitted|right)\s+to\s+work\s+in\s+(?:the\s+)?(?P<where>[^.;\n]{2,60})",
    re.I,
)
_CITIZEN_RE = re.compile(
    r"\b(?P<nat>u\.?s\.?|united states|american|uk|british|canadian|australian|israeli|german|french|eu|european union|nato)"
    r"\s+(?:citizen(?:ship)?|national(?:ity)?|person)s?\b"
    r"|citizenship\s+(?:is\s+)?required|must\s+(?:be|hold)\s+(?:a\s+)?(?:\w+\s+){0,2}citizen",
    re.I,
)
_CLEARANCE_RE = re.compile(
    r"\b(ts/sci|top secret|secret clearance|security clearance|sc clearance|dv clearance|sc/dv|nv1|nv2|agsva|"
    r"baseline clearance|active clearance|clearance is required|public trust|polygraph|bpss)\b",
    re.I,
)
_NEGATION_RE = re.compile(r"\b(no|not|without|n't|isn't|nor)\b[^.\n]{0,40}$", re.I)
_SPONSOR_RE = re.compile(r"(unable|not able|cannot|can't|do not|don't|will not|won't)\s+(?:to\s+)?(?:provide\s+|offer\s+)?(?:visa\s+)?sponsor", re.I)
_WORLD_TEXT_RE = re.compile(
    r"work from anywhere|anywhere in the world|remote[- ](?:first\s+)?(?:worldwide|globally|anywhere)|"
    r"hire (?:globally|worldwide|in any country|anywhere)|fully remote,? (?:worldwide|globally|anywhere)|"
    r"(?:open to|accept) (?:candidates|applicants) (?:from )?(?:anywhere|worldwide|all countries)",
    re.I,
)
_FULLY_REMOTE_RE = re.compile(r"\b(fully remote|100% remote|remote[- ]first|remote[- ]friendly|remote position|remote role|work remotely)\b", re.I)
_HYBRID_TEXT_RE = re.compile(r"\bhybrid\s+(?:role|position|work\w*|model|schedule|arrangement|setup|policy)\b", re.I)
_TZ_RANGE_RE = re.compile(r"(?:utc|gmt)\s*([+\-−]\s*\d{1,2})\s*(?:to|-|–|and)\s*(?:utc|gmt)?\s*([+\-−]\s*\d{1,2})", re.I)
_US_TZ_RE = re.compile(r"\b(pst|pdt|est|edt|cst|mst|pacific time|eastern time|central time|us time ?zones?|u\.s\. business hours)\b", re.I)


def _negated(text: str, start: int) -> bool:
    return bool(_NEGATION_RE.search(text[max(0, start - 50): start]))


@dataclass
class Eligibility:
    status: str                 # yes | no | uncertain
    reason: str
    remote: str                 # remote | hybrid | onsite | unknown
    regions: list = field(default_factory=list)
    countries: list = field(default_factory=list)
    clearance: str | None = None
    visa: str | None = None
    concerns: list = field(default_factory=list)
    evidence: list = field(default_factory=list)


def _home_terms(home: str) -> set[str]:
    home = home.lower()
    terms = {home} | {k for k, v in COUNTRIES.items() if v == home} | {k for k, v in CITIES.items() if v == home}
    return terms


def _classify_where(where: str, home: str) -> str:
    """Return 'home' | 'world' | 'region' | 'excluded' | 'unknown' for a restriction clause."""
    pl = parse_place(where)
    if home in pl.countries:
        return "home"
    if pl.worldwide:
        return "world"
    if any(REGIONS.get(r) for r in pl.regions):
        return "region"
    if pl.countries or pl.regions:
        return "excluded"
    return "unknown"


def assess(locations: list[str], text: str, *, remote_hint: str | None = None, profile: dict | None = None,
           loc_cfg: dict | None = None) -> Eligibility:
    profile = profile or {}
    loc_cfg = loc_cfg or {}
    cand = profile.get("candidate", {})
    home = str(cand.get("location_country", "Armenia")).lower()
    auth = {a.lower() for a in cand.get("work_authorization", [home])}
    citizenships = {c.lower() for c in cand.get("citizenships", [home])}
    has_clearance = bool(cand.get("has_clearance", False))
    region_status = loc_cfg.get("region_remote_status", "uncertain")
    unspecified_status = loc_cfg.get("unspecified_remote_status", "uncertain")
    home_offset = cand.get("timezone_utc_offset")
    text = text or ""

    places = [parse_place(x) for x in split_locations(locations)]
    elig = Eligibility(status="uncertain", reason="", remote="unknown")

    # --- remote mode ---
    if remote_hint in ("remote", "hybrid", "onsite"):
        elig.remote = remote_hint
    elif any(p.remote for p in places):
        elig.remote = "remote"
    elif any(p.hybrid for p in places) or _HYBRID_TEXT_RE.search(text[:4000]):
        elig.remote = "hybrid"
    elif _FULLY_REMOTE_RE.search(text) or _WORLD_TEXT_RE.search(text):
        elig.remote = "remote"
    elif places and any(not p.empty for p in places):
        elig.remote = "onsite"

    remote_places = [p for p in places if p.remote] or (places if elig.remote == "remote" else [])
    all_countries = set().union(*(p.countries for p in places)) if places else set()
    all_regions = set().union(*(p.regions for p in places)) if places else set()
    elig.countries = sorted(all_countries)
    elig.regions = sorted(all_regions | ({"worldwide"} if any(p.worldwide for p in places) else set()))

    # --- hard blockers in text ---
    blockers: list[str] = []
    for m in _CLEARANCE_RE.finditer(text):
        if not _negated(text, m.start()):
            elig.clearance = m.group(0)
            if not has_clearance:
                blockers.append(f"requires clearance ({m.group(0)})")
            break
    for m in _CITIZEN_RE.finditer(text):
        if _negated(text, m.start()):
            continue
        nat = (m.group("nat") or "").lower()
        if nat and any(nat.startswith(c[:4]) for c in citizenships):
            continue
        blockers.append(f"citizenship requirement (\"{m.group(0)}\")")
        break
    region_restriction = None
    for rx, groups in ((_RESTRICT_RE, ("where", "where2", "where3")), (_AUTH_RE, ("where",))):
        for m in rx.finditer(text):
            where = next((m.group(g) for g in groups if m.groupdict().get(g)), "")
            if _negated(text, m.start()):
                continue
            kind = _classify_where(where, home)
            if kind == "excluded":
                if any(a in where.lower() for a in auth):
                    continue
                blockers.append(f"restricted to {where.strip()[:60]}")
            elif kind == "region" and region_restriction is None:
                region_restriction = where.strip()[:60]
            elig.evidence.append(m.group(0)[:140])
            if blockers:
                break
    if _SPONSOR_RE.search(text):
        elig.visa = "no visa sponsorship"

    # --- timezone hints ---
    for m in _TZ_RANGE_RE.finditer(text):
        try:
            lo, hi = sorted(int(x.replace(" ", "").replace("−", "-")) for x in m.groups())
        except ValueError:
            continue
        if home_offset is not None and not (lo <= home_offset <= hi):
            elig.concerns.append(f"timezone window {m.group(0)} excludes UTC{home_offset:+d}")
        break
    if _US_TZ_RE.search(text):
        elig.concerns.append("expects US time-zone overlap")

    home_terms = _home_terms(home)
    home_hit = next((p for p in places if home in p.countries), None)
    text_home = re.search("|".join(_wb(t) for t in home_terms), text, re.I)

    def done(status: str, reason: str) -> Eligibility:
        elig.status, elig.reason = status, reason
        return elig

    if blockers:
        return done("no", blockers[0])
    if home_hit:
        return done("yes", f"location lists {home.title()} ({home_hit.raw})")
    if elig.remote in ("onsite", "hybrid"):
        where = ", ".join(p.raw for p in places[:3]) or "unspecified location"
        if text_home:
            return done("uncertain", f"{elig.remote} ({where}) but posting mentions {home.title()}")
        return done("no", f"{elig.remote} in {where}")
    if elig.remote == "unknown" and not places:
        return done("uncertain", "no location data")
    if any(p.worldwide for p in remote_places) or (_WORLD_TEXT_RE.search(text) and not any(p.countries for p in remote_places)):
        if region_restriction:
            return done(region_status, f"worldwide listing but text says {region_restriction}")
        return done("yes", "remote, worldwide/anywhere")
    if text_home and elig.remote == "remote":
        elig.evidence.append(text[max(0, text_home.start() - 60): text_home.end() + 60])
        return done("yes", f"remote and posting mentions {home.title()}")

    rc = set().union(*(p.countries for p in remote_places)) if remote_places else set()
    rr = set().union(*(p.regions for p in remote_places)) if remote_places else set()
    plausible_regions = sorted(r for r in rr if REGIONS.get(r))
    if plausible_regions:
        note = f"remote {'/'.join(r.upper() if len(r) <= 4 else r.title() for r in plausible_regions)}"
        return done(region_status, f"{note}; confirm {home.title()} is a hiring country")
    if region_restriction:
        return done(region_status, f"text: based in {region_restriction}")
    if rc or rr:
        where = ", ".join(sorted(rc | rr))[:80]
        return done("no", f"remote restricted to {where}")
    if elig.remote == "remote":
        return done(unspecified_status, "remote, country not specified (often means HQ country)")
    return done("uncertain", "location unclear")
