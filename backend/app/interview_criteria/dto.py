"""DTOs for the recruiter-defined evaluation criteria and generated reports."""

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class InterviewSettingsDTO(BaseModel):
    role_level: Literal["ENTRY", "MID", "SENIOR"] = "MID"
    technical_question_count: int = Field(default=2, ge=1, le=5)
    behavioral_question_count: int = Field(default=2, ge=1, le=4)
    max_followups_per_question: int = Field(default=1, ge=0, le=2)
    invitation_window_days: int = Field(default=7, ge=1, le=30)


class CriterionDTO(BaseModel):
    key: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=120)
    weight: float = Field(gt=0, le=100)
    description: str = Field(default="", max_length=500)
    category: Optional[Literal["TECHNICAL", "BEHAVIORAL"]] = None


class CriteriaUpsertRequest(BaseModel):
    competencies: list[CriterionDTO] = Field(min_length=1, max_length=20)
    custom_questions: list[str] = Field(default_factory=list, max_length=20)
    pass_threshold: float = Field(default=6.0, ge=0, le=10)
    interview_settings: InterviewSettingsDTO = Field(default_factory=InterviewSettingsDTO)

    @model_validator(mode="after")
    def require_technical_and_behavioral_competencies(self):
        behavioral_terms = re.compile(
            r"communication|behavior|teamwork|collaboration|leadership|ownership|conflict|adaptability|stakeholder|mentoring",
            re.IGNORECASE,
        )
        categories = {
            item.category or ("BEHAVIORAL" if behavioral_terms.search(f"{item.key} {item.label}") else "TECHNICAL")
            for item in self.competencies
        }
        if not {"TECHNICAL", "BEHAVIORAL"} <= categories:
            raise ValueError("The AI interview rubric must include at least one technical and one behavioral competency")
        return self


class CriteriaResponse(BaseModel):
    posting_id: int
    competencies: list[CriterionDTO]
    custom_questions: list[str]
    pass_threshold: float
    interview_settings: InterviewSettingsDTO = Field(default_factory=InterviewSettingsDTO)
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
    interview_details: dict = Field(default_factory=dict)
