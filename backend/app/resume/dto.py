"""DTOs: request/response contracts for the resume domain.

These describe what crosses the HTTP boundary, not what is stored — that is
`entity.py`. A parsed field is always a best-effort suggestion the candidate
reviews and edits; nothing here is persisted to the profile until the
candidate explicitly imports it via `ResumeImportRequest`.
"""

from typing import Optional

from pydantic import BaseModel, Field


class ParsedSkill(BaseModel):
    skill: str = Field(min_length=1, max_length=100)
    years: Optional[float] = Field(default=None, ge=0, le=70)


class ParsedWorkExperience(BaseModel):
    company: str = Field(default="", max_length=200)
    title: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=200)
    start_date: str = Field(default="", max_length=10)
    end_date: Optional[str] = Field(default=None, max_length=10)
    is_current: bool = False
    description: str = Field(default="", max_length=5_000)


class ParsedEducation(BaseModel):
    institution: str = Field(default="", max_length=200)
    degree: str = Field(default="", max_length=200)
    field: str = Field(default="", max_length=200)
    start_year: Optional[int] = Field(default=None, ge=1900, le=2100)
    end_year: Optional[int] = Field(default=None, ge=1900, le=2100)


class ParsedProfile(BaseModel):
    headline: str = Field(default="", max_length=200)
    summary: str = Field(default="", max_length=5_000)
    location: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=40)
    work_authorization: str = Field(default="", max_length=200)
    years_experience: Optional[float] = Field(default=None, ge=0, le=70)
    skills: list[ParsedSkill] = Field(default_factory=list, max_length=200)
    work_experiences: list[ParsedWorkExperience] = Field(default_factory=list, max_length=50)
    education: list[ParsedEducation] = Field(default_factory=list, max_length=20)


class ResumeParseResponse(BaseModel):
    resume_document_id: int
    char_count: int
    parsed_by: str  # "llm" | "heuristic"
    raw_text: str
    parsed: ParsedProfile
    warnings: list[str] = Field(default_factory=list)


class ResumeImportRequest(BaseModel):
    """What the candidate confirms after reviewing/editing the parse result.

    Replaces the profile's scalar fields and wholesale-replaces the
    experience/education/skill lists — this is an explicit "apply my resume"
    action, not an incremental edit (those remain the existing granular
    `/me/profile/experience` etc. endpoints).
    """

    headline: str = Field(default="", max_length=200)
    summary: str = Field(default="", max_length=5_000)
    location: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=40)
    work_authorization: str = Field(default="", max_length=200)
    years_experience: Optional[float] = Field(default=None, ge=0, le=70)
    resume_text: str = Field(default="", max_length=20_000)
    skills: list[ParsedSkill] = Field(default_factory=list, max_length=200)
    work_experiences: list[ParsedWorkExperience] = Field(default_factory=list, max_length=50)
    education: list[ParsedEducation] = Field(default_factory=list, max_length=20)
