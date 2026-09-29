"""Request models for the text-first preparation suite."""

from typing import Optional

from pydantic import BaseModel, Field


class RoadmapCreateRequest(BaseModel):
    target_role: str = Field(min_length=1, max_length=200)
    title: Optional[str] = Field(default=None, max_length=200)
    target_date: Optional[str] = Field(default=None, max_length=40)
    topic_slugs: list[str] = Field(default_factory=list, max_length=30)


class ProblemSubmissionRequest(BaseModel):
    answer_text: str = Field(min_length=1, max_length=20_000)
