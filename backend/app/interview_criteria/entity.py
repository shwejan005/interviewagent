"""Entities: persisted shapes for posting criteria and generated reports."""

import json
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class PostingCriteria:
    posting_id: int
    org_id: int
    competencies: list[dict] = field(default_factory=list)
    custom_questions: list[str] = field(default_factory=list)
    pass_threshold: float = 6.0
    rubric_version: str = "posting-v1"
    updated_by: Optional[int] = None
    updated_at: str = ""

    @staticmethod
    def from_row(row: Optional[dict]) -> Optional["PostingCriteria"]:
        if row is None:
            return None
        return PostingCriteria(
            posting_id=row["posting_id"],
            org_id=row["org_id"],
            competencies=json.loads(row["competencies_json"] or "[]"),
            custom_questions=json.loads(row["custom_questions_json"] or "[]"),
            pass_threshold=row["pass_threshold"],
            rubric_version=row["rubric_version"],
            updated_by=row.get("updated_by"),
            updated_at=str(row["updated_at"]),
        )


@dataclass(frozen=True)
class ApplicationReport:
    application_id: int
    evaluation_id: int
    posting_id: int
    org_id: int
    competency_scores: list[dict[str, Any]] = field(default_factory=list)
    overall_weighted_score: Optional[float] = None
    recommendation: str = ""
    rubric_version: str = "posting-v1"
    generated_at: str = ""

    @staticmethod
    def from_row(row: Optional[dict]) -> Optional["ApplicationReport"]:
        if row is None:
            return None
        return ApplicationReport(
            application_id=row["application_id"],
            evaluation_id=row["evaluation_id"],
            posting_id=row["posting_id"],
            org_id=row["org_id"],
            competency_scores=json.loads(row["competency_scores_json"] or "[]"),
            overall_weighted_score=row.get("overall_weighted_score"),
            recommendation=row["recommendation"],
            rubric_version=row["rubric_version"],
            generated_at=str(row["generated_at"]),
        )
