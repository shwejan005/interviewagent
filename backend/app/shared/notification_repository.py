"""Durable, user-scoped notifications with idempotent creation."""

import json

from app.config.database import USE_POSTGRES, _get_conn, _now_sql, _ph, _row_to_dict


def _safe_href(href: str) -> str:
    value = (href or "").strip()
    return value if value.startswith("/") and not value.startswith("//") else "/notifications"


def _validate_notification(notification_type: str, title: str, body: str, dedupe_key: str | None) -> None:
    if not notification_type.strip() or not title.strip():
        raise ValueError("Notification type and title are required")
    if len(notification_type) > 80 or len(title) > 160 or len(body) > 1000:
        raise ValueError("Notification content exceeds its maximum length")
    if dedupe_key is not None and (not dedupe_key.strip() or len(dedupe_key) > 255):
        raise ValueError("Notification dedupe key is invalid")


def _insert_notification(cur, args: tuple, dedupe_key: str | None) -> int:
    p = _ph()
    columns = (
        "user_id, org_id, application_id, notification_type, title, body, "
        "href, metadata_json, dedupe_key"
    )
    placeholders = ", ".join([p] * 9)
    if USE_POSTGRES:
        cur.execute(
            f"INSERT INTO user_notifications ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT (dedupe_key) DO NOTHING RETURNING id",
            args,
        )
        row = cur.fetchone()
        if row is not None:
            return int(row["id"])
    else:
        cur.execute(
            f"INSERT OR IGNORE INTO user_notifications ({columns}) VALUES ({placeholders})",
            args,
        )
        if cur.rowcount == 1:
            return int(cur.lastrowid)

    if dedupe_key is None:
        raise RuntimeError("Notification insert was ignored without a dedupe key")
    cur.execute(f"SELECT id, user_id FROM user_notifications WHERE dedupe_key = {p}", (dedupe_key,))
    row = cur.fetchone()
    if row is None or int(row["user_id"]) != int(args[0]):
        raise RuntimeError("Notification dedupe key belongs to a different recipient")
    return int(row["id"])


def create_notification(
    user_id: int,
    notification_type: str,
    title: str,
    body: str = "",
    *,
    href: str = "/notifications",
    org_id: int | None = None,
    application_id: int | None = None,
    metadata: dict | None = None,
    dedupe_key: str | None = None,
) -> int:
    """Create an inbox item once; return its ID even when a job is retried."""
    _validate_notification(notification_type, title, body, dedupe_key)
    args = (
        user_id,
        org_id,
        application_id,
        notification_type.strip(),
        title.strip(),
        body.strip(),
        _safe_href(href),
        json.dumps(metadata or {}, separators=(",", ":")),
        dedupe_key,
    )
    with _get_conn() as (conn, cur):
        return _insert_notification(cur, args, dedupe_key)


def list_notifications(user_id: int, *, limit: int = 20, offset: int = 0) -> dict:
    """Return a user's inbox and unread count; never query by client-supplied user ID."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT id, org_id, application_id, notification_type, title, body, href, "
            f"metadata_json, created_at, read_at FROM user_notifications "
            f"WHERE user_id = {p} ORDER BY created_at DESC, id DESC LIMIT {p} OFFSET {p}",
            (user_id, limit + 1, offset),
        )
        rows = [_row_to_dict(row) for row in cur.fetchall()]
        cur.execute(
            f"SELECT COUNT(*) AS unread_count FROM user_notifications WHERE user_id = {p} AND read_at IS NULL",
            (user_id,),
        )
        unread_count = int(cur.fetchone()["unread_count"])

    has_more = len(rows) > limit
    rows = rows[:limit]
    for row in rows:
        try:
            row["metadata"] = json.loads(row.pop("metadata_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            row["metadata"] = {}
    return {"notifications": rows, "unread_count": unread_count, "has_more": has_more}


def mark_notification_read(user_id: int, notification_id: int) -> bool:
    """Mark one owned notification read; a foreign ID is indistinguishable from absent."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"UPDATE user_notifications SET read_at = COALESCE(read_at, {_now_sql()}) "
            f"WHERE id = {p} AND user_id = {p}",
            (notification_id, user_id),
        )
        return cur.rowcount == 1


def mark_all_notifications_read(user_id: int) -> int:
    """Mark every unread notification for the authenticated user read."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"UPDATE user_notifications SET read_at = {_now_sql()} WHERE user_id = {p} AND read_at IS NULL",
            (user_id,),
        )
        return int(cur.rowcount)
