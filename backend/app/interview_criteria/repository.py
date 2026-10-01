"""Repository: persistence for posting_evaluation_criteria and
application_interview_reports, using the shared connection primitives from
database.py (same convention as hiring_db.py / candidate_db.py)."""

import json
from typing import Optional

from app.config.database import USE_POSTGRES, _get_conn, _ph, _row_to_dict

from app.interview_criteria.entity import ApplicationReport, PostingCriteria


class CriteriaRepository:
    def get(self, posting_id: int) -> Optional[PostingCriteria]:
        p = _ph()
        with _get_conn() as (conn, cur):
            cur.execute(
                f"SELECT * FROM posting_evaluation_criteria WHERE posting_id = {p}",
                (posting_id,),
            )
            row = _row_to_dict(cur.fetchone())
        return PostingCriteria.from_row(row)

    def upsert(
        self,
        posting_id: int,
        org_id: int,
        competencies: list[dict],
        custom_questions: list[str],
        pass_threshold: float,
        interview_settings: dict,
        updated_by: int,
    ) -> PostingCriteria:
        p = _ph()
        competencies_json = json.dumps(competencies)
        questions_json = json.dumps(custom_questions)
        settings_json = json.dumps(interview_settings)
        with _get_conn() as (conn, cur):
            if not USE_POSTGRES:
                conn.execute("BEGIN IMMEDIATE")
            posting_lock = " FOR UPDATE" if USE_POSTGRES else ""
            cur.execute(
                f"SELECT id FROM job_postings WHERE id = {p} AND org_id = {p} AND deleted_at IS NULL{posting_lock}",
                (posting_id, org_id),
            )
            if cur.fetchone() is None:
                raise LookupError("Posting not found")
            cur.execute(
                f"SELECT rubric_version FROM posting_evaluation_criteria WHERE posting_id = {p}{posting_lock}",
                (posting_id,),
            )
            existing = cur.fetchone()
            if existing is None:
                next_version = 1
            else:
                current = str(existing["rubric_version"] or "posting-v0")
                try:
                    next_version = int(current.rsplit("v", 1)[1]) + 1
                except (IndexError, ValueError):
                    next_version = 2
            rubric_version = f"posting-v{next_version}"
            if USE_POSTGRES:
                cur.execute(
                    f"""
                    INSERT INTO posting_evaluation_criteria
                        (posting_id, org_id, competencies_json, custom_questions_json, pass_threshold,
                         interview_settings_json, rubric_version, updated_by, updated_at)
                    VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, CURRENT_TIMESTAMP)
                    ON CONFLICT (posting_id) DO UPDATE SET
                        competencies_json = EXCLUDED.competencies_json,
                        custom_questions_json = EXCLUDED.custom_questions_json,
                        pass_threshold = EXCLUDED.pass_threshold,
                        interview_settings_json = EXCLUDED.interview_settings_json,
                        rubric_version = EXCLUDED.rubric_version,
                        updated_by = EXCLUDED.updated_by,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (posting_id, org_id, competencies_json, questions_json, pass_threshold,
                     settings_json, rubric_version, updated_by),
                )
            else:
                cur.execute(
                    f"""
                    INSERT INTO posting_evaluation_criteria
                        (posting_id, org_id, competencies_json, custom_questions_json, pass_threshold,
                         interview_settings_json, rubric_version, updated_by, updated_at)
                    VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, datetime('now'))
                    ON CONFLICT (posting_id) DO UPDATE SET
                        competencies_json = excluded.competencies_json,
                        custom_questions_json = excluded.custom_questions_json,
                        pass_threshold = excluded.pass_threshold,
                        interview_settings_json = excluded.interview_settings_json,
                        rubric_version = excluded.rubric_version,
                        updated_by = excluded.updated_by,
                        updated_at = datetime('now')
                    """,
                    (posting_id, org_id, competencies_json, questions_json, pass_threshold,
                     settings_json, rubric_version, updated_by),
                )
            cur.execute(
                f"SELECT * FROM posting_evaluation_criteria WHERE posting_id = {p}",
                (posting_id,),
            )
            row = _row_to_dict(cur.fetchone())
        criteria = PostingCriteria.from_row(row)
        assert criteria is not None
        return criteria


class ReportRepository:
    def get_by_application(self, application_id: int) -> Optional[ApplicationReport]:
        p = _ph()
        with _get_conn() as (conn, cur):
            cur.execute(
                f"SELECT * FROM application_interview_reports WHERE application_id = {p}",
                (application_id,),
            )
            row = _row_to_dict(cur.fetchone())
        return ApplicationReport.from_row(row)

    def upsert(
        self,
        application_id: int,
        evaluation_id: int,
        posting_id: int,
        org_id: int,
        competency_scores: list[dict],
        overall_weighted_score: Optional[float],
        recommendation: str,
        rubric_version: str,
        interview_details: Optional[dict] = None,
    ) -> ApplicationReport:
        p = _ph()
        scores_json = json.dumps(competency_scores)
        details_json = json.dumps(interview_details or {})
        with _get_conn() as (conn, cur):
            if USE_POSTGRES:
                cur.execute(
                    f"""
                    INSERT INTO application_interview_reports
                        (application_id, evaluation_id, posting_id, org_id, competency_scores_json,
                            overall_weighted_score, recommendation, rubric_version, interview_details_json, generated_at)
                        VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, CURRENT_TIMESTAMP)
                    ON CONFLICT (application_id) DO UPDATE SET
                        evaluation_id = EXCLUDED.evaluation_id,
                        competency_scores_json = EXCLUDED.competency_scores_json,
                        overall_weighted_score = EXCLUDED.overall_weighted_score,
                        recommendation = EXCLUDED.recommendation,
                        rubric_version = EXCLUDED.rubric_version,
                                interview_details_json = EXCLUDED.interview_details_json,
                        generated_at = CURRENT_TIMESTAMP
                    """,
                    (application_id, evaluation_id, posting_id, org_id, scores_json,
                            overall_weighted_score, recommendation, rubric_version, details_json),
                )
            else:
                cur.execute(
                    f"""
                    INSERT INTO application_interview_reports
                        (application_id, evaluation_id, posting_id, org_id, competency_scores_json,
                            overall_weighted_score, recommendation, rubric_version, interview_details_json, generated_at)
                        VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, datetime('now'))
                    ON CONFLICT (application_id) DO UPDATE SET
                        evaluation_id = excluded.evaluation_id,
                        competency_scores_json = excluded.competency_scores_json,
                        overall_weighted_score = excluded.overall_weighted_score,
                        recommendation = excluded.recommendation,
                        rubric_version = excluded.rubric_version,
                                interview_details_json = excluded.interview_details_json,
                        generated_at = datetime('now')
                    """,
                    (application_id, evaluation_id, posting_id, org_id, scores_json,
                            overall_weighted_score, recommendation, rubric_version, details_json),
                )
            cur.execute(
                f"SELECT * FROM application_interview_reports WHERE application_id = {p}",
                (application_id,),
            )
            row = _row_to_dict(cur.fetchone())
        report = ApplicationReport.from_row(row)
        assert report is not None
        return report
