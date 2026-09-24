"""Layered configuration: bundled defaults + user overrides in JOB_HUNTER_HOME."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

SKILL_DIR = Path(__file__).resolve().parents[2]
BUNDLED_CONFIG = SKILL_DIR / "config"


def home_dir() -> Path:
    return Path(os.environ.get("JOB_HUNTER_HOME", "~/.job-hunter")).expanduser()


def _load(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = val
    return out


@dataclass
class Config:
    home: Path
    search: dict
    profile: dict
    skills: dict
    boards: list[dict]
    profile_is_example: bool
    warnings: list[str] = field(default_factory=list)

    @property
    def db_path(self) -> Path:
        return self.home / "state" / "jobs.db"

    @property
    def cv_dir(self) -> Path:
        return self.home / "cv"

    def scoring_hash(self) -> str:
        """Changes whenever anything that affects filtering/scoring changes."""
        blob = json.dumps([self.search, self.profile, self.skills], sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def run(self, key: str, default=None):
        return self.search.get("run", {}).get(key, default)


def _merge_boards(bundled: list[dict], user: list[dict]) -> list[dict]:
    by_key: dict[tuple, dict] = {}
    for b in bundled + user:
        key = (b.get("ats", "").lower(), str(b.get("token", "")).lower())
        by_key[key] = deep_merge(by_key.get(key, {}), b)
    return [b for b in by_key.values() if b.get("enabled", True)]


def load(home: Path | None = None) -> Config:
    home = home or home_dir()
    user_cfg = home / "config"
    search = deep_merge(_load(BUNDLED_CONFIG / "search.toml"), _load(user_cfg / "search.toml"))
    skills = deep_merge(_load(BUNDLED_CONFIG / "skills.toml"), _load(user_cfg / "skills.toml"))
    user_companies = _load(user_cfg / "companies.toml")
    include_bundled = user_companies.get("settings", {}).get("include_bundled", True)
    boards = _merge_boards(
        _load(BUNDLED_CONFIG / "companies.toml").get("boards", []) if include_bundled else [],
        user_companies.get("boards", []),
    )
    warnings = []
    profile_path = user_cfg / "profile.toml"
    is_example = not profile_path.is_file()
    profile = _load(BUNDLED_CONFIG / "profile.example.toml" if is_example else profile_path)
    if is_example:
        warnings.append("Using the example profile. Run `jh init` and edit ~/.job-hunter/config/profile.toml.")
    elif not profile.get("candidate", {}).get("verified", False):
        warnings.append("Profile not verified: skill levels/years are placeholders. Edit profile.toml, set verified = true.")
    return Config(home, search, profile, skills, boards, is_example, warnings)


def init_home(home: Path | None = None) -> list[str]:
    home = home or home_dir()
    created = []
    for sub in ("config", "state", "cv", "applications"):
        p = home / sub
        if not p.exists():
            p.mkdir(parents=True)
            created.append(str(p))
    target = home / "config" / "profile.toml"
    if not target.exists():
        shutil.copy(BUNDLED_CONFIG / "profile.example.toml", target)
        created.append(str(target))
    try:
        os.chmod(home, 0o700)
    except OSError:
        pass
    return created
