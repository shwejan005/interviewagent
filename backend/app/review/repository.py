"""Persistence helpers for evidence review and benchmark replay."""

import json
from typing import Optional

from app.config.database import USE_POSTGRES, _get_conn, _ph, _row_to_dict


def seed_rubrics() -> None:
    p = _ph()
    definition = {
        "criteria": [
            {"id": "evidence", "label": "Evidence grounded", "description": "Claims are tied to the supplied answer or resume evidence."},
            {"id": "correctness", "label": "Technically correct", "description": "The assessment does not accept plausible but incorrect reasoning."},
            {"id": "uncertainty", "label": "Uncertainty handled", "description": "Insufficient evidence is surfaced for human review."},
        ],
        "forbidden_inferences": ["protected characteristics", "emotion", "honesty", "culture fit proxies"],
    }
    with _get_conn() as (conn, cur):
        cur.execute(
            f"INSERT INTO rubric_versions (role, version, definition_json) VALUES ({p}, {p}, {p}) ON CONFLICT (role, version) DO NOTHING",
            ("backend-engineer", "backend-v1", json.dumps(definition, separators=(",", ":"))),
        )
        cases = (
            ("invalid-json-screening", "screening", {"raw_output": "not json"}, [{"rule_id": "contract.json_object", "passed": False}], "development"),
            ("missing-confidence-screening", "screening", {"raw_output": '{"decision":"PASS","score":8}'}, [{"rule_id": "contract.schema", "passed": False}], "development"),
        )
        for case_id, stage, input_data, expected_rules, split in cases:
            cur.execute(
                f"INSERT INTO benchmark_cases (case_id, stage, input_json, expected_rules_json, split, provenance) VALUES ({p}, {p}, {p}, {p}, {p}, {p}) ON CONFLICT (case_id) DO NOTHING",
                (case_id, stage, json.dumps(input_data), json.dumps(expected_rules), split, "synthetic-contract-fixture"),
            )


def list_review_actions(evaluation_id: int) -> list[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT id, evaluation_id, actor_user_id, action, note, correction_json, rubric_version, created_at FROM review_actions WHERE evaluation_id = {p} ORDER BY created_at, id",
            (evaluation_id,),
        )
        rows = [_row_to_dict(row) for row in cur.fetchall()]
    for row in rows:
        row["correction_json"] = json.loads(row["correction_json"] or "{}")
    return rows


def record_review_action(evaluation_id: int, actor_user_id: int, action: str, note: str, correction: dict, rubric_version: str = "backend-v1") -> dict:
    p = _ph()
    with _get_conn() as (conn, cur):
        values = (evaluation_id, actor_user_id, action, note, json.dumps(correction or {}, separators=(",", ":")), rubric_version)
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO review_actions (evaluation_id, actor_user_id, action, note, correction_json, rubric_version) VALUES ({', '.join([p] * len(values))}) RETURNING *",
                values,
            )
        else:
            cur.execute(
                f"INSERT INTO review_actions (evaluation_id, actor_user_id, action, note, correction_json, rubric_version) VALUES ({', '.join([p] * len(values))})",
                values,
            )
            cur.execute("SELECT * FROM review_actions WHERE id = last_insert_rowid()")
        row = _row_to_dict(cur.fetchone())
    row["correction_json"] = json.loads(row["correction_json"] or "{}")
    return row


def list_benchmark_cases(split: Optional[str] = None) -> list[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        if split:
            cur.execute(f"SELECT * FROM benchmark_cases WHERE split = {p} ORDER BY case_id", (split,))
        else:
            cur.execute("SELECT * FROM benchmark_cases ORDER BY case_id")
        rows = [_row_to_dict(row) for row in cur.fetchall()]
    for row in rows:
        row["input_json"] = json.loads(row["input_json"])
        row["expected_rules_json"] = json.loads(row["expected_rules_json"] or "[]")
    return rows


def record_benchmark_run(case_id: str, harness_version: str, passed: bool, report: dict) -> dict:
    p = _ph()
    with _get_conn() as (conn, cur):
        values = (case_id, harness_version, passed, json.dumps(report, separators=(",", ":")))
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO benchmark_runs (case_id, harness_version, passed, report_json) VALUES ({', '.join([p] * len(values))}) RETURNING *",
                values,
            )
        else:
            cur.execute(
                f"INSERT INTO benchmark_runs (case_id, harness_version, passed, report_json) VALUES ({', '.join([p] * len(values))})",
                values,
            )
            cur.execute("SELECT * FROM benchmark_runs WHERE id = last_insert_rowid()")
        row = _row_to_dict(cur.fetchone())
    row["report_json"] = json.loads(row["report_json"] or "{}")
    return row
