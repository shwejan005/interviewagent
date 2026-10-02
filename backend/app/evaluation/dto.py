"""
Pydantic Models — Structured output schemas for all agents.

These models define the exact JSON structure each agent must produce,
ensuring deterministic, parseable, and validateable outputs.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field
from enum import Enum

from app.shared.input_validation import NormalizedEmail


# ── Enums ──────────────────────────────────────────────────────────


class ScreeningDecision(str, Enum):
    PASS = "PASS"
    BORDERLINE = "BORDERLINE"
    FAIL = "FAIL"


class RoundDecision(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class BehavioralDecision(str, Enum):
    PASS = "PASS"
    BORDERLINE = "BORDERLINE"
    FAIL = "FAIL"


class HiringDecision(str, Enum):
    HIRE = "HIRE"
    HOLD = "HOLD"
    REJECT = "REJECT"


class EvaluationStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    REJECTED = "REJECTED"


# ── Agent Output Models ────────────────────────────────────────────


class ScreeningVerdict(BaseModel):
    """Output from the Resume Screening Agent."""
    decision: ScreeningDecision = Field(description="PASS, BORDERLINE, or FAIL")
    score: float = Field(ge=0, le=10, description="Score from 0 to 10")
    strengths: list[str] = Field(description="Key strengths identified")
    weaknesses: list[str] = Field(description="Key weaknesses identified")
    reasoning: str = Field(description="Detailed explanation of the evaluation")
    candidate_summary: str = Field(description="Brief summary of the candidate profile")
    skills_extracted: list[str] = Field(default_factory=list, description="Technical skills extracted from resume")
    experience_years: Optional[int] = Field(default=None, description="Estimated years of experience")
    recommended_questions: list[str] = Field(description="2-3 questions for the next round")
    confidence: float = Field(ge=0, le=1, description="Confidence in this assessment (0-1); the agent must assert this explicitly")


class QuestionEvaluation(BaseModel):
    """Evaluation of a single interview question response."""
    question: str = Field(description="The question that was asked")
    correctness: float = Field(ge=0, le=10, description="Correctness score 0-10")
    depth: float = Field(ge=0, le=10, description="Depth of understanding 0-10")
    clarity: float = Field(ge=0, le=10, description="Communication clarity 0-10")
    assessment: str = Field(description="Brief assessment of the answer")


class TechnicalVerdict(BaseModel):
    """Output from the Technical Interview Agent."""
    decision: RoundDecision = Field(description="PASS or FAIL")
    score: float = Field(ge=0, le=10, description="Overall technical score 0-10")
    question_evaluations: list[QuestionEvaluation] = Field(description="Per-question evaluations")
    strengths: list[str] = Field(description="Technical strengths demonstrated")
    weaknesses: list[str] = Field(description="Technical weaknesses identified")
    reasoning: str = Field(description="Detailed technical evaluation")
    coding_quality: Optional[float] = Field(default=None, ge=0, le=10, description="Code quality if applicable")
    confidence: float = Field(ge=0, le=1, description="Confidence in this assessment (0-1); the agent must assert this explicitly")


class BehavioralVerdict(BaseModel):
    """Output from the Behavioral Interview Agent."""
    decision: BehavioralDecision = Field(description="PASS, BORDERLINE, or FAIL")
    score: float = Field(ge=0, le=10, description="Overall behavioral score 0-10")
    star_evaluation: str = Field(description="Assessment of STAR response quality")
    leadership: float = Field(ge=0, le=10, description="Leadership score 0-10")
    communication: float = Field(ge=0, le=10, description="Communication score 0-10")
    teamwork: float = Field(ge=0, le=10, description="Teamwork score 0-10")
    ownership: float = Field(ge=0, le=10, description="Ownership/accountability score 0-10")
    conflict_handling: float = Field(ge=0, le=10, description="Conflict resolution score 0-10")
    culture_fit: float = Field(ge=0, le=10, description="Culture fit assessment 0-10")
    strengths: list[str] = Field(description="Behavioral strengths")
    weaknesses: list[str] = Field(description="Behavioral weaknesses")
    reasoning: str = Field(description="Detailed behavioral evaluation")
    confidence: float = Field(ge=0, le=1, description="Confidence in this assessment (0-1); the agent must assert this explicitly")


class HiringRecommendation(BaseModel):
    """Output from the Hiring Recommendation Agent."""
    decision: HiringDecision = Field(description="HIRE, HOLD, or REJECT")
    score: float = Field(ge=0, le=10, description="Overall recommendation score 0-10")
    detailed_recommendation: str = Field(description="Comprehensive recommendation narrative")
    risks: list[str] = Field(description="Identified hiring risks")
    positives: list[str] = Field(description="Key positives supporting hire")
    suggested_role: str = Field(description="Suggested role/level for the candidate")
    growth_areas: list[str] = Field(default_factory=list, description="Areas for development")
    confidence: float = Field(ge=0, le=1, description="Confidence in this recommendation (0-1); the agent must assert this explicitly")


class RoundSummary(BaseModel):
    """Summary of a single evaluation round."""
    round_name: str = Field(description="Name of the round")
    decision: str = Field(description="Decision from this round")
    score: float = Field(ge=0, le=10, description="Score from this round")
    key_finding: str = Field(description="Most important finding from this round")


class CommitteeDecision(BaseModel):
    """Output from the Committee Evaluator — the final decision."""
    decision: HiringDecision = Field(description="HIRE, HOLD, or REJECT")
    confidence: float = Field(ge=0, le=1, description="Confidence in this decision (0-1); the agent must assert this explicitly")
    executive_summary: str = Field(description="One-paragraph executive summary")
    round_summaries: list[RoundSummary] = Field(description="Summary of each evaluation round")
    overall_assessment: str = Field(description="Detailed overall assessment")
    recommendation: str = Field(description="Final recommendation with conditions or notes")
    hiring_risks: list[str] = Field(description="Key risks identified across all rounds")
    strengths_summary: list[str] = Field(description="Top strengths across all rounds")
    weaknesses_summary: list[str] = Field(description="Top weaknesses across all rounds")


# ── API Request Models ─────────────────────────────────────────────


class StartRequest(BaseModel):
    resume: str = Field(min_length=1, max_length=20_000, description="Candidate resume text")
    role: str = Field(min_length=1, max_length=200, description="Target role")
    candidate_name: str = Field(default="", max_length=200, description="Candidate name (optional)")


class AnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=10_000, description="Candidate's answer")


# ── Identity & Access Models ───────────────────────────────────────


class RegisterRequest(BaseModel):
    email: NormalizedEmail = Field(description="Account email address")
    # 12 chars is a deliberate floor: composition rules (symbols, mixed case)
    # push users toward predictable substitutions, while length is the factor
    # that actually resists offline cracking. NIST SP 800-63B agrees.
    password: str = Field(min_length=12, max_length=256, description="Password, minimum 12 characters")
    full_name: str = Field(default="", max_length=200)


class RegistrationResponse(BaseModel):
    message: str
    verification_required: bool = False


class AccountEmailRequest(BaseModel):
    email: NormalizedEmail


class AccountTokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class PasswordResetRequest(AccountEmailRequest):
    pass


class PasswordResetConfirmRequest(AccountTokenRequest):
    new_password: str = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Token lifetime in seconds")


class MembershipSummary(BaseModel):
    org_id: int
    org_name: str
    org_slug: str
    role_name: str


class ActorResponse(BaseModel):
    """The authenticated caller's identity, active context, and powers."""
    user_id: int
    email: str
    full_name: str
    is_platform_admin: bool
    email_verified_at: Optional[datetime] = None
    email_verification_required: bool = False
    impersonated_by: Optional[int] = None
    active_org_id: Optional[int] = None
    active_role: Optional[str] = None
    capabilities: list[str] = Field(default_factory=list)
    memberships: list[MembershipSummary] = Field(default_factory=list)


class CreateOrganizationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(
        min_length=2,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$",
        description="URL-safe identifier, lowercase alphanumeric and hyphens",
    )


class OrganizationResponse(BaseModel):
    id: int
    name: str
    slug: str
    plan: str
    status: str


class AddMemberRequest(BaseModel):
    email: NormalizedEmail
    role: str = Field(description="One of the org-scoped system role names")


class SetMemberRoleRequest(BaseModel):
    role: str = Field(description="One of the org-scoped system role names")


class InterviewProfileRequest(BaseModel):
    job_title: str = Field(default="", max_length=120)
    interview_skills: list[str] = Field(default_factory=list, max_length=30)
    timezone: str = Field(default="UTC", min_length=1, max_length=80)
    weekly_capacity: int = Field(default=5, ge=0, le=40)
    available_for_interviews: bool = True


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)



# ── API Response Models ────────────────────────────────────────────


class RoundResponse(BaseModel):
    """Standard response for a round completion."""
    evaluation_id: int
    round: int
    decision: str
    verdict: dict
    verdict_text: str
    status: str
    next_round: Optional[int] = None
    question: Optional[str] = None
    message: Optional[str] = None


class EvaluationSummary(BaseModel):
    """Summary for listing evaluations."""
    id: int
    candidate_name: str
    role: str
    status: str
    current_round: int
    overall_score: Optional[float] = None
    final_decision: Optional[str] = None
    created_at: str
    updated_at: str


class PipelineStage(BaseModel):
    """Status of a single pipeline stage."""
    stage: int
    name: str
    agent: str
    status: str  # "complete" | "active" | "pending" | "failed"
    score: Optional[float] = None
    decision: Optional[str] = None


class PipelineStatus(BaseModel):
    """Full pipeline status for an evaluation."""
    evaluation_id: int
    stages: list[PipelineStage]
    current_stage: int
    overall_status: str


class ReportResponse(BaseModel):
    """Full evaluation report."""
    evaluation_id: int
    candidate_name: str
    role: str
    status: str
    overall_score: Optional[float] = None
    final_decision: Optional[str] = None
    pipeline: list[PipelineStage]
    verdicts: list[dict]
    created_at: str


class DashboardStats(BaseModel):
    """Dashboard statistics."""
    total: int
    completed: int
    in_progress: int
    rejected: int
    hired: int
    hire_rate: float
    avg_score: float
