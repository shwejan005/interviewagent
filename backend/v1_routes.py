"""Additive durable command API for interview execution.

The legacy routes remain available for compatibility. These commands separate
admission from worker execution and return 202 until a worker completes work.
"""

import asyncio
import hashlib
import os
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response
from fastapi.responses import JSONResponse

import database as db
import security
from authz import Actor, optional_actor
from job_worker import BEHAVIORAL_JOB, FINAL_DECISION_JOB, SCREENING_JOB, TECHNICAL_JOB
from models import AnswerRequest, StartRequest
from routes import _load_accessible_evaluation

router = APIRouter(prefix="/v1", tags=["durable-interview"])


async def _db(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def _scope_key(actor: Optional[Actor]) -> str:
    if actor is None:
        return "public"
    return f"org:{actor.org_id}" if actor.org_id is not None else f"user:{actor.user_id}"


def _cookie(response: Response, token: Optional[str]) -> None:
    if not token:
        return
    response.set_cookie(
        "evalia_evaluation_token",
        token,
        httponly=True,
        samesite="lax",
        secure=os.getenv("APP_ENV", "development").strip().lower() == "production",
        max_age=60 * 60 * 12,
        path="/",
    )


def _token_from_request(header: Optional[str], cookie: Optional[str]) -> Optional[str]:
    return header or cookie


@router.post("/evaluations", status_code=202)
async def admit_evaluation(
    req: StartRequest,
    response: Response,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    actor: Optional[Actor] = Depends(optional_actor),
):
    resume = req.resume.strip()
    role = req.role.strip()
    if not resume or not role:
        raise HTTPException(status_code=400, detail="Resume and role are required.")

    anonymous_token = security.generate_evaluation_access_token() if actor is None else None
    digest = hashlib.sha256(f"{_scope_key(actor)}:{role}:{resume}".encode()).hexdigest()
    key = idempotency_key or f"v1-screen:{digest}"
    evaluation_id = await _db(
        db.create_evaluation,
        resume_text=resume,
        role=role,
        candidate_name=req.candidate_name.strip(),
        org_id=actor.org_id if actor else None,
        owner_user_id=actor.user_id if actor else None,
        access_token_hash=(security.hash_evaluation_access_token(anonymous_token) if anonymous_token else None),
    )
    job_id = await _db(
        db.enqueue_job,
        SCREENING_JOB,
        {"evaluation_id": evaluation_id, "trace_id": hashlib.sha256(key.encode()).hexdigest()[:32]},
        idempotency_key=key,
        tenant_key=_scope_key(actor),
    )
    _cookie(response, anonymous_token)
    response.status_code = 202
    return {
        "evaluation_id": evaluation_id,
        "job_id": job_id,
        "status": "QUEUED",
        "evaluation_access_token": anonymous_token,
    }


@router.post("/evaluations/{evaluation_id}/answers", status_code=202)
async def admit_answer(
    evaluation_id: int,
    req: AnswerRequest,
    actor: Optional[Actor] = Depends(optional_actor),
    evaluation_token: Optional[str] = Header(default=None, alias="X-Evaluation-Token"),
    evaluation_cookie: Optional[str] = Cookie(default=None, alias="evalia_evaluation_token"),
):
    token = _token_from_request(evaluation_token, evaluation_cookie)
    await _load_accessible_evaluation(evaluation_id, actor, token)
    round_number = evaluation["current_round"]
    if round_number not in (2, 3):
        raise HTTPException(status_code=409, detail="This evaluation is not waiting for an answer.")
    answer = req.answer.strip()
    if not answer:
        raise HTTPException(status_code=400, detail="Answer cannot be empty.")
    existing = await _db(db.get_answer, evaluation_id, round_number)
    if existing is not None and await _db(db.get_verdict_by_round, evaluation_id, round_number) is not None:
        raise HTTPException(status_code=409, detail="This round has already been evaluated.")
    if existing is None:
        await _db(db.save_answer, evaluation_id, round_number, answer)
    digest = hashlib.sha256(answer.encode()).hexdigest()
    job_type = TECHNICAL_JOB if round_number == 2 else BEHAVIORAL_JOB
    job_id = await _db(
        db.enqueue_job,
        job_type,
        {"evaluation_id": evaluation_id, "trace_id": digest[:32]},
        idempotency_key=f"v1-answer:{evaluation_id}:{round_number}:{digest}",
        tenant_key=_scope_key(actor),
    )
    return JSONResponse(
        status_code=202,
        content={"evaluation_id": evaluation_id, "job_id": job_id, "status": "QUEUED", "round": round_number},
    )


@router.post("/evaluations/{evaluation_id}/finalize", status_code=202)
async def admit_finalization(
    evaluation_id: int,
    actor: Optional[Actor] = Depends(optional_actor),
    evaluation_token: Optional[str] = Header(default=None, alias="X-Evaluation-Token"),
    evaluation_cookie: Optional[str] = Cookie(default=None, alias="evalia_evaluation_token"),
):
    token = _token_from_request(evaluation_token, evaluation_cookie)
    evaluation = await _load_accessible_evaluation(evaluation_id, actor, token)
    if evaluation["status"] == "COMPLETE":
        return {"evaluation_id": evaluation_id, "status": "COMPLETE"}
    if evaluation["current_round"] < 4:
        raise HTTPException(status_code=400, detail="Interview is not complete.")
    job_id = await _db(
        db.enqueue_job,
        FINAL_DECISION_JOB,
        {"evaluation_id": evaluation_id, "trace_id": hashlib.sha256(f"final:{evaluation_id}".encode()).hexdigest()[:32]},
        idempotency_key=f"v1-final:{evaluation_id}",
        tenant_key=_scope_key(actor),
    )
    return JSONResponse(
        status_code=202,
        content={"evaluation_id": evaluation_id, "job_id": job_id, "status": "QUEUED"},
    )


@router.get("/evaluations/{evaluation_id}")
async def durable_evaluation_status(
    evaluation_id: int,
    actor: Optional[Actor] = Depends(optional_actor),
    evaluation_token: Optional[str] = Header(default=None, alias="X-Evaluation-Token"),
    evaluation_cookie: Optional[str] = Cookie(default=None, alias="evalia_evaluation_token"),
):
    token = _token_from_request(evaluation_token, evaluation_cookie)
    evaluation = await _load_accessible_evaluation(evaluation_id, actor, token)
    public = await _db(db.get_evaluation_public, evaluation_id)
    jobs = []
    for job_type in (SCREENING_JOB, TECHNICAL_JOB, BEHAVIORAL_JOB, FINAL_DECISION_JOB):
        job = await _db(db.get_job_by_idempotency_key, f"v1-{job_type}:{evaluation_id}")
        if job:
            jobs.append({"id": job["id"], "job_type": job["job_type"], "status": job["status"], "attempts": job["attempts"], "last_error": job["last_error"]})
    return {"evaluation": public, "jobs": jobs}
