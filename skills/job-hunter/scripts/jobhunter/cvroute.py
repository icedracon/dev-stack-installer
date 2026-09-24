"""Pick the most suitable CV variant for a job. Deterministic and explained."""
from __future__ import annotations

from pathlib import Path


def route(job: dict, profile: dict, cv_dir: Path) -> dict | None:
    variants = profile.get("cv", [])
    if not variants:
        return None
    job_skills = set((job.get("skills_required") or []) + (job.get("skills_preferred") or []))
    best, best_key, best_reason = None, None, ""
    for cv in variants:
        cat_hit = job.get("category") in cv.get("categories", [])
        emph = [s for s in cv.get("emphasis", []) if s in job_skills]
        key = (int(cat_hit), len(emph), int(bool(cv.get("default"))))
        if best_key is None or key > best_key:
            parts = []
            if cat_hit:
                parts.append(f"targets category '{job.get('category')}'")
            if emph:
                parts.append(f"emphasises {', '.join(emph[:5])} which the posting asks for")
            if not parts:
                parts.append("default variant (no category or emphasis match)")
            best, best_key, best_reason = cv, key, "; ".join(parts)
    path = cv_dir / best.get("file", "")
    return {"name": best.get("name"), "file": str(path), "exists": path.is_file(), "reason": best_reason}
