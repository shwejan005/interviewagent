"""DTOs for the recruiter-defined evaluation criteria and generated reports."""

from typing import Optional

from pydantic import BaseModel, Field


class CriterionDTO(BaseModel):
    key: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=120)
    weight: float = Field(gt=0, le=100)
    description: str = Field(default="", max_length=500)


class CriteriaUpsertRequest(BaseModel):
    competencies: list[CriterionDTO] = Field(min_length=1, max_length=20)
    custom_questions: list[str] = Field(default_factory=list, max_length=20)
    pass_threshold: float = Field(default=6.0, ge=0, le=10)


class CriteriaResponse(BaseModel):
    posting_id: int
    competencies: list[CriterionDTO]
    custom_questions: list[str]
    pass_threshold: float
    rubric_version: str
    updated_at: str


class CompetencyScoreDTO(BaseModel):
    key: str
    label: str
    weight: float
    score: Optional[float]
    evidence: str


class ApplicationReportResponse(BaseModel):
    application_id: int
    evaluation_id: int
    posting_id: int
    competency_scores: list[CompetencyScoreDTO]
    overall_weighted_score: Optional[float]
    recommendation: str
    rubric_version: str
    generated_at: str
