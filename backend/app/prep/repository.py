"""Repository for the safe, text-first preparation suite."""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.config.database import USE_POSTGRES, _get_conn, _ph, _row_to_dict
from app.prep.catalog import PROBLEM_SEED, TOPIC_SEED


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_topic(cur, p: str, topic: tuple) -> int:
    slug, name, description, difficulty, prerequisites = topic
    cur.execute(f"SELECT id FROM prep_topics WHERE slug = {p}", (slug,))
    row = cur.fetchone()
    if row is not None:
        return row["id"]
    values = (slug, name, description, difficulty, json.dumps(prerequisites))
    if USE_POSTGRES:
        cur.execute(
            f"INSERT INTO prep_topics (slug, name, description, difficulty, prerequisites) VALUES ({', '.join([p] * len(values))}) RETURNING id",
            values,
        )
        return cur.fetchone()["id"]
    cur.execute(
        f"INSERT INTO prep_topics (slug, name, description, difficulty, prerequisites) VALUES ({', '.join([p] * len(values))})",
        values,
    )
    return cur.lastrowid


def _seed_problem(cur, p: str, topic_ids: dict[str, int], problem: dict) -> None:
    slug = problem["slug"]
    values = (
        topic_ids[problem["topic_slug"]], slug, problem["title"], problem["prompt"],
        problem["difficulty"], problem["estimated_minutes"], json.dumps(problem["expected_concepts"]),
        json.dumps(problem["constraints"]), problem["hint"], json.dumps(problem["starter_code"]),
        json.dumps(problem["harnesses"]),
    )
    cur.execute(f"SELECT id FROM prep_problems WHERE slug = {p}", (slug,))
    row = cur.fetchone()
    if row is None:
        cur.execute(
            f"INSERT INTO prep_problems (topic_id, slug, title, prompt, difficulty, estimated_minutes, expected_concepts, constraints, hint, starter_code, harnesses) VALUES ({', '.join([p] * len(values))})",
            values,
        )
        if USE_POSTGRES:
            cur.execute(f"SELECT id FROM prep_problems WHERE slug = {p}", (slug,))
            problem_id = cur.fetchone()["id"]
        else:
            problem_id = cur.lastrowid
    else:
        problem_id = row["id"]
        cur.execute(
            f"UPDATE prep_problems SET topic_id = {p}, title = {p}, prompt = {p}, difficulty = {p}, estimated_minutes = {p}, expected_concepts = {p}, constraints = {p}, hint = {p}, starter_code = {p}, harnesses = {p} WHERE id = {p}",
            (values[0], values[2], values[3], values[4], values[5], values[6], values[7], values[8], values[9], values[10], problem_id),
        )
    cur.execute(f"SELECT id FROM prep_problem_test_cases WHERE problem_id = {p}", (problem_id,))
    if cur.fetchone() is not None:
        return
    for position, test_case in enumerate(problem["test_cases"], start=1):
        cur.execute(
            f"INSERT INTO prep_problem_test_cases (problem_id, title, input_json, expected_output, explanation, is_hidden, position) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p})",
            (problem_id, test_case["title"], json.dumps(test_case["input"], separators=(",", ":")), test_case["expected_output"], test_case.get("explanation", ""), test_case.get("is_hidden", False), position),
        )


def seed_catalog() -> None:
    """Insert the reviewed DSA catalog and remove retired topics."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(f"DELETE FROM prep_topics WHERE slug = {p}", ("system-design",))
        topic_ids = {topic[0]: _seed_topic(cur, p, topic) for topic in TOPIC_SEED}
        for problem in PROBLEM_SEED:
            _seed_problem(cur, p, topic_ids, problem)


def _decode(row: Optional[dict], fields: tuple[str, ...] = ()) -> Optional[dict]:
    if row is None:
        return None
    for field in fields:
        if isinstance(row.get(field), str):
            row[field] = json.loads(row[field])
    return row


def _load_test_cases(cur, problem_ids: list[int], *, include_hidden: bool = False) -> dict[int, list[dict]]:
    if not problem_ids:
        return {}
    p = _ph()
    placeholders = ", ".join([p] * len(problem_ids))
    hidden_clause = ""
    if not include_hidden:
        hidden_value = "TRUE" if USE_POSTGRES else "0"
        hidden_clause = f" AND is_hidden = {hidden_value}"
    cur.execute(
        f"SELECT id, problem_id, title, input_json, expected_output, explanation, is_hidden, position FROM prep_problem_test_cases WHERE problem_id IN ({placeholders}){hidden_clause} ORDER BY problem_id, position",
        tuple(problem_ids),
    )
    cases: dict[int, list[dict]] = {problem_id: [] for problem_id in problem_ids}
    for row in cur.fetchall():
        item = _row_to_dict(row)
        item["input"] = json.loads(item.pop("input_json"))
        item["is_hidden"] = bool(item["is_hidden"])
        cases[item["problem_id"]].append(item)
    return cases


def list_topics() -> list[dict]:
    with _get_conn() as (conn, cur):
        cur.execute("SELECT * FROM prep_topics ORDER BY id")
        rows = [_row_to_dict(row) for row in cur.fetchall()]
    return [_decode(row, ("prerequisites",)) for row in rows]


def list_problems(topic_slug: Optional[str] = None, difficulty: Optional[str] = None) -> list[dict]:
    p = _ph()
    clauses = []
    params: list = []
    if topic_slug:
        clauses.append(f"t.slug = {p}")
        params.append(topic_slug)
    if difficulty:
        clauses.append(f"p.difficulty = {p}")
        params.append(difficulty)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT p.id, p.slug, p.title, p.prompt, p.difficulty, p.estimated_minutes, "
            f"p.expected_concepts, p.constraints, p.hint, p.starter_code, p.harnesses, "
            f"t.slug AS topic_slug, t.name AS topic_name "
            f"FROM prep_problems p JOIN prep_topics t ON t.id = p.topic_id {where} ORDER BY p.id",
            tuple(params),
        )
        rows = [_row_to_dict(row) for row in cur.fetchall()]
        problem_ids = [row["id"] for row in rows]
        cases = _load_test_cases(cur, problem_ids)
    decoded = [_decode(row, ("expected_concepts", "constraints", "starter_code", "harnesses")) for row in rows]
    for row in decoded:
        row["test_cases"] = cases.get(row["id"], [])
        row["available_languages"] = sorted(row.get("harnesses", {}).keys())
        row.pop("harnesses", None)
    return decoded


def get_problem(problem_id: int) -> Optional[dict]:
    problems = list_problems()
    return next((problem for problem in problems if problem["id"] == problem_id), None)


def get_problem_for_execution(problem_id: int) -> Optional[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT p.*, t.slug AS topic_slug, t.name AS topic_name FROM prep_problems p JOIN prep_topics t ON t.id = p.topic_id WHERE p.id = {p}",
            (problem_id,),
        )
        row = _decode(_row_to_dict(cur.fetchone()), ("expected_concepts", "constraints", "starter_code", "harnesses"))
        if row is None:
            return None
        row["test_cases"] = _load_test_cases(cur, [problem_id], include_hidden=True).get(problem_id, [])
        return row


def create_generated_problem(problem: dict) -> dict:
    p = _ph()
    slug = f"generated-{uuid.uuid4().hex[:12]}"
    with _get_conn() as (conn, cur):
        cur.execute(f"SELECT id FROM prep_topics WHERE slug = {p}", (problem["topic_slug"],))
        topic = cur.fetchone()
        if topic is None:
            raise ValueError("The generated problem topic does not exist.")
        values = (
            topic["id"], slug, problem["title"], problem["prompt"], problem["difficulty"],
            int(problem.get("estimated_minutes", 35)), json.dumps(problem.get("expected_concepts", [])),
            json.dumps(problem.get("constraints", [])), problem.get("hint", ""),
            json.dumps(problem.get("starter_code", {})), json.dumps(problem.get("harnesses", {})),
        )
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO prep_problems (topic_id, slug, title, prompt, difficulty, estimated_minutes, expected_concepts, constraints, hint, starter_code, harnesses) VALUES ({', '.join([p] * len(values))}) RETURNING id",
                values,
            )
            problem_id = cur.fetchone()["id"]
        else:
            cur.execute(
                f"INSERT INTO prep_problems (topic_id, slug, title, prompt, difficulty, estimated_minutes, expected_concepts, constraints, hint, starter_code, harnesses) VALUES ({', '.join([p] * len(values))})",
                values,
            )
            problem_id = cur.lastrowid
        for position, test_case in enumerate(problem.get("test_cases", []), start=1):
            cur.execute(
                f"INSERT INTO prep_problem_test_cases (problem_id, title, input_json, expected_output, explanation, is_hidden, position) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p})",
                (problem_id, test_case.get("title", f"Case {position}"), json.dumps(test_case["input"], separators=(",", ":")), test_case["expected_output"], test_case.get("explanation", ""), bool(test_case.get("is_hidden", False)), position),
            )
    return get_problem(problem_id) or {"id": problem_id, "slug": slug}


def create_roadmap(user_id: int, request: dict) -> dict:
    p = _ph()
    requested = request.get("topic_slugs") or []
    with _get_conn() as (conn, cur):
        cur.execute("SELECT id, slug FROM prep_topics ORDER BY id")
        topics = [_row_to_dict(row) for row in cur.fetchall()]
        if requested:
            selected = [topic for topic in topics if topic["slug"] in requested]
        else:
            selected = topics
        if not selected:
            raise ValueError("At least one known topic is required")
        title = request.get("title") or f"{request['target_role']} preparation roadmap"
        values = (
            user_id, title, request["target_role"], request.get("target_date"), request.get("goal_id"),
            request.get("summary", ""), request.get("generated_by", "heuristic"),
            request.get("daily_minutes", 45), request.get("weekly_hours", 5),
        )
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO prep_roadmaps (user_id, title, target_role, target_date, goal_id, summary, generated_by, daily_minutes, weekly_hours) "
                f"VALUES ({', '.join([p] * len(values))}) RETURNING id",
                values,
            )
            roadmap_id = cur.fetchone()["id"]
        else:
            cur.execute(
                f"INSERT INTO prep_roadmaps (user_id, title, target_role, target_date, goal_id, summary, generated_by, daily_minutes, weekly_hours) "
                f"VALUES ({', '.join([p] * len(values))})",
                values,
            )
            roadmap_id = cur.lastrowid
        for position, topic in enumerate(selected, start=1):
            cur.execute(
                f"INSERT INTO prep_roadmap_nodes (roadmap_id, topic_id, position, item_type, estimated_minutes) VALUES ({p}, {p}, {p}, {p}, {p})",
                (roadmap_id, topic["id"], position, "TOPIC", request.get("daily_minutes", 45)),
            )
    return get_roadmap(roadmap_id, user_id)


def list_roadmaps(user_id: int) -> list[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT * FROM prep_roadmaps WHERE user_id = {p} ORDER BY updated_at DESC",
            (user_id,),
        )
        return [_row_to_dict(row) for row in cur.fetchall()]


def get_roadmap(roadmap_id: int, user_id: int) -> Optional[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT r.*, n.id AS node_id, n.topic_id, n.problem_id, n.position, n.item_type, n.estimated_minutes, n.rationale, n.status AS node_status, "
            f"n.completed_at, t.slug AS topic_slug, t.name AS topic_name, t.description "
            f"FROM prep_roadmaps r JOIN prep_roadmap_nodes n ON n.roadmap_id = r.id "
            f"JOIN prep_topics t ON t.id = n.topic_id "
            f"WHERE r.id = {p} AND r.user_id = {p} ORDER BY n.position",
            (roadmap_id, user_id),
        )
        rows = [_row_to_dict(row) for row in cur.fetchall()]
    if not rows:
        return None
    roadmap = {key: rows[0][key] for key in ("id", "user_id", "title", "target_role", "target_date", "goal_id", "summary", "generated_by", "daily_minutes", "weekly_hours", "status", "created_at", "updated_at")}
    roadmap["nodes"] = [
        {
            "id": row["node_id"],
            "topic_id": row["topic_id"],
            "problem_id": row["problem_id"],
            "position": row["position"],
            "item_type": row["item_type"],
            "estimated_minutes": row["estimated_minutes"],
            "rationale": row["rationale"],
            "status": row["node_status"],
            "completed_at": row["completed_at"],
            "topic_slug": row["topic_slug"],
            "topic_name": row["topic_name"],
            "description": row["description"],
        }
        for row in rows
    ]
    return roadmap


def complete_node(roadmap_id: int, node_id: int, user_id: int) -> Optional[dict]:
    p = _ph()
    now = _now()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT n.topic_id FROM prep_roadmap_nodes n JOIN prep_roadmaps r ON r.id = n.roadmap_id "
            f"WHERE n.id = {p} AND n.roadmap_id = {p} AND r.user_id = {p}",
            (node_id, roadmap_id, user_id),
        )
        if cur.fetchone() is None:
            return None
        cur.execute(
            f"UPDATE prep_roadmap_nodes SET status = 'COMPLETE', completed_at = {p} "
            f"WHERE id = {p} AND status <> 'COMPLETE'",
            (now, node_id),
        )
        changed = cur.rowcount == 1
        cur.execute(
            f"UPDATE prep_roadmaps SET updated_at = {p} WHERE id = {p}",
            (now, roadmap_id),
        )
        if changed:
            _award_xp(cur, p, user_id, 10, "roadmap_node_completed", node_id)
    return get_roadmap(roadmap_id, user_id)


def submit_problem(user_id: int, problem_id: int, answer_text: str) -> Optional[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(f"SELECT id FROM prep_problems WHERE id = {p}", (problem_id,))
        if cur.fetchone() is None:
            return None
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO prep_submissions (user_id, problem_id, answer_text) "
                f"VALUES ({p}, {p}, {p}) RETURNING id, created_at",
                (user_id, problem_id, answer_text),
            )
            row = _row_to_dict(cur.fetchone())
        else:
            cur.execute(
                f"INSERT INTO prep_submissions (user_id, problem_id, answer_text) VALUES ({p}, {p}, {p})",
                (user_id, problem_id, answer_text),
            )
            row = {"id": cur.lastrowid, "created_at": _now()}
        _award_xp(cur, p, user_id, 5, "problem_submitted", row["id"])
    return {"id": row["id"], "problem_id": problem_id, "status": "SUBMITTED", "verified": False, "created_at": str(row["created_at"])}


def _award_xp(cur, p: str, user_id: int, points: int, event_type: str, reference_id: int) -> None:
    now = _now()
    if USE_POSTGRES:
        cur.execute(
            f"INSERT INTO prep_gamification (user_id, xp, last_activity_at, updated_at) "
            f"VALUES ({p}, {p}, {p}, {p}) ON CONFLICT (user_id) DO UPDATE SET "
            f"xp = prep_gamification.xp + EXCLUDED.xp, last_activity_at = EXCLUDED.last_activity_at, "
            f"updated_at = EXCLUDED.updated_at",
            (user_id, points, now, now),
        )
    else:
        cur.execute(
            f"INSERT OR IGNORE INTO prep_gamification (user_id, xp, last_activity_at, updated_at) VALUES ({p}, 0, {p}, {p})",
            (user_id, now, now),
        )
        cur.execute(
            f"UPDATE prep_gamification SET xp = xp + {p}, last_activity_at = {p}, updated_at = {p} WHERE user_id = {p}",
            (points, now, now, user_id),
        )
    cur.execute(
        f"INSERT INTO prep_xp_events (user_id, event_type, points, reference_type, reference_id) "
        f"VALUES ({p}, {p}, {p}, {p}, {p})",
        (user_id, event_type, points, "prep", reference_id),
    )


def get_gamification(user_id: int) -> dict:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT user_id, xp, streak_days, last_activity_at, updated_at "
            f"FROM prep_gamification WHERE user_id = {p}",
            (user_id,),
        )
        row = _row_to_dict(cur.fetchone())
    return row or {"user_id": user_id, "xp": 0, "streak_days": 0, "last_activity_at": None, "updated_at": None}


def upsert_goal(user_id: int, request: dict) -> dict:
    p = _ph()
    values = (
        user_id, request.get("target_role", "Software Engineer"), request.get("target_date"),
        request.get("daily_minutes", 45), request.get("days_per_week", 5),
        request.get("current_level", "BEGINNER"), json.dumps(request.get("preferred_languages") or ["python"]),
        json.dumps(request.get("focus_topics") or []), request.get("notes", ""), _now(),
    )
    with _get_conn() as (conn, cur):
        cur.execute(f"SELECT id FROM prep_goals WHERE user_id = {p}", (user_id,))
        row = cur.fetchone()
        if row is None:
            if USE_POSTGRES:
                cur.execute(
                    f"INSERT INTO prep_goals (user_id, target_role, target_date, daily_minutes, days_per_week, current_level, preferred_languages, focus_topics, notes, updated_at) VALUES ({', '.join([p] * len(values))}) RETURNING id",
                    values,
                )
                goal_id = cur.fetchone()["id"]
            else:
                cur.execute(
                    f"INSERT INTO prep_goals (user_id, target_role, target_date, daily_minutes, days_per_week, current_level, preferred_languages, focus_topics, notes, updated_at) VALUES ({', '.join([p] * len(values))})",
                    values,
                )
                goal_id = cur.lastrowid
        else:
            goal_id = row["id"]
            cur.execute(
                f"UPDATE prep_goals SET target_role = {p}, target_date = {p}, daily_minutes = {p}, days_per_week = {p}, current_level = {p}, preferred_languages = {p}, focus_topics = {p}, notes = {p}, updated_at = {p} WHERE user_id = {p}",
                values[1:] + (user_id,),
            )
    return get_goal(user_id) or {"id": goal_id, "user_id": user_id}


def get_goal(user_id: int) -> Optional[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(f"SELECT * FROM prep_goals WHERE user_id = {p}", (user_id,))
        row = _row_to_dict(cur.fetchone())
    return _decode(row, ("preferred_languages", "focus_topics"))


def record_code_submission(user_id: int, problem_id: int, language: str, source_code: str, result: dict) -> int:
    p = _ph()
    tests = result.get("tests") or []
    passed_tests = sum(1 for test in tests if test.get("passed"))
    total_tests = len(tests)
    passed = bool(result.get("status") == "Accepted")
    with _get_conn() as (conn, cur):
        values = (
            user_id, problem_id, language, source_code, result.get("status", "Unknown"), passed,
            passed_tests, total_tests, result.get("stdout", ""), result.get("stderr", ""),
            result.get("time"), result.get("memory"),
        )
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO prep_code_submissions (user_id, problem_id, language, source_code, status, passed, passed_tests, total_tests, stdout, stderr, runtime_ms, memory_kb) VALUES ({', '.join([p] * len(values))}) RETURNING id",
                values,
            )
            submission_id = cur.fetchone()["id"]
        else:
            cur.execute(
                f"INSERT INTO prep_code_submissions (user_id, problem_id, language, source_code, status, passed, passed_tests, total_tests, stdout, stderr, runtime_ms, memory_kb) VALUES ({', '.join([p] * len(values))})",
                values,
            )
            submission_id = cur.lastrowid
        if passed:
            _award_xp(cur, p, user_id, 25, "problem_solved", problem_id)
    return submission_id


def list_code_submissions(user_id: int, problem_id: int, limit: int = 20) -> list[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT id, problem_id, language, status, passed, passed_tests, total_tests, runtime_ms, memory_kb, created_at FROM prep_code_submissions WHERE user_id = {p} AND problem_id = {p} ORDER BY created_at DESC LIMIT {p}",
            (user_id, problem_id, limit),
        )
        return [_row_to_dict(row) for row in cur.fetchall()]


def get_dashboard(user_id: int) -> dict:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute("SELECT COUNT(*) AS count FROM prep_problems")
        total = int(_row_to_dict(cur.fetchone())["count"])
        cur.execute(f"SELECT COUNT(DISTINCT problem_id) AS count FROM prep_code_submissions WHERE user_id = {p} AND passed = {1 if not USE_POSTGRES else 'TRUE'}", (user_id,))
        solved = int(_row_to_dict(cur.fetchone())["count"])
        cur.execute(f"SELECT DISTINCT problem_id FROM prep_code_submissions WHERE user_id = {p} AND passed = {1 if not USE_POSTGRES else 'TRUE'}", (user_id,))
        solved_problem_ids = [int(_row_to_dict(row)["problem_id"]) for row in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) AS count FROM prep_code_submissions WHERE user_id = {p}", (user_id,))
        attempts = int(_row_to_dict(cur.fetchone())["count"])
        cur.execute(
            f"SELECT t.slug, t.name, COUNT(DISTINCT p.id) AS total, COUNT(DISTINCT CASE WHEN cs.passed = {1 if not USE_POSTGRES else 'TRUE'} THEN p.id END) AS solved FROM prep_topics t LEFT JOIN prep_problems p ON p.topic_id = t.id LEFT JOIN prep_code_submissions cs ON cs.problem_id = p.id AND cs.user_id = {p} GROUP BY t.id, t.slug, t.name ORDER BY t.id",
            (user_id,),
        )
        by_topic = [_row_to_dict(row) for row in cur.fetchall()]
        cur.execute(
            f"SELECT cs.id, cs.problem_id, p.title, cs.language, cs.status, cs.passed, cs.passed_tests, cs.total_tests, cs.created_at FROM prep_code_submissions cs JOIN prep_problems p ON p.id = cs.problem_id WHERE cs.user_id = {p} ORDER BY cs.created_at DESC LIMIT 8",
            (user_id,),
        )
        recent = [_row_to_dict(row) for row in cur.fetchall()]
    stats = get_gamification(user_id)
    return {
        "total_problems": total,
        "solved_problems": solved,
        "solved_problem_ids": solved_problem_ids,
        "attempts": attempts,
        "completion_percent": round((solved / total) * 100, 1) if total else 0,
        "xp": stats.get("xp", 0),
        "streak_days": stats.get("streak_days", 0),
        "by_topic": by_topic,
        "recent_submissions": recent,
        "goal": get_goal(user_id),
        "roadmaps": list_roadmaps(user_id)[:3],
    }


def create_generated_roadmap(user_id: int, goal: dict, plan: dict, problems: list[dict]) -> dict:
    selected = {problem["slug"]: problem for problem in problems}
    selected_problems = [selected[slug] for slug in plan.get("problem_slugs", []) if slug in selected]
    if not selected_problems:
        raise ValueError("The generated plan did not contain known problems.")
    topic_slugs = list(dict.fromkeys(problem["topic_slug"] for problem in selected_problems))
    roadmap = create_roadmap(
        user_id,
        {
            "target_role": goal.get("target_role", "Software Engineer"),
            "title": plan.get("title") or f"{goal.get('target_role', 'Software Engineer')} DSA plan",
            "target_date": goal.get("target_date"),
            "topic_slugs": topic_slugs,
            "goal_id": goal.get("id"),
            "summary": plan.get("summary", ""),
            "generated_by": plan.get("generated_by", "heuristic"),
            "daily_minutes": goal.get("daily_minutes", 45),
            "weekly_hours": round((goal.get("daily_minutes", 45) * goal.get("days_per_week", 5)) / 60, 1),
        },
    )
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(f"DELETE FROM prep_roadmap_nodes WHERE roadmap_id = {p}", (roadmap["id"],))
        for position, problem in enumerate(selected_problems, start=1):
            cur.execute(
                f"SELECT id FROM prep_topics WHERE slug = {p}",
                (problem["topic_slug"],),
            )
            topic_row = cur.fetchone()
            cur.execute(
                f"INSERT INTO prep_roadmap_nodes (roadmap_id, topic_id, problem_id, position, item_type, estimated_minutes, rationale) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p})",
                (
                    roadmap["id"], topic_row["id"], problem["id"], position, "PROBLEM", problem["estimated_minutes"],
                    f"Practice {problem['title']} after the {problem['topic_name']} pattern.",
                ),
            )
    return get_roadmap(roadmap["id"], user_id)
