"""Entity: the persisted shape of a resume upload.

A thin, typed mirror of the `resume_documents` row. Kept separate from the
DTOs in dto.py, which represent what a client sends/receives rather than
what is stored.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ResumeDocument:
    id: int
    user_id: int
    filename: str
    content_type: str
    raw_text: str
    char_count: int
    parsed_by: str
    created_at: str

    @staticmethod
    def from_row(row: Optional[dict]) -> Optional["ResumeDocument"]:
        if row is None:
            return None
        return ResumeDocument(
            id=row["id"],
            user_id=row["user_id"],
            filename=row["filename"],
            content_type=row["content_type"],
            raw_text=row["raw_text"],
            char_count=row["char_count"],
            parsed_by=row["parsed_by"],
            created_at=str(row["created_at"]),
        )
