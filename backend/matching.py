"""
Deterministic matching engine — Stage 1 of the staged approach in
docs/PRODUCT_BLUEPRINT.md §8.1.

Explicitly staged rather than jumping to embeddings or learned ranking:

  Stage 1 (this file): weighted, explainable, no training data required.
  Stage 2 (deferred):  semantic similarity via pgvector, once there is enough
                       posting/profile volume for it to add signal over
                       keyword overlap.
  Stage 3 (deferred):  learned ranking on real outcomes. Requires thousands
                       of labeled application outcomes that do not exist yet
                       — building this now would mean training on nothing.

Every score ships with its own explanation. A bare number a recruiter or
candidate cannot interrogate is not a recommendation, it is a black box, and
turning hiring signals into black boxes is exactly the failure mode this
system is designed to avoid (see docs/PRODUCT_BLUEPRINT.md §8.2).

The scoring function here is pure — no database access, no I/O — so it can be
unit-tested exhaustively without a database. Database orchestration
(fetching a pool and ranking it) lives in the second half of this module.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from candidate_db import normalize_skill

logger = logging.getLogger(__name__)

# Weights sum to 1.0 so the final score is directly interpretable as a
# weighted average, scaled to a 0-10 range to match the rest of the product's
# scoring convention (verdict scores are also 0-10).
_WEIGHTS = {
    "skills": 0.40,
    "experience": 0.25,
    "location": 0.20,
    "compensation": 0.10,
    "recency": 0.05,
}

# Extra credit within the skills component for a verified (not merely
# claimed) matching skill. Capped so it cannot push the component past 1.0.
_VERIFIED_SKILL_BONUS = 0.10

# Neutral scores used when there isn't enough information to judge a
# dimension. Deliberately not 0 or 1: an absence of data is not evidence of
# mismatch or fit, and scoring it as either would be a fabricated signal.
_NEUTRAL = 0.55


def _score_skills(required_skills: list[str], candidate_skills: list[dict]) -> tuple[float, dict]:
    if not required_skills:
        return 0.7, {"matched": [], "missing": [], "note": "posting lists no required skills"}

    # Preserve the posting's original casing for anything shown back to a
    # human; normalization is an internal matching detail, not display text.
    required_by_norm = {normalize_skill(s): s for s in required_skills if s.strip()}
    candidate_by_norm = {normalize_skill(s["skill"]): s for s in candidate_skills}

    matched_norm = required_by_norm.keys() & candidate_by_norm.keys()
    missing_norm = required_by_norm.keys() - candidate_by_norm.keys()

    base = len(matched_norm) / len(required_by_norm) if required_by_norm else 0.0
    verified_bonus = sum(
        _VERIFIED_SKILL_BONUS for n in matched_norm if candidate_by_norm[n].get("verified")
    )
    component = min(1.0, base + verified_bonus)

    return component, {
        "matched": sorted(candidate_by_norm[n]["skill"] for n in matched_norm),
        "missing": sorted(required_by_norm[n] for n in missing_norm),
    }


def _score_experience(years: Optional[float], min_exp: Optional[float],
                      max_exp: Optional[float]) -> tuple[float, str]:
    if min_exp is None and max_exp is None:
        return 1.0, "no experience requirement stated"
    if years is None:
        return _NEUTRAL, "candidate has not stated years of experience"

    lo = min_exp if min_exp is not None else 0.0
    hi = max_exp

    if hi is None and years >= lo:
        return 1.0, f"{years} years meets the {lo}-year minimum"
    if hi is not None and lo <= years <= hi:
        return 1.0, f"{years} years is within the {lo}-{hi} year requirement"
    if years < lo:
        deficit = lo - years
        component = max(0.0, 1 - deficit / max(lo, 1))
        return component, f"{deficit:.1f} years short of the {lo}-year minimum"
    # Over-qualified: penalized more gently than under-qualified, and floored
    # rather than driven to zero — too senior is a softer signal than too junior.
    if hi is None:
        return _NEUTRAL, "candidate has not stated years of experience"
    excess = years - hi
    component = max(0.3, 1 - excess / 10)
    return component, f"{excess:.1f} years above the {hi}-year maximum"


def _score_location(posting_location: str, remote_policy: str,
                    preferences: Optional[dict]) -> tuple[float, str]:
    remote_policy = (remote_policy or "ONSITE").upper()
    candidate_remote_pref = (preferences or {}).get("remote_preference", "ANY")
    candidate_locations = [normalize_skill(loc) for loc in (preferences or {}).get("locations", [])]

    if remote_policy == "REMOTE":
        if candidate_remote_pref == "ONSITE":
            return 0.3, "candidate prefers onsite; posting is fully remote"
        return 1.0, "posting is remote; location is not a constraint"

    if candidate_remote_pref == "REMOTE":
        return 0.2, f"candidate wants remote only; posting is {remote_policy.lower()}"

    if not candidate_locations:
        return _NEUTRAL, "candidate has not stated location preferences"

    posting_loc_norm = normalize_skill(posting_location or "")
    if any(loc in posting_loc_norm or posting_loc_norm in loc for loc in candidate_locations):
        return 1.0, f"posting location matches a candidate preference"
    return 0.4, "posting location is not among candidate preferences"


def _score_compensation(salary_min: Optional[float], salary_max: Optional[float],
                        preferences: Optional[dict]) -> tuple[float, str]:
    cand_min = (preferences or {}).get("min_salary")
    cand_max = (preferences or {}).get("max_salary")

    if salary_min is None and salary_max is None:
        return _NEUTRAL, "posting does not state a salary range"
    if cand_min is None and cand_max is None:
        return _NEUTRAL, "candidate has not stated salary expectations"

    p_lo, p_hi = salary_min or 0, salary_max if salary_max is not None else float("inf")
    c_lo, c_hi = cand_min or 0, cand_max if cand_max is not None else float("inf")

    overlap_lo, overlap_hi = max(p_lo, c_lo), min(p_hi, c_hi)
    if overlap_hi <= overlap_lo:
        return 0.15, "salary ranges do not overlap"

    # Ratio of overlap to the candidate's desired range width. A candidate
    # with an unbounded max (no ceiling stated) is treated as fully satisfied
    # by any overlap, since there is no width to compare against.
    cand_width = c_hi - c_lo
    if cand_width == float("inf") or cand_width == 0:
        return 1.0, "salary ranges overlap"
    ratio = min(1.0, (overlap_hi - overlap_lo) / cand_width)
    return 0.3 + 0.7 * ratio, "salary ranges partially overlap"


def _score_recency(updated_at: Optional[str]) -> float:
    if not updated_at:
        return _NEUTRAL
    try:
        # SQLite stores naive ISO strings, Postgres returns timezone-aware
        # datetimes already stringified by the row conversion — handle both.
        ts = updated_at.replace("Z", "+00:00") if isinstance(updated_at, str) else updated_at
        moment = datetime.fromisoformat(ts) if isinstance(ts, str) else ts
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - moment).days
    except (ValueError, TypeError):
        return _NEUTRAL

    if age_days < 30:
        return 1.0
    if age_days < 90:
        return 0.7
    if age_days < 180:
        return 0.4
    return 0.2


def score_match(
    profile: dict,
    skills: list[dict],
    preferences: Optional[dict],
    posting: dict,
) -> dict:
    """Score one candidate against one posting. Symmetric — used for both
    'jobs recommended to a candidate' and 'candidates recommended for a
    posting'; only which side is held fixed differs at the call site.
    """
    skills_score, skills_detail = _score_skills(posting.get("required_skills", []), skills)
    experience_score, experience_note = _score_experience(
        profile.get("years_experience"), posting.get("min_experience"), posting.get("max_experience")
    )
    location_score, location_note = _score_location(
        posting.get("location", ""), posting.get("remote_policy", "ONSITE"), preferences
    )
    compensation_score, compensation_note = _score_compensation(
        posting.get("salary_min"), posting.get("salary_max"), preferences
    )
    recency_score = _score_recency(profile.get("updated_at"))

    components = {
        "skills": round(skills_score, 3),
        "experience": round(experience_score, 3),
        "location": round(location_score, 3),
        "compensation": round(compensation_score, 3),
        "recency": round(recency_score, 3),
    }
    weighted = sum(components[k] * _WEIGHTS[k] for k in _WEIGHTS)
    overall = round(weighted * 10, 1)

    headline = []
    if skills_detail["matched"]:
        headline.append(f"Strong overlap on {', '.join(skills_detail['matched'][:4])}")
    if skills_detail["missing"]:
        headline.append(f"Gap: missing {', '.join(sorted(skills_detail['missing'])[:3])}")
    headline.append(experience_note)
    headline.append(location_note)

    return {
        "score": overall,
        "components": components,
        "matched_skills": skills_detail["matched"],
        "missing_skills": skills_detail["missing"],
        "explanation": ". ".join(h for h in headline if h) + ".",
    }


# ── Orchestration (database-touching) ───────────────────────────────


def rank_jobs_for_candidate(user_id: int, limit: int = 20) -> list[dict]:
    """Score every open, unapplied-to posting against one candidate's profile.

    O(published postings) per call — acceptable at pilot scale (hundreds of
    postings). At real volume this needs a pre-filtered candidate set (e.g.
    by required skill) before scoring, not a smarter scoring function; see
    docs/PRODUCT_BLUEPRINT.md §8.1 Stage 2 for the actual scaling answer
    (semantic pre-filtering via pgvector).
    """
    import candidate_db as cdb
    import hiring_db as hdb

    profile = cdb.get_profile_by_user(user_id)
    if profile is None:
        return []

    skills = cdb.list_skills(profile["id"])
    preferences = cdb.get_preferences(profile["id"])
    applied_posting_ids = {
        a["posting_id"] for a in hdb.list_applications_for_candidate(user_id, limit=1000)
        if a["withdrawn_at"] is None
    }

    results = hdb.search_published_postings(limit=200)
    ranked = []
    for posting in results["postings"]:
        if posting["id"] in applied_posting_ids:
            continue
        match = score_match(profile, skills, preferences, posting)
        ranked.append({
            "posting_id": posting["id"], "title": posting["title"],
            "org_name": posting["org_name"], "location": posting["location"],
            "remote_policy": posting["remote_policy"], **match,
        })

    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked[:limit]


def rank_candidates_for_posting(
    posting_id: int, org_id: int, limit: int = 20,
    skill: Optional[str] = None, location: Optional[str] = None,
) -> list[dict]:
    """Score discoverable, not-yet-applied candidates against one posting."""
    import candidate_db as cdb
    import hiring_db as hdb

    posting = hdb.get_posting(posting_id, org_id)
    if posting is None:
        return []

    applied_user_ids = {
        a["candidate_user_id"]
        for a in hdb.list_applications_for_posting(posting_id, org_id, limit=1000)
    }

    pool = cdb.search_discoverable_profiles(skill=skill, location=location, limit=200)
    ranked = []
    for profile in pool["profiles"]:
        if profile["user_id"] in applied_user_ids:
            continue
        preferences = cdb.get_preferences(profile["id"])
        match = score_match(profile, profile["skills"], preferences, posting)
        ranked.append({
            "user_id": profile["user_id"], "full_name": profile["full_name"],
            "headline": profile["headline"], "location": profile["location"],
            "years_experience": profile["years_experience"], **match,
        })

    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked[:limit]
