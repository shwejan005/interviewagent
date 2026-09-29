"""Repository for the safe, text-first preparation suite."""

import json
from datetime import datetime, timezone
from typing import Optional

from database import USE_POSTGRES, _get_conn, _ph, _row_to_dict


_TOPIC_SEED = (
    ("arrays", "Arrays", "Indexing, iteration, and invariant-driven array problems.", "FOUNDATION", []),
    ("hashing", "Hashing", "Maps and sets for lookup, counting, and deduplication.", "FOUNDATION", ["arrays"]),
    ("two-pointers", "Two Pointers", "Ordered scans that maintain a moving invariant.", "CORE", ["arrays"]),
    ("trees", "Trees", "Recursive and iterative traversal of hierarchical data.", "CORE", ["arrays"]),
    ("graphs", "Graphs", "Reachability, traversal, and shortest-path reasoning.", "CORE", ["trees"]),
    ("system-design", "System Design", "Bounded design exercises for reliable backend systems.", "APPLIED", ["hashing", "graphs"]),
)

_PROBLEM_SEED = (
    ("two-sum", "arrays", "Two Sum", "Given an integer array and a target, return the indices of two values that add to the target. Explain the time and space complexity.", "EASY", 25, ["arrays", "hashing"]),
    ("deduplicate-events", "hashing", "Deduplicate Events", "Given an unordered stream of event IDs, return the first occurrence of each ID while preserving arrival order. State the memory trade-off.", "EASY", 30, ["hashing"]),
    ("longest-window", "two-pointers", "Longest Unique Window", "Find the longest contiguous substring with no repeated characters. Explain the invariant maintained by your window.", "MEDIUM", 35, ["two-pointers", "hashing"]),
    ("tree-level-order", "trees", "Tree Level Order", "Return the values of a binary tree grouped by depth. Compare the iterative and recursive approaches.", "MEDIUM", 35, ["trees"]),
    ("shortest-route", "graphs", "Shortest Route", "Given an unweighted graph, return the shortest number of edges between two nodes or explain why no route exists.", "MEDIUM", 45, ["graphs"]),
    ("rate-limited-api", "system-design", "Rate-Limited API", "Design a multi-instance rate limiter for an HTTP API. Cover correctness, storage, failure behavior, and observability.", "APPLIED", 60, ["system-design", "hashing"]),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_catalog() -> None:
    """Insert the small reviewed starter catalog without overwriting edits."""
    p = _ph()
    with _get_conn() as (conn, cur):
        topic_ids: dict[str, int] = {}
        for slug, name, description, difficulty, prerequisites in _TOPIC_SEED:
            cur.execute(f"SELECT id FROM prep_topics WHERE slug = {p}", (slug,))
            row = cur.fetchone()
            if row is None:
                if USE_POSTGRES:
                    cur.execute(
                        f"INSERT INTO prep_topics (slug, name, description, difficulty, prerequisites) "
                        f"VALUES ({p}, {p}, {p}, {p}, {p}) RETURNING id",
                        (slug, name, description, difficulty, json.dumps(prerequisites)),
                    )
                    topic_id = cur.fetchone()["id"]
                else:
                    cur.execute(
                        f"INSERT INTO prep_topics (slug, name, description, difficulty, prerequisites) "
                        f"VALUES ({p}, {p}, {p}, {p}, {p})",
                        (slug, name, description, difficulty, json.dumps(prerequisites)),
                    )
                    topic_id = cur.lastrowid
            else:
                topic_id = row["id"]
            topic_ids[slug] = topic_id

        for slug, topic_slug, title, prompt, difficulty, minutes, concepts in _PROBLEM_SEED:
            cur.execute(f"SELECT id FROM prep_problems WHERE slug = {p}", (slug,))
            if cur.fetchone() is not None:
                continue
            values = (
                topic_ids[topic_slug], slug, title, prompt, difficulty,
                minutes, json.dumps(concepts),
            )
            cur.execute(
                f"INSERT INTO prep_problems "
                f"(topic_id, slug, title, prompt, difficulty, estimated_minutes, expected_concepts) "
                f"VALUES ({', '.join([p] * len(values))})",
                values,
            )


def _decode(row: Optional[dict], fields: tuple[str, ...] = ()) -> Optional[dict]:
    if row is None:
        return None
    for field in fields:
        if isinstance(row.get(field), str):
            row[field] = json.loads(row[field])
    return row


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
            f"p.expected_concepts, t.slug AS topic_slug, t.name AS topic_name "
            f"FROM prep_problems p JOIN prep_topics t ON t.id = p.topic_id {where} ORDER BY p.id",
            tuple(params),
        )
        rows = [_row_to_dict(row) for row in cur.fetchall()]
    return [_decode(row, ("expected_concepts",)) for row in rows]


def get_problem(problem_id: int) -> Optional[dict]:
    problems = list_problems()
    return next((problem for problem in problems if problem["id"] == problem_id), None)


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
        values = (user_id, title, request["target_role"], request.get("target_date"))
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO prep_roadmaps (user_id, title, target_role, target_date) "
                f"VALUES ({p}, {p}, {p}, {p}) RETURNING id",
                values,
            )
            roadmap_id = cur.fetchone()["id"]
        else:
            cur.execute(
                f"INSERT INTO prep_roadmaps (user_id, title, target_role, target_date) "
                f"VALUES ({p}, {p}, {p}, {p})",
                values,
            )
            roadmap_id = cur.lastrowid
        for position, topic in enumerate(selected, start=1):
            cur.execute(
                f"INSERT INTO prep_roadmap_nodes (roadmap_id, topic_id, position) VALUES ({p}, {p}, {p})",
                (roadmap_id, topic["id"], position),
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
            f"SELECT r.*, n.id AS node_id, n.topic_id, n.position, n.status AS node_status, "
            f"n.completed_at, t.slug AS topic_slug, t.name AS topic_name, t.description "
            f"FROM prep_roadmaps r JOIN prep_roadmap_nodes n ON n.roadmap_id = r.id "
            f"JOIN prep_topics t ON t.id = n.topic_id "
            f"WHERE r.id = {p} AND r.user_id = {p} ORDER BY n.position",
            (roadmap_id, user_id),
        )
        rows = [_row_to_dict(row) for row in cur.fetchall()]
    if not rows:
        return None
    roadmap = {key: rows[0][key] for key in ("id", "user_id", "title", "target_role", "target_date", "status", "created_at", "updated_at")}
    roadmap["nodes"] = [
        {
            "id": row["node_id"],
            "topic_id": row["topic_id"],
            "position": row["position"],
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
