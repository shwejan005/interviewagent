"""Strict request and model-output contracts for application AI interviews."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScreeningEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion_key: str = Field(min_length=1, max_length=80)
    status: Literal["MET", "MISSING", "UNCLEAR"]
    source: Optional[Literal["RESUME", "PROFILE", "APPLICATION_ANSWER"]] = None
    quote: str = Field(default="", max_length=500)
    value: Optional[float] = Field(default=None, ge=0, le=70)
    rationale: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def require_source_for_met_evidence(self):
        if self.status == "MET" and (not self.source or len(self.quote.strip()) < 3):
            raise ValueError("MET screening evidence requires a source and exact evidence quote")
        return self


class ApplicationScreeningAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["PASS", "REVIEW_REQUIRED"]
    score: float = Field(ge=0, le=10)
    evidence: list[ScreeningEvidence] = Field(min_length=1, max_length=40)
    strengths: list[str] = Field(default_factory=list, max_length=12)
    gaps: list[str] = Field(default_factory=list, max_length=12)
    summary: str = Field(min_length=1, max_length=1500)

    @model_validator(mode="after")
    def require_unique_evidence_keys(self):
        keys = [item.criterion_key for item in self.evidence]
        if len(keys) != len(set(keys)):
            raise ValueError("Screening evidence criterion keys must be unique")
        return self


class InterviewQuestion(BaseModel):
    competency_key: str = Field(min_length=1, max_length=60)
    question: str = Field(min_length=12, max_length=700)
    difficulty: int = Field(ge=1, le=3)


class InterviewQuestionPlan(BaseModel):
    technical_questions: list[InterviewQuestion] = Field(min_length=1, max_length=5)
    behavioral_questions: list[InterviewQuestion] = Field(min_length=1, max_length=4)


class AnswerAssessment(BaseModel):
    score: float = Field(ge=0, le=10)
    evidence_quote: str = Field(default="", max_length=500)
    summary: str = Field(min_length=1, max_length=1200)
    strengths: list[str] = Field(default_factory=list, max_length=8)
    gaps: list[str] = Field(default_factory=list, max_length=8)
    follow_up_question: Optional[str] = Field(default=None, max_length=700)
    next_difficulty: int = Field(ge=1, le=3)

    @model_validator(mode="after")
    def validate_evidence_quote(self):
        if self.evidence_quote and len(self.evidence_quote.strip()) < 8:
            raise ValueError("evidence_quote must be a meaningful exact excerpt or empty")
        return self


class StartInterviewRequest(BaseModel):
    accepted: bool
    notice_version: str = Field(min_length=1, max_length=80)
    modality: Literal["TEXT", "VOICE"] = "TEXT"


class RequestTextAccommodation(BaseModel):
    notice_version: str = Field(min_length=1, max_length=80)


class ScreeningOverrideRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


class SubmitInterviewAnswerRequest(BaseModel):
    turn_id: int = Field(ge=1)
    answer: str = Field(min_length=1, max_length=12000)
    source: Literal["TEXT", "VOICE"] = "TEXT"


class SaveInterviewDraftRequest(BaseModel):
    turn_id: int = Field(ge=1)
    draft_answer_text: str = Field(default="", max_length=12000)


class CandidateInterviewTurn(BaseModel):
    id: int
    sequence_no: int
    phase: Literal["TECHNICAL", "BEHAVIORAL"]
    question_type: Literal["CORE", "FOLLOW_UP"]
    competency_key: str
    difficulty: int
    question_text: str
    draft_answer_text: str = ""
    draft_updated_at: Optional[datetime | str] = None
    answer_text: Optional[str] = None
    answer_source: Literal["TEXT", "VOICE"] = "TEXT"
    state: Literal["ASKED", "ANSWER_QUEUED", "ASSESSED"]


class CandidateInterviewResponse(BaseModel):
    application_id: int
    status: str
    phase: str
    rubric_version: str
    role_level: str
    candidate_notice_version: str
    modality: Literal["TEXT", "VOICE"] = "TEXT"
    invitation_expires_at: Optional[datetime | str] = None
    consent_required: bool
    current_question: Optional[CandidateInterviewTurn] = None
    turns: list[CandidateInterviewTurn] = Field(default_factory=list)
    message: str = ""


class RecruiterInterviewStatusResponse(BaseModel):
    application_id: int
    status: str
    phase: str
    rubric_version: str
    screening_result: dict = Field(default_factory=dict)
    error_code: Optional[str] = None
    updated_at: str
