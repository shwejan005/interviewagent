"""
Request/response models for the hiring domain.

Kept separate from models.py, which holds the agent-output schemas, because
the two evolve for entirely different reasons: those are constrained by what
an LLM must emit, these by what a client sends.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator
from pydantic import BaseModel, Field, field_validator, model_validator

from app.shared.input_validation import NormalizedEmail


# ── Candidate profile ────────────────────────────────────────────────


class ProfileUpsertRequest(BaseModel):
    headline: str = Field(default="", max_length=200)
    summary: str = Field(default="", max_length=5_000)
    location: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=40)
    work_authorization: str = Field(default="", max_length=200)
    years_experience: Optional[float] = Field(default=None, ge=0, le=70)
    open_to_work: bool = True
    # Opt-in, defaults closed. See hiring_schema.py for why this is distinct
    # from open_to_work.
    is_discoverable: bool = False
    resume_text: str = Field(default="", max_length=20_000)


class ExperienceRequest(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    location: str = Field(default="", max_length=200)
    # ISO-8601 date strings, free-form enough to accept "2021-03" or "2021-03-01".
    start_date: str = Field(min_length=4, max_length=10)
    end_date: Optional[str] = Field(default=None, max_length=10)
    is_current: bool = False
    description: str = Field(default="", max_length=5_000)


class EducationRequest(BaseModel):
    institution: str = Field(min_length=1, max_length=200)
    degree: str = Field(default="", max_length=200)
    field: str = Field(default="", max_length=200)
    start_year: Optional[int] = Field(default=None, ge=1900, le=2100)
    end_year: Optional[int] = Field(default=None, ge=1900, le=2100)


class SkillEntry(BaseModel):
    skill: str = Field(min_length=1, max_length=100)
    years: Optional[float] = Field(default=None, ge=0, le=70)


class SkillsRequest(BaseModel):
    skills: list[SkillEntry] = Field(max_length=200)


class PreferencesRequest(BaseModel):
    desired_roles: list[str] = Field(default_factory=list, max_length=20)
    locations: list[str] = Field(default_factory=list, max_length=20)
    remote_preference: str = Field(default="ANY", pattern="^(ANY|REMOTE|HYBRID|ONSITE)$")
    min_salary: Optional[float] = Field(default=None, ge=0)
    max_salary: Optional[float] = Field(default=None, ge=0)
    currency: str = Field(default="INR", max_length=8)
    notice_period_days: Optional[int] = Field(default=None, ge=0, le=365)


class VaultAnswerRequest(BaseModel):
    question_key: str = Field(min_length=1, max_length=100)
    question_text: str = Field(default="", max_length=500)
    answer_text: str = Field(min_length=1, max_length=5_000)


# ── Campaigns & postings ─────────────────────────────────────────────


class CampaignRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5_000)
    department: str = Field(default="", max_length=200)
    hiring_manager: str = Field(default="", max_length=200)
    priority: str = Field(default="MEDIUM", pattern="^(LOW|MEDIUM|HIGH|URGENT)$")
    target_hires: Optional[int] = Field(default=None, ge=1, le=500)
    # Free-form ISO date string (e.g. "2026-12-31"), consistent with the
    # candidate profile date fields elsewhere in this module.
    target_close_date: Optional[str] = Field(default=None, max_length=10)


class CampaignUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5_000)
    department: Optional[str] = Field(default=None, max_length=200)
    hiring_manager: Optional[str] = Field(default=None, max_length=200)
    priority: Optional[str] = Field(default=None, pattern="^(LOW|MEDIUM|HIGH|URGENT)$")
    target_hires: Optional[int] = Field(default=None, ge=1, le=500)
    target_close_date: Optional[str] = Field(default=None, max_length=10)
    status: Optional[str] = Field(default=None, pattern="^(ACTIVE|CLOSED)$")

    @model_validator(mode="after")
    def reject_null_required_fields(self):
        nullable_fields = {"target_hires", "target_close_date"}
        for field in self.model_fields_set - nullable_fields:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class CampaignMemberRequest(BaseModel):
    user_id: int = Field(ge=1)
    member_role: str = Field(default="RECRUITER", min_length=1, max_length=80)


class ScreeningQuestion(BaseModel):
    """A posting-specific question.

    `key` is what makes the answer vault work: a stable key means the same
    question asked by a different company can be pre-filled from a previous
    answer.
    """
    key: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=500)
    required: bool = True


class PostingRequest(BaseModel):
    campaign_id: int
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=20_000)
    location: str = Field(default="", max_length=200)
    employment_type: str = Field(default="FULL_TIME", pattern="^(FULL_TIME|PART_TIME|CONTRACT|INTERNSHIP)$")
    remote_policy: str = Field(default="ONSITE", pattern="^(REMOTE|HYBRID|ONSITE)$")
    min_experience: Optional[float] = Field(default=None, ge=0, le=70)
    max_experience: Optional[float] = Field(default=None, ge=0, le=70)
    salary_min: Optional[float] = Field(default=None, ge=0)
    salary_max: Optional[float] = Field(default=None, ge=0)
    currency: str = Field(default="INR", max_length=8)
    required_skills: list[str] = Field(default_factory=list, max_length=50)
    screening_questions: list[ScreeningQuestion] = Field(default_factory=list, max_length=20)
    # Opt-in only. See DECISIONS.md D-10.
    auto_reject_enabled: bool = False

    @model_validator(mode="after")
    def require_unique_screening_question_keys(self):
        keys = [question.key for question in self.screening_questions]
        if len(keys) != len(set(keys)):
            raise ValueError("screening question keys must be unique")
        return self


class PostingUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=20_000)
    location: Optional[str] = Field(default=None, max_length=200)
    employment_type: Optional[str] = Field(default=None, pattern="^(FULL_TIME|PART_TIME|CONTRACT|INTERNSHIP)$")
    remote_policy: Optional[str] = Field(default=None, pattern="^(REMOTE|HYBRID|ONSITE)$")
    min_experience: Optional[float] = Field(default=None, ge=0, le=70)
    max_experience: Optional[float] = Field(default=None, ge=0, le=70)
    salary_min: Optional[float] = Field(default=None, ge=0)
    salary_max: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, min_length=1, max_length=8)
    required_skills: Optional[list[str]] = Field(default=None, max_length=50)
    screening_questions: Optional[list[ScreeningQuestion]] = Field(default=None, max_length=20)
    auto_reject_enabled: Optional[bool] = None

    @model_validator(mode="after")
    def validate_partial_update(self):
        nullable_fields = {"min_experience", "max_experience", "salary_min", "salary_max"}
        for field in self.model_fields_set - nullable_fields:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        if self.screening_questions is not None:
            keys = [question.key for question in self.screening_questions]
            if len(keys) != len(set(keys)):
                raise ValueError("screening question keys must be unique")
        return self


class PostingStatusRequest(BaseModel):
    status: str = Field(pattern="^(DRAFT|PUBLISHED|CLOSED)$")


# ── Applications ─────────────────────────────────────────────────────


class ApplicationAnswer(BaseModel):
    question_key: str = Field(min_length=1, max_length=100)
    question_text: str = Field(default="", max_length=500)
    answer_text: str = Field(default="", max_length=5_000)


class ApplyRequest(BaseModel):
    """Apply to a posting.

    Answers are optional because the vault pre-fills them; only genuinely new
    questions need to be supplied. Supplied answers are written back to the
    vault so the next application can reuse them.
    """
    answers: list[ApplicationAnswer] = Field(default_factory=list, max_length=20)
    save_answers_to_vault: bool = True


class TransitionRequest(BaseModel):
    to_stage: str = Field(
        pattern="^(SCREENING|AI_INTERVIEW|PENDING_REVIEW|TECHNICAL|BEHAVIORAL|INTERVIEW|OFFER|HIRED|REJECTED)$"
    )
    note: str = Field(default="", max_length=2_000)


class ApplicationDecisionRequest(BaseModel):
    action: Literal["PROMOTE", "HOLD", "REJECT"]
    target_stage: Optional[Literal["TECHNICAL", "BEHAVIORAL", "INTERVIEW", "OFFER"]] = None
    reason: str = Field(default="", max_length=2_000)
    scheduled_start: Optional[str] = Field(default=None, min_length=10, max_length=40)
    scheduled_end: Optional[str] = Field(default=None, min_length=10, max_length=40)
    timezone: str = Field(default="UTC", min_length=1, max_length=80)
    interviewer_user_ids: list[int] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_decision_details(self):
        if self.action == "PROMOTE" and self.target_stage is None:
            raise ValueError("A target stage is required when promoting an application")
        if self.action != "PROMOTE" and self.target_stage is not None:
            raise ValueError("A target stage is only valid when promoting an application")
        schedules_human_round = self.action == "PROMOTE" and self.target_stage in {"TECHNICAL", "BEHAVIORAL", "INTERVIEW"}
        if schedules_human_round and bool(self.scheduled_start) != bool(self.scheduled_end):
            raise ValueError("Both scheduled_start and scheduled_end are required to schedule a human round")
        if not schedules_human_round and (self.scheduled_start or self.scheduled_end or self.interviewer_user_ids):
            raise ValueError("Interview scheduling details only apply when promoting to a human round")
        if self.action != "PROMOTE" and (self.scheduled_start or self.scheduled_end or self.interviewer_user_ids):
            raise ValueError("Scheduling and interviewers are only valid when promoting an application")
        return self


class InterviewCreateRequest(BaseModel):
    title: str = Field(default="Interview", min_length=1, max_length=200)
    scheduled_start: str = Field(min_length=10, max_length=40)
    scheduled_end: str = Field(min_length=10, max_length=40)
    timezone: str = Field(default="UTC", min_length=1, max_length=80)
    meeting_url: str = Field(default="", max_length=2_000)
    interviewer_user_ids: list[int] = Field(default_factory=list, max_length=20)


class InterviewScorecardRatingRequest(BaseModel):
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    label: str = Field(min_length=1, max_length=120)
    score: int = Field(ge=1, le=5)
    evidence: str = Field(min_length=10, max_length=1_000)

    @field_validator("evidence")
    @classmethod
    def require_meaningful_scorecard_evidence(cls, value: str) -> str:
        evidence = value.strip()
        if len(evidence) < 10:
            raise ValueError("Each scorecard rating requires at least 10 characters of job-related evidence")
        return evidence


class InterviewScorecardRequest(BaseModel):
    ratings: list[InterviewScorecardRatingRequest] = Field(min_length=1, max_length=30)
    recommendation: Literal["ADVANCE", "HOLD"]
    notes: str = Field(default="", max_length=4_000)

    @model_validator(mode="after")
    def require_unique_rating_keys(self):
        keys = [rating.key for rating in self.ratings]
        if len(keys) != len(set(keys)):
            raise ValueError("Scorecard rating keys must be unique")
        return self


# ── Referrals ────────────────────────────────────────────────────────


class ReferralRequest(BaseModel):
    candidate_email: NormalizedEmail
    note: str = Field(default="", max_length=2_000)
