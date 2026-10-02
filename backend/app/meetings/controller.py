"""Authenticated in-app WebRTC signaling for scheduled human interviews."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from app.config import database as db
from app.hiring import repository as hdb
from app.shared.authz import Actor, current_actor
from app.shared.security import TokenError, create_meeting_room_ticket, decode_meeting_room_ticket

router = APIRouter(tags=["in-app-meetings"])
_NOT_FOUND = "Not found."
_JOIN_EARLY_SECONDS = 15 * 60
_JOIN_LATE_SECONDS = 30 * 60
_MAX_SIGNAL_BYTES = 256_000
_MEETING_PROTOCOL = "evalia-meeting-v1"
_PARTICIPANT_LABEL = "Interview participant"
_DEFAULT_STUN_URL = "stun:stun.l.google.com:19302"
_TURN_CREDENTIAL_TTL_SECONDS = 10 * 60


def _ice_server_configuration(
    user_id: int,
    interview_id: int,
    *,
    now: int | None = None,
    turn_urls: str | None = None,
    shared_secret: str | None = None,
) -> list[dict[str, Any]]:
    """Build browser ICE config with short-lived coturn REST credentials."""
    configured_urls = os.getenv("TURN_URLS", "") if turn_urls is None else turn_urls
    secret_value = os.getenv("TURN_SHARED_SECRET", "") if shared_secret is None else shared_secret
    secret = secret_value.strip()
    servers: list[dict[str, Any]] = [{"urls": [_DEFAULT_STUN_URL]}]
    urls = [value.strip() for value in configured_urls.split(",") if value.strip()]
    if not urls:
        return servers
    if not secret:
        raise HTTPException(status_code=503, detail="TURN_URLS is configured but TURN_SHARED_SECRET is missing.")
    if any(
        not value.startswith(("turn:", "turns:")) or "@" in value
        for value in urls
    ):
        raise HTTPException(status_code=500, detail="TURN_URLS must contain only turn: or turns: URLs.")

    expires_at = (int(time.time()) if now is None else now) + _TURN_CREDENTIAL_TTL_SECONDS
    username = f"{expires_at}:{user_id}:{interview_id}"
    # Coturn's REST API specifies HMAC-SHA1 credentials; this is keyed HMAC,
    # not bare SHA-1. Credentials are additionally short-lived and room-scoped.
    digest = hmac.new(secret.encode("utf-8"), username.encode("utf-8"), hashlib.sha1).digest()  # NOSONAR
    credential = base64.b64encode(digest).decode("ascii")
    servers.append({"urls": urls, "username": username, "credential": credential})
    return servers


def _join_window(interview: dict) -> tuple[datetime, datetime]:
    start = hdb._parse_ts(interview["scheduled_start"])
    end = hdb._parse_ts(interview["scheduled_end"])
    if start is None or end is None:
        raise HTTPException(status_code=409, detail="This interview has an invalid schedule.")
    return start - timedelta(seconds=_JOIN_EARLY_SECONDS), end + timedelta(seconds=_JOIN_LATE_SECONDS)


def _participant_summary(interview: dict, actor_user_id: int) -> list[dict[str, Any]]:
    return [
        {
            "user_id": int(participant["user_id"]),
            "name": participant.get("full_name") or _PARTICIPANT_LABEL,
            "role": participant["participant_role"],
            "self": int(participant["user_id"]) == actor_user_id,
        }
        for participant in interview.get("participants", [])
    ]


@router.post("/me/interviews/{interview_id}/join")
async def create_interview_room_ticket(interview_id: int, actor: Actor = Depends(current_actor)):
    interview = await asyncio.to_thread(hdb.get_interview_for_participant, interview_id, actor.user_id)
    if interview is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    if interview["status"] != "SCHEDULED":
        raise HTTPException(status_code=409, detail="This interview is not currently scheduled.")
    opens_at, closes_at = _join_window(interview)
    now = datetime.now(timezone.utc)
    if now < opens_at:
        raise HTTPException(status_code=409, detail=f"The in-app meeting room opens at {opens_at.isoformat()}.")
    if now > closes_at:
        raise HTTPException(status_code=409, detail="The in-app meeting room is closed. Contact the hiring team to reschedule.")
    ticket = create_meeting_room_ticket(
        actor.user_id,
        interview_id,
        int(interview["org_id"]),
        auth_version=actor.auth_version,
    )
    ice_servers = _ice_server_configuration(actor.user_id, interview_id)
    return {
        "interview_id": interview_id,
        "org_id": int(interview["org_id"]),
        "title": interview["title"],
        "posting_title": interview["posting_title"],
        "org_name": interview["org_name"],
        "scheduled_start": interview["scheduled_start"],
        "scheduled_end": interview["scheduled_end"],
        "timezone": interview["timezone"],
        "ticket": ticket,
        "ice_servers": ice_servers,
        "participants": _participant_summary(interview, actor.user_id),
        "room_opens_at": opens_at.isoformat(),
        "room_closes_at": closes_at.isoformat(),
    }


class MeetingHub:
    """Process-local WebRTC signaling relay; media stays peer-to-peer."""

    def __init__(self) -> None:
        self._rooms: dict[int, dict[int, WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def join(self, interview_id: int, user_id: int, websocket: WebSocket, profile: dict) -> list[dict]:
        async with self._lock:
            room = self._rooms.setdefault(interview_id, {})
            existing = [
                {"user_id": peer_id, "name": peer.get("name", "Interview participant"), "role": peer.get("role", "PARTICIPANT")}
                for peer_id, peer in room.items()
            ]
            room[user_id] = {"socket": websocket, **profile}
        await self.broadcast(
            interview_id,
            {"type": "peer_joined", "participant": {"user_id": user_id, **profile}},
            exclude_user_id=user_id,
        )
        return existing

    async def leave(self, interview_id: int, user_id: int) -> None:
        async with self._lock:
            room = self._rooms.get(interview_id, {})
            room.pop(user_id, None)
            if not room:
                self._rooms.pop(interview_id, None)
        await self.broadcast(interview_id, {"type": "peer_left", "user_id": user_id})

    async def relay(self, interview_id: int, sender_id: int, target_id: int, message: dict) -> None:
        async with self._lock:
            peer = self._rooms.get(interview_id, {}).get(target_id)
            target_socket = peer.get("socket") if peer else None
        if target_socket is not None:
            await target_socket.send_json({**message, "from_user_id": sender_id})

    async def broadcast(self, interview_id: int, message: dict, *, exclude_user_id: int | None = None) -> None:
        async with self._lock:
            targets = [
                entry["socket"] for user_id, entry in self._rooms.get(interview_id, {}).items()
                if user_id != exclude_user_id
            ]
        for target in targets:
            try:
                await target.send_json(message)
            except Exception:
                continue

    async def contains(self, interview_id: int, user_id: int) -> bool:
        async with self._lock:
            return user_id in self._rooms.get(interview_id, {})


meeting_hub = MeetingHub()


def _ticket_from_subprotocols(websocket: WebSocket) -> str | None:
    values = [value.strip() for value in websocket.headers.get("sec-websocket-protocol", "").split(",")]
    return values[1] if len(values) >= 2 and values[0] == _MEETING_PROTOCOL else None


async def _authenticate_websocket(websocket: WebSocket, interview_id: int) -> tuple[dict, dict] | None:
    ticket = _ticket_from_subprotocols(websocket)
    if not ticket:
        await websocket.close(code=4401, reason="A short-lived in-app meeting ticket is required.")
        return None
    try:
        claims = decode_meeting_room_ticket(ticket)
    except TokenError:
        await websocket.close(code=4401, reason="Meeting ticket is invalid or expired.")
        return None
    if claims["interview_id"] != interview_id:
        await websocket.close(code=4403, reason="Meeting ticket is scoped to another room.")
        return None
    actor = await asyncio.to_thread(db.get_user, claims["user_id"])
    is_valid_user = (
        actor is not None
        and actor.get("status") == "ACTIVE"
        and int(actor.get("auth_version", 0)) == claims["auth_version"]
    )
    if not is_valid_user:
        await websocket.close(code=4401, reason="Account session is no longer valid.")
        return None
    return claims, actor


async def _scheduled_room_for_ticket(websocket: WebSocket, interview_id: int, claims: dict) -> dict | None:
    db.set_request_db_context(user_id=claims["user_id"], org_id=claims["org_id"])
    try:
        interview = await asyncio.to_thread(hdb.get_interview_for_participant, interview_id, claims["user_id"])
    finally:
        db.clear_request_db_context()
    if interview is None or int(interview["org_id"]) != claims["org_id"] or interview["status"] != "SCHEDULED":
        await websocket.close(code=4404, reason="Interview room not found.")
        return None
    opens_at, closes_at = _join_window(interview)
    if not opens_at <= datetime.now(timezone.utc) <= closes_at:
        await websocket.close(code=4409, reason="This meeting room is outside its scheduled join window.")
        return None
    return interview


def _participant_profile(interview: dict, user_id: int, actor: dict) -> dict:
    for person in interview.get("participants", []):
        if int(person["user_id"]) == user_id:
            return {"name": person.get("full_name") or _PARTICIPANT_LABEL, "role": person["participant_role"]}
    return {"name": actor.get("full_name") or _PARTICIPANT_LABEL, "role": "PARTICIPANT"}


async def _relay_signal(websocket: WebSocket, interview_id: int, sender_id: int, message: Any) -> bool:
    if not isinstance(message, dict):
        return True
    message_type = message.get("type")
    if message_type == "leave":
        return False
    if message_type not in {"offer", "answer", "ice_candidate"}:
        await websocket.send_json({"type": "error", "message": "Unsupported signaling message."})
        return True
    target_id = message.get("to_user_id")
    if not isinstance(target_id, int) or not await meeting_hub.contains(interview_id, target_id):
        await websocket.send_json({"type": "error", "message": "The other participant is no longer in this room."})
        return True
    if len(str(message).encode("utf-8")) > _MAX_SIGNAL_BYTES:
        await websocket.send_json({"type": "error", "message": "Signaling message is too large."})
        return True
    safe_message = {key: value for key, value in message.items() if key not in {"from_user_id", "self_user_id"}}
    await meeting_hub.relay(interview_id, sender_id, target_id, safe_message)
    return True


@router.websocket("/ws/interviews/{interview_id}")
async def interview_signaling(websocket: WebSocket, interview_id: int):
    authenticated = await _authenticate_websocket(websocket, interview_id)
    if authenticated is None:
        return
    claims, actor = authenticated
    interview = await _scheduled_room_for_ticket(websocket, interview_id, claims)
    if interview is None:
        return
    negotiated = _MEETING_PROTOCOL if _MEETING_PROTOCOL in websocket.headers.get("sec-websocket-protocol", "") else None
    await websocket.accept(subprotocol=negotiated)
    profile = _participant_profile(interview, claims["user_id"], actor)
    existing = await meeting_hub.join(interview_id, claims["user_id"], websocket, profile)
    await websocket.send_json({"type": "room_state", "interview_id": interview_id, "self_user_id": claims["user_id"], "participants": existing})
    try:
        while True:
            message = await websocket.receive_json()
            if not await _relay_signal(websocket, interview_id, claims["user_id"], message):
                break
    except WebSocketDisconnect:
        pass
    finally:
        await meeting_hub.leave(interview_id, claims["user_id"])
