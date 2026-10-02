"""Repository: persistence for resume_documents.

Uses the shared connection primitives from `database.py` directly (same
convention as the existing `hiring_db.py` / `candidate_db.py` modules) rather
than introducing a second database abstraction.
"""

from typing import Optional

from app.config.database import USE_POSTGRES, _get_conn, _ph, _row_to_dict

from app.resume.entity import ResumeDocument


class ResumeRepository:
    def save(
        self,
        user_id: int,
        filename: str,
        content_type: str,
        raw_text: str,
        parsed_by: str,
    ) -> ResumeDocument:
        p = _ph()
        with _get_conn() as (conn, cur):
            columns = "user_id, filename, content_type, raw_text, char_count, parsed_by"
            values = (user_id, filename, content_type, raw_text, len(raw_text), parsed_by)
            placeholders = ", ".join([p] * 6)
            if USE_POSTGRES:
                cur.execute(
                    f"INSERT INTO resume_documents ({columns}) VALUES ({placeholders}) RETURNING id",
                    values,
                )
                new_id = cur.fetchone()["id"]
            else:
                cur.execute(
                    f"INSERT INTO resume_documents ({columns}) VALUES ({placeholders})",
                    values,
                )
                new_id = cur.lastrowid
            cur.execute(f"SELECT * FROM resume_documents WHERE id = {p}", (new_id,))
            row = _row_to_dict(cur.fetchone())
        document = ResumeDocument.from_row(row)
        assert document is not None
        return document


    def get(self, resume_document_id: int, user_id: int) -> Optional[ResumeDocument]:
        p = _ph()
        with _get_conn() as (conn, cur):
            cur.execute(
                f"SELECT * FROM resume_documents WHERE id = {p} AND user_id = {p}",
                (resume_document_id, user_id),
            )
            row = _row_to_dict(cur.fetchone())
        return ResumeDocument.from_row(row)
