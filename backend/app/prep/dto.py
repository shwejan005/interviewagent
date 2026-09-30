"""Request models for the text-first preparation suite."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class RoadmapCreateRequest(BaseModel):
    target_role: str = Field(min_length=1, max_length=200)
    title: Optional[str] = Field(default=None, max_length=200)
    target_date: Optional[str] = Field(default=None, max_length=40)
    topic_slugs: list[str] = Field(default_factory=list, max_length=30)


class PrepGoalRequest(BaseModel):
    target_role: str = Field(default="Software Engineer", min_length=1, max_length=200)
    target_date: Optional[str] = Field(default=None, max_length=40)
    daily_minutes: int = Field(default=45, ge=15, le=480)
    days_per_week: int = Field(default=5, ge=1, le=7)
    current_level: Literal["BEGINNER", "INTERMEDIATE", "ADVANCED"] = "BEGINNER"
    preferred_languages: list[str] = Field(default_factory=lambda: ["python"], max_length=5)
    focus_topics: list[str] = Field(default_factory=list, max_length=10)
    notes: str = Field(default="", max_length=2_000)


class GeneratedProblemRequest(BaseModel):
    topic_slug: str = Field(min_length=1, max_length=100)
    difficulty: Literal["EASY", "MEDIUM", "HARD"] = "MEDIUM"
    language: Literal["python", "javascript", "typescript"] = "python"


class ProblemSubmissionRequest(BaseModel):
    answer_text: str = Field(min_length=1, max_length=20_000)


class CodeExecutionRequest(BaseModel):
    language: Literal["python", "javascript", "typescript", "java", "cpp"]
    source_code: str = Field(min_length=1, max_length=20_000)
    stdin: str = Field(default="", max_length=5_000)
    expected_output: Optional[str] = Field(default=None, max_length=5_000)
    problem_id: Optional[int] = Field(default=None, ge=1)
    test_case_id: Optional[int] = Field(default=None, ge=1)
    mode: Literal["run", "submit"] = "run"
