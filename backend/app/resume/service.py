"""Service: resume text extraction and field parsing.

Extraction (PDF/DOCX/plain text -> raw text) is deterministic and always
succeeds or raises a clear client error. Parsing (raw text -> structured
`ParsedProfile`) prefers the configured LLM and falls back to a heuristic
extractor when the model is unavailable, unreachable, or returns something
we cannot validate — mirroring the pattern used by
`prep_ai.generate_roadmap_plan`. The heuristic never blocks or hangs: it does
regex/keyword matching only.
"""

import json
import logging
import re
from typing import Any, Optional

from fastapi import HTTPException, UploadFile

from app.resume.dto import ParsedEducation, ParsedProfile, ParsedSkill, ParsedWorkExperience
from app.resume.entity import ResumeDocument
from app.resume.repository import ResumeRepository

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

# A short, well-known list used only to *suggest* skills out of free text.
# This is intentionally small and transparent rather than trying to be a
# comprehensive taxonomy; the candidate reviews and edits before saving.
_KNOWN_SKILLS = [
    "python", "java", "javascript", "typescript", "go", "golang", "rust", "c++", "c#",
    "react", "next.js", "node.js", "django", "flask", "fastapi", "spring", "spring boot",
    "sql", "postgresql", "mysql", "mongodb", "redis", "docker", "kubernetes", "aws",
    "azure", "gcp", "terraform", "git", "graphql", "rest", "microservices", "kafka",
    "machine learning", "data science", "pandas", "numpy", "tensorflow", "pytorch",
]

_PHONE_RE = re.compile(r"\+?\d[\d\-\s()]{8,}\d")
_YEARS_EXPERIENCE_RE = re.compile(r"(\d{1,2})\+?\s?years? of experience")


class UnsupportedFileTypeError(Exception):
    pass


class ResumeParsingService:
    def __init__(self, repository: Optional[ResumeRepository] = None):
        self._repository = repository or ResumeRepository()

    async def extract_text(self, upload: UploadFile) -> tuple[str, str]:
        """Read the upload and return (raw_text, content_type). Raises
        HTTPException for oversized/unsupported/empty files."""
        filename = upload.filename or "resume"
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Only PDF, DOCX, or TXT resumes are supported.")

        body = await upload.read()
        if len(body) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail="Resume file is too large (max 5 MB).")
        if not body:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")

        try:
            if ext == ".pdf":
                text = self._extract_pdf(body)
            elif ext == ".docx":
                text = self._extract_docx(body)
            else:
                text = body.decode("utf-8", errors="ignore")
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Resume text extraction failed for %s: %s", filename, exc)
            raise HTTPException(status_code=422, detail="Could not read this file. Try a different PDF/DOCX/TXT export.")

        text = text.strip()
        if not text:
            raise HTTPException(status_code=422, detail="No readable text was found in this file.")
        return text, upload.content_type or "application/octet-stream"

    @staticmethod
    def _extract_pdf(body: bytes) -> str:
        from io import BytesIO

        from pypdf import PdfReader

        reader = PdfReader(BytesIO(body))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    @staticmethod
    def _extract_docx(body: bytes) -> str:
        from io import BytesIO

        from docx import Document

        document = Document(BytesIO(body))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)

    def parse(self, raw_text: str) -> tuple[ParsedProfile, str]:
        """Return (parsed_profile, parsed_by) where parsed_by is 'llm' or 'heuristic'."""
        try:
            parsed = self._parse_with_llm(raw_text)
            if parsed is not None:
                return parsed, "llm"
        except Exception as exc:
            logger.warning("Resume LLM parsing unavailable; using heuristic parser: %s", exc)
        return self._parse_heuristically(raw_text), "heuristic"

    def _parse_with_llm(self, raw_text: str) -> Optional[ParsedProfile]:
        from crewai import Agent, Crew, Task

        from app.evaluation.agents import LLM_MODEL

        agent = Agent(
            role="Resume Information Extractor",
            goal="Extract structured candidate profile fields from raw resume text without inventing facts.",
            backstory="You carefully extract only what is stated in the resume text. You never fabricate dates, employers, or skills.",
            llm=LLM_MODEL,
            verbose=False,
            allow_delegation=False,
        )
        task = Task(
            description=(
                "Extract structured fields from this resume text:\n"
                f"{raw_text[:12_000]}\n\n"
                "Return ONLY JSON with keys: headline, summary, location, phone, work_authorization, "
                "years_experience (number or null), "
                "skills (array of {skill, years}), "
                "work_experiences (array of {company, title, location, start_date, end_date, is_current, description}), "
                "education (array of {institution, degree, field, start_year, end_year}). "
                "Use empty string/null/empty array for anything not present. Dates as YYYY-MM or YYYY."
            ),
            expected_output="A single valid JSON object with the requested keys.",
            agent=agent,
        )
        raw = str(Crew(agents=[agent], tasks=[task], verbose=False).kickoff())
        data = self._extract_json(raw)
        return ParsedProfile.model_validate(data)

    @staticmethod
    def _extract_json(raw: str) -> dict[str, Any]:
        candidate = raw.strip()
        if "```" in candidate:
            candidate = re.sub(r"```(?:json)?", "", candidate, flags=re.IGNORECASE).replace("```", "").strip()
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("The extractor did not return a JSON object.")
        value = json.loads(candidate[start : end + 1])
        if not isinstance(value, dict):
            raise ValueError("The extractor returned an invalid JSON object.")
        return value

    def _parse_heuristically(self, raw_text: str) -> ParsedProfile:
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        lowered = raw_text.lower()

        return ParsedProfile(
            headline=self._guess_headline(lines)[:200],
            summary=self._guess_summary(lines),
            location="",
            phone=self._guess_phone(raw_text)[:40],
            work_authorization="",
            years_experience=self._guess_years_experience(lowered),
            skills=[ParsedSkill(skill=skill) for skill in _KNOWN_SKILLS if skill in lowered],
            work_experiences=[],
            education=[],
        )

    @staticmethod
    def _guess_phone(raw_text: str) -> str:
        match = _PHONE_RE.search(raw_text)
        return match.group(0).strip() if match else ""

    @staticmethod
    def _guess_headline(lines: list[str]) -> str:
        for line in lines[:5]:
            if "@" in line or _PHONE_RE.search(line):
                continue
            if len(line) < 100:
                return line
        return ""

    @staticmethod
    def _guess_years_experience(lowered: str) -> Optional[float]:
        match = _YEARS_EXPERIENCE_RE.search(lowered)
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def _guess_summary(lines: list[str]) -> str:
        summary_lines = []
        for line in lines:
            if len(line) > 60:
                summary_lines.append(line)
            if len(summary_lines) >= 2:
                break
        return " ".join(summary_lines)[:1_000]


class ResumeService:
    def __init__(self, repository: Optional[ResumeRepository] = None):
        self._repository = repository or ResumeRepository()
        self._parsing = ResumeParsingService(self._repository)

    async def upload_and_parse(self, user_id: int, upload: UploadFile) -> tuple[ResumeDocument, ParsedProfile, str]:
        raw_text, content_type = await self._parsing.extract_text(upload)
        parsed, parsed_by = self._parsing.parse(raw_text)
        document = self._repository.save(
            user_id=user_id,
            filename=upload.filename or "resume",
            content_type=content_type,
            raw_text=raw_text,
            parsed_by=parsed_by,
        )
        return document, parsed, parsed_by
