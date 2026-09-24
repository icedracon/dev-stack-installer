"""Explainable additive scoring. Every point is attributed to a named component with a
reason, stored in `breakdown`, and printed by `why <n>`. The total is a ranking aid,
not a probability of getting hired."""
from __future__ import annotations

from datetime import date


LEVEL_CAP = 3  # "strong" counts as full coverage; expert gives no extra credit


def tier_for(category: str | None, profile: dict) -> str | None:
    targets = profile.get("targets", {})
    if category in targets.get("primary", []):
        return "primary"
    if category in targets.get("secondary", []):
        return "secondary"
    return None


def skill_overlap(required: list[str], preferred: list[str], profile_skills: dict) -> tuple[float | None, list, list]:
    weights = [(s, 1.0) for s in required] + [(s, 0.5) for s in preferred]
    if not weights:
        return None, [], []
    have = lambda s: min(int(profile_skills.get(s, 0) or 0), LEVEL_CAP) / LEVEL_CAP  # noqa: E731
    total = sum(w for _, w in weights)
    got = sum(w * have(s) for s, w in weights)
    matched = sorted({s for s, _ in weights if have(s) > 0}, key=lambda s: -int(profile_skills.get(s, 0)))
    missing = [s for s in required if have(s) == 0]
    return got / total, matched, missing


def years_gap(job_years: int | None, profile: dict) -> int | None:
    mine = profile.get("candidate", {}).get("years_experience", -1)
    if job_years is None or mine is None or mine < 0:
        return None
    return job_years - int(mine)


def score(rec: dict, profile: dict, search: dict, today: date | None = None) -> dict:
    w = search.get("scoring", {})
    cand = profile.get("candidate", {})
    today = today or date.today()
    parts: list[tuple[str, float, str]] = []

    tier = rec.get("tier")
    if tier == "primary":
        parts.append(("role", w.get("role_primary", 25), f"primary target ({rec.get('category')})"))
    elif tier == "secondary":
        parts.append(("role", w.get("role_secondary", 14), f"secondary target ({rec.get('category')})"))

    overlap, matched, missing = skill_overlap(rec.get("skills_required") or [], rec.get("skills_preferred") or [],
                                              profile.get("skills", {}))
    if overlap is None:
        parts.append(("skills", w.get("skills_unknown", 12), "no recognisable skills extracted"))
    else:
        parts.append(("skills", round(w.get("skills_max", 40) * overlap, 1),
                      f"{overlap:.0%} weighted overlap; matched {', '.join(matched[:6]) or 'none'}"))

    elig = rec.get("eligible")
    if elig == "yes":
        parts.append(("location", w.get("location_yes", 12), rec.get("eligibility_reason", "")))
    elif elig == "uncertain":
        parts.append(("location", w.get("location_uncertain", 5), rec.get("eligibility_reason", "")))

    gap = years_gap(rec.get("experience_min"), profile)
    exp_max = w.get("experience_max", 10)
    if rec.get("experience_min") is None:
        parts.append(("experience", w.get("experience_unknown", 5), "no years requirement found"))
    elif gap is None:
        parts.append(("experience", w.get("experience_unknown", 5), f"asks {rec['experience_min']}+ yrs; your years unknown"))
    elif gap <= 0:
        parts.append(("experience", exp_max, f"asks {rec['experience_min']}+ yrs; you meet it"))
    else:
        pts = max(w.get("experience_floor", -12), exp_max - w.get("experience_per_year_gap", 4) * gap)
        parts.append(("experience", pts, f"asks {rec['experience_min']}+ yrs; {gap} yr gap"))

    mine = cand.get("years_experience", -1)
    senior_ok = mine is not None and mine >= 8
    if rec.get("seniority") in ("staff", "principal") and not senior_ok:
        parts.append(("seniority", w.get("seniority_staff_penalty", -8), f"{rec['seniority']} level"))
    elif rec.get("seniority") == "lead" and not senior_ok:
        parts.append(("seniority", w.get("seniority_lead_penalty", -3), "lead role"))

    floor = float(cand.get("min_salary_usd_year", 0) or 0)
    usd = rec.get("salary_usd")
    if usd and floor > 0:
        if usd < floor:
            parts.append(("salary", w.get("salary_below_min", -12), f"max ≈ ${usd:,.0f}/yr < floor ${floor:,.0f}"))
        else:
            parts.append(("salary", w.get("salary_meets_min", 3), f"max ≈ ${usd:,.0f}/yr"))

    if rec.get("posted_at"):
        try:
            age = (today - date.fromisoformat(rec["posted_at"][:10])).days
            if age <= 7:
                parts.append(("fresh", w.get("fresh_7d", 3), f"posted {age}d ago"))
            elif age <= 30:
                parts.append(("fresh", w.get("fresh_30d", 1), f"posted {age}d ago"))
        except ValueError:
            pass

    preferred = {c.lower() for c in profile.get("companies", {}).get("preferred", [])}
    if rec.get("company", "").lower() in preferred:
        parts.append(("company", w.get("preferred_company", 5), "preferred company"))

    total = round(sum(p[1] for p in parts), 1)

    # confidence in the *extracted data*, not in the match
    signals = [
        (rec.get("_text_len") or 0) > 500,
        rec.get("remote") not in (None, "unknown"),
        elig in ("yes", "no"),
        rec.get("experience_min") is not None,
        len((rec.get("skills_required") or []) + (rec.get("skills_preferred") or [])) >= 3,
    ]
    n = sum(signals)
    confidence = "high" if n >= 4 else "medium" if n == 3 else "low"

    if elig == "no":
        label = "Ineligible"
    elif confidence == "low" and total >= w.get("stretch", 35):
        label = "Needs verification"
    elif (gap is not None and gap >= w.get("stretch_gap_years", 3) and (overlap or 0) >= w.get("stretch_min_overlap", 0.55)) \
            or (rec.get("seniority") in ("staff", "principal") and not senior_ok and total >= w.get("stretch", 35)):
        label = "Stretch"
    elif total >= w.get("strong", 65) and (overlap is None or overlap >= w.get("strong_min_overlap", 0.5)):
        label = "Strong match"
    elif total >= w.get("reasonable", 50):
        label = "Reasonable match"
    elif total >= w.get("stretch", 35):
        label = "Stretch"
    else:
        label = "Poor match"

    held = {c.lower() for c in cand.get("certifications", [])}
    return {
        "score": total,
        "label": label,
        "confidence": confidence,
        "overlap": None if overlap is None else round(overlap, 3),
        "breakdown": {
            "parts": [{"c": c, "pts": p, "why": r} for c, p, r in parts],
            "matched": matched,
            "missing_required": missing,
            "cert_gaps": [c for c in (rec.get("certs") or []) if c not in held],
            "gap_years": gap,
        },
    }
