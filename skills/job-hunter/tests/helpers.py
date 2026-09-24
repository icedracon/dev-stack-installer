"""Shared test helpers: offline fake HTTP backed by fixture files, temp homes."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from jobhunter.http import FetchError  # noqa: E402

FIX = HERE / "fixtures"


def fixture(name: str):
    return json.loads((FIX / name).read_text())


ROUTES = {
    "https://boards-api.greenhouse.io/v1/boards/acme/jobs": "greenhouse_acme.json",
    "https://api.lever.co/v0/postings/beta": "lever_beta.json",
    "https://api.ashbyhq.com/posting-api/job-board/gamma": "ashby_gamma.json",
    "https://apply.workable.com/api/v1/widget/accounts/delta": "workable_delta.json",
    "https://api.smartrecruiters.com/v1/companies/epsilon/postings": "smartrecruiters_epsilon.json",
    "https://api.smartrecruiters.com/v1/companies/epsilon/postings/744000001": "smartrecruiters_epsilon_detail.json",
    "https://remotive.com/api/remote-jobs": "remotive_software-dev.json",
}

BOARDS_TOML = """
[settings]
include_bundled = false

[[boards]]
ats = "greenhouse"
token = "acme"
company = "Acme"

[[boards]]
ats = "lever"
token = "beta"
company = "Beta"

[[boards]]
ats = "ashby"
token = "gamma"
company = "Gamma"

[[boards]]
ats = "workable"
token = "delta"
company = "Delta Security"

[[boards]]
ats = "smartrecruiters"
token = "epsilon"
company = "Epsilon"

[[boards]]
ats = "remotive"
token = "software-dev"
company = "(Remotive)"
"""

PROFILE_TOML = """
[candidate]
verified = true
location_country = "Armenia"
timezone_utc_offset = 4
years_experience = 3
work_authorization = ["Armenia"]
citizenships = ["Armenia"]
has_clearance = false
min_salary_usd_year = 0
certifications = []

[targets]
primary = ["redteam", "offensive", "pentest", "research", "appsec", "cloudsec"]
secondary = ["detection", "tooling", "infrasec", "security_engineer"]

[companies]
preferred = []
blocked = []

[skills]
active_directory = 3
kerberos = 3
adcs = 2
python = 3
rust = 2
c2 = 2
red_team_ops = 3
pentest = 3
web_appsec = 2
edr = 2
siem = 2

[[cv]]
name = "redteam"
file = "redteam.pdf"
categories = ["redteam", "offensive", "pentest"]
emphasis = ["active_directory", "kerberos", "c2"]

[[cv]]
name = "general"
file = "general.pdf"
categories = []
emphasis = ["python"]
default = true
"""

SEARCH_TOML = """
[run]
max_age_days = 3650
request_delay_seconds = 0
"""


class FakeHttp:
    def __init__(self, routes: dict | None = None, fail: set[str] | None = None, overrides: dict | None = None):
        self.routes = dict(ROUTES if routes is None else routes)
        self.fail = fail or set()
        self.overrides = overrides or {}
        self.requests = 0
        self.calls: list[str] = []

    def get_json(self, url, params=None, retries=2):
        self.requests += 1
        self.calls.append(url)
        if url in self.fail:
            raise FetchError(f"HTTP 503 for {url}", 503)
        if url in self.overrides:
            return json.loads(json.dumps(self.overrides[url]))
        if url not in self.routes:
            raise FetchError(f"HTTP 404 for {url}", 404)
        return fixture(self.routes[url])


def make_home(profile: str = PROFILE_TOML, boards: str = BOARDS_TOML, search: str = SEARCH_TOML) -> Path:
    home = Path(tempfile.mkdtemp(prefix="jh-test-"))
    (home / "config").mkdir()
    (home / "config" / "profile.toml").write_text(profile)
    (home / "config" / "companies.toml").write_text(boards)
    (home / "config" / "search.toml").write_text(search)
    return home


class EnvHome:
    """Context manager that points JOB_HUNTER_HOME at a temp home."""

    def __init__(self, home: Path):
        self.home = home
        self.prev = None

    def __enter__(self):
        self.prev = os.environ.get("JOB_HUNTER_HOME")
        os.environ["JOB_HUNTER_HOME"] = str(self.home)
        return self.home

    def __exit__(self, *exc):
        if self.prev is None:
            os.environ.pop("JOB_HUNTER_HOME", None)
        else:
            os.environ["JOB_HUNTER_HOME"] = self.prev
