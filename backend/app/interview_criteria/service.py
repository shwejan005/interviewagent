"""Services: criteria CRUD (with default-derivation from posting skills) and
report generation from a completed evaluation's per-round verdicts.

The report heuristic is intentionally simple and transparent (v1): for each
recruiter-defined competency we keyword-match its label against the
technical/behavioral rounds and otherwise blend the available round scores.
This is documented here, not oversold as fine-grained AI grading, consistent
with how review_routes.py and evaluation_harness.py describe their own
heuristics elsewhere in this codebase.
"""

import logging
import re
from dataclasses import replace
from typing import Optional

from app.config import database as db
from app.hiring import repository as hdb

from app.interview_criteria.entity import ApplicationReport, PostingCriteria
from app.interview_criteria.repository import CriteriaRepository, ReportRepository

logger = logging.getLogger(__name__)

_TECHNICAL_KEYWORDS = re.compile(
    r"technical|coding|algorithm|system design|architecture|engineering|debugging|problem[- ]solving",
    re.IGNORECASE,
)
_BEHAVIORAL_KEYWORDS = re.compile(
    r"communication|leadership|teamwork|collaboration|culture|ownership|conflict|adaptability",
    re.IGNORECASE,
)

_ROUND_SCREENING = 1
_ROUND_TECHNICAL = 2
_ROUND_BEHAVIORAL = 3


class CriteriaService:
    def __init__(self, repository: Optional[CriteriaRepository] = None):
        self._repository = repository or CriteriaRepository()

    def get_or_default(self, posting_id: int, org_id: int) -> PostingCriteria:
        """Return saved criteria, or a sensible default derived from the
        posting's required_skills so a recruiter always sees a starting
        point instead of a blank form."""
        existing = self._repository.get(posting_id)
        if existing is not None:
            competencies = [
                {
                    **item,
                    "category": item.get("category") or (
                        "BEHAVIORAL" if _BEHAVIORAL_KEYWORDS.search(f"{item.get('key', '')} {item.get('label', '')}") else "TECHNICAL"
                    ),
                }
                for item in existing.competencies
            ]
            settings = {"invitation_window_days": 7, **(existing.interview_settings or {})}
            return replace(existing, competencies=competencies, interview_settings=settings)

        posting = hdb.get_posting(posting_id, org_id)
        required_skills = (posting or {}).get("required_skills") or []
        selected_skills = required_skills[:10]
        if selected_skills:
            technical_weight = 80.0
            competencies = [
                {
                    "key": re.sub(r"[^a-z0-9_]", "_", skill.lower())[:60] or f"skill_{i}",
                    "label": skill,
                    "weight": round(technical_weight / len(selected_skills), 2),
                    "description": "",
                    "category": "TECHNICAL",
                }
                for i, skill in enumerate(selected_skills)
            ]
            # Assign rounding remainder deterministically so the rubric totals 100.
            competencies[0]["weight"] = round(technical_weight - sum(c["weight"] for c in competencies[1:]), 2)
            competencies.append({
                "key": "behavioral_communication",
                "label": "Behavioral communication and collaboration",
                "weight": 20.0,
                "description": "Job-related clarity, collaboration, and ownership demonstrated in concrete work examples.",
                "category": "BEHAVIORAL",
            })
        else:
            competencies = [
                {"key": "technical_skills", "label": "Technical skills", "weight": 50.0, "description": "", "category": "TECHNICAL"},
                {"key": "behavioral_communication", "label": "Behavioral communication and collaboration", "weight": 50.0, "description": "", "category": "BEHAVIORAL"},
            ]
        return PostingCriteria(
            posting_id=posting_id,
            org_id=org_id,
            competencies=competencies,
            custom_questions=[],
            pass_threshold=6.0,
            interview_settings={
                "role_level": "MID",
                "technical_question_count": 2,
                "behavioral_question_count": 2,
                "max_followups_per_question": 1,
                "invitation_window_days": 7,
            },
            rubric_version="posting-v1",
            updated_by=None,
            updated_at="",
        )

    def upsert(
        self,
        posting_id: int,
        org_id: int,
        competencies: list[dict],
        custom_questions: list[str],
        pass_threshold: float,
        interview_settings: dict,
        updated_by: int,
    ) -> PostingCriteria:
        normalized_competencies = [
            {
                **item,
                "category": item.get("category") or (
                    "BEHAVIORAL" if _BEHAVIORAL_KEYWORDS.search(f"{item.get('key', '')} {item.get('label', '')}") else "TECHNICAL"
                ),
            }
            for item in competencies
        ]
        return self._repository.upsert(
            posting_id, org_id, normalized_competencies, custom_questions, pass_threshold,
            interview_settings, updated_by
        )


class ReportService:
    def __init__(self, report_repository: Optional[ReportRepository] = None, criteria_repository: Optional[CriteriaRepository] = None):
        self._reports = report_repository or ReportRepository()
        self._criteria = criteria_repository or CriteriaRepository()

    def get(self, application_id: int) -> Optional[ApplicationReport]:
        return self._reports.get_by_application(application_id)

    def generate_from_evaluation(self, evaluation_id: int) -> Optional[ApplicationReport]:
        """Best-effort report generation called from finalize_evaluation.

        Returns None (without raising) when the evaluation has no linked
        application/posting, or no criteria have been defined yet — both are
        normal for evaluations created outside the recruiter pipeline.
        """
        application = hdb.get_application_by_evaluation_id(evaluation_id)
        if application is None:
            return None

        posting_id = application["posting_id"]
        criteria = self._criteria.get(posting_id)
        if criteria is None:
            logger.info("No evaluation criteria defined for posting %s; skipping report.", posting_id)
            return None

        evaluation = db.get_evaluation(evaluation_id)
        if evaluation is None:
            return None
        verdicts_by_round = {v["round_number"]: v for v in db.get_verdicts(evaluation_id)}

        competency_scores = []
        for competency in criteria.competencies:
            label = competency.get("label", "")
            key = competency.get("key", "")
            weight = float(competency.get("weight", 0))

            if _TECHNICAL_KEYWORDS.search(label):
                rounds = [_ROUND_TECHNICAL]
            elif _BEHAVIORAL_KEYWORDS.search(label):
                rounds = [_ROUND_BEHAVIORAL]
            else:
                rounds = [_ROUND_SCREENING, _ROUND_TECHNICAL, _ROUND_BEHAVIORAL]

            relevant = [verdicts_by_round[r] for r in rounds if r in verdicts_by_round and verdicts_by_round[r].get("score") is not None]
            if relevant:
                score = round(sum(v["score"] for v in relevant) / len(relevant), 2)
                evidence = (relevant[0].get("verdict_text") or "")[:200]
            else:
                score = None
                evidence = "No scored round available for this competency."

            competency_scores.append(
                {"key": key, "label": label, "weight": weight, "score": score, "evidence": evidence}
            )

        scored = [c for c in competency_scores if c["score"] is not None]
        total_weight = sum(c["weight"] for c in scored)
        overall_weighted_score = (
            round(sum(c["score"] * c["weight"] for c in scored) / total_weight, 2)
            if total_weight > 0
            else None
        )
        recommendation = evaluation.get("final_decision") or "PENDING"

        return self._reports.upsert(
            application_id=application["id"],
            evaluation_id=evaluation_id,
            posting_id=posting_id,
            org_id=application["org_id"],
            competency_scores=competency_scores,
            overall_weighted_score=overall_weighted_score,
            recommendation=recommendation,
            rubric_version=criteria.rubric_version,
        )
