"""
Request/response models for the hiring domain.

Kept separate from models.py, which holds the agent-output schemas, because
the two evolve for entirely different reasons: those are constrained by what
an LLM must emit, these by what a client sends.
"""

from typing import Optional

from pydantic import BaseModel, Field


# ── Candidate profile ────────────────────────────────────────────────


class ProfileUpsertRequest(BaseModel):
    headline: str = Field(default="", max_length=200)
    summary: str = Field(default="", max_length=5_000)
    location: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=40)
    work_authorization: str = Field(default="", max_length=200)
    years_experience: Optional[float] = Field(default=None, ge=0, le=70)
    open_to_work: bool = True
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
    required_skills: Optional[list[str]] = Field(default=None, max_length=50)
    screening_questions: Optional[list[ScreeningQuestion]] = Field(default=None, max_length=20)
    auto_reject_enabled: Optional[bool] = None


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
        pattern="^(SCREENING|PENDING_REVIEW|TECHNICAL|BEHAVIORAL|INTERVIEW|OFFER|HIRED|REJECTED)$"
    )
    note: str = Field(default="", max_length=2_000)
