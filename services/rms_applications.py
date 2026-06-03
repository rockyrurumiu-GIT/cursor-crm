"""RMS applications business logic (Phase 2)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth.service import AuthContext
from schemas.rms import ALLOWED_TRANSITIONS, APPLICATION_TERMINAL
from services import rms_scope as rms_ds


def _utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def application_to_dict(row: Any) -> Dict[str, Any]:
    return {
        "id": row.id,
        "job_id": row.job_id,
        "candidate_id": row.candidate_id,
        "client_id": row.client_id,
        "resume_id": row.resume_id,
        "status": row.status or "",
        "recommended_by": row.recommended_by,
        "recommended_at": row.recommended_at or "",
        "current_stage": row.current_stage or "",
        "last_activity_at": row.last_activity_at or "",
        "created_at": row.created_at or "",
        "updated_at": row.updated_at or "",
    }


def status_history_to_dict(row: Any) -> Dict[str, Any]:
    return {
        "id": row.id,
        "application_id": row.application_id,
        "from_status": row.from_status or "",
        "to_status": row.to_status or "",
        "reason": row.reason or "",
        "note": row.note or "",
        "changed_by": row.changed_by,
        "changed_at": row.changed_at or "",
    }


def list_applications(
    db: Session,
    ctx: AuthContext,
    RmsApplication: Type[Any],
    Client: Type[Any],
    *,
    job_id: Optional[int] = None,
    candidate_id: Optional[int] = None,
    client_id: Optional[int] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    q = rms_ds.scoped_applications_query(db, ctx, RmsApplication, Client, action="read")
    if job_id is not None:
        q = q.filter(RmsApplication.job_id == job_id)
    if candidate_id is not None:
        q = q.filter(RmsApplication.candidate_id == candidate_id)
    if client_id is not None:
        q = q.filter(RmsApplication.client_id == client_id)
    if status:
        q = q.filter(RmsApplication.status == status)
    rows = q.order_by(RmsApplication.id.desc()).all()
    return [application_to_dict(r) for r in rows]


def get_application(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    RmsApplication: Type[Any],
    Client: Type[Any],
) -> Dict[str, Any]:
    row = (
        rms_ds.scoped_applications_query(db, ctx, RmsApplication, Client, action="read")
        .filter(RmsApplication.id == application_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="推荐记录不存在")
    return application_to_dict(row)


def _get_writable_application(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    RmsApplication: Type[Any],
    Client: Type[Any],
):
    row = (
        rms_ds.scoped_applications_query(db, ctx, RmsApplication, Client, action="write")
        .filter(RmsApplication.id == application_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="推荐记录不存在")
    return row


def create_application(
    db: Session,
    ctx: AuthContext,
    data: Dict[str, Any],
    RmsJob: Type[Any],
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
) -> Dict[str, Any]:
    job_id = int(data["job_id"])
    candidate_id = int(data["candidate_id"])
    job = rms_ds.assert_job_writable(db, ctx, job_id, RmsJob, Client)
    rms_ds.assert_candidate_usable_for_application(
        db, ctx, candidate_id, RmsCandidate, RmsApplication, Client
    )
    now = _utc_now_str()
    row = RmsApplication(
        job_id=job_id,
        candidate_id=candidate_id,
        client_id=int(job.client_id),
        resume_id=data.get("resume_id"),
        status="recommended",
        recommended_by=ctx.user_id,
        recommended_at=now,
        current_stage="recommended",
        last_activity_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="该岗位已存在该候选人的推荐记录")
    db.refresh(row)
    return application_to_dict(row)


def update_application(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    data: Dict[str, Any],
    RmsJob: Type[Any],
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
) -> Dict[str, Any]:
    row = _get_writable_application(db, ctx, application_id, RmsApplication, Client)

    if data.get("job_id") is not None:
        job_id = int(data["job_id"])
        job = rms_ds.assert_job_writable(db, ctx, job_id, RmsJob, Client)
        row.job_id = job_id
        row.client_id = int(job.client_id)

    if data.get("candidate_id") is not None:
        candidate_id = int(data["candidate_id"])
        rms_ds.assert_candidate_usable_for_application(
            db, ctx, candidate_id, RmsCandidate, RmsApplication, Client
        )
        row.candidate_id = candidate_id

    if "resume_id" in data:
        row.resume_id = data.get("resume_id")

    row.updated_at = _utc_now_str()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="该岗位已存在该候选人的推荐记录")
    db.refresh(row)
    return application_to_dict(row)


def transition_application_status(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    data: Dict[str, Any],
    RmsApplication: Type[Any],
    RmsApplicationStatusHistory: Type[Any],
    Client: Type[Any],
) -> Dict[str, Any]:
    row = _get_writable_application(db, ctx, application_id, RmsApplication, Client)
    from_status = (row.status or "").strip() or "recommended"
    to_status = str(data.get("to_status") or "").strip()
    if not to_status:
        raise HTTPException(status_code=400, detail="to_status 不能为空")
    if from_status in APPLICATION_TERMINAL:
        raise HTTPException(status_code=400, detail=f"终态 {from_status} 不可再流转")
    allowed = ALLOWED_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"不允许从 {from_status} 变更为 {to_status}",
        )
    now = _utc_now_str()
    row.status = to_status
    row.current_stage = to_status
    row.last_activity_at = now
    row.updated_at = now
    hist = RmsApplicationStatusHistory(
        application_id=row.id,
        from_status=from_status,
        to_status=to_status,
        reason=str(data.get("reason") or "").strip(),
        note=str(data.get("note") or "").strip(),
        changed_by=ctx.user_id,
        changed_at=now,
    )
    db.add(hist)
    db.commit()
    db.refresh(row)
    return application_to_dict(row)


def list_status_history(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    RmsApplication: Type[Any],
    RmsApplicationStatusHistory: Type[Any],
    Client: Type[Any],
) -> List[Dict[str, Any]]:
    get_application(db, ctx, application_id, RmsApplication, Client)
    rows = (
        db.query(RmsApplicationStatusHistory)
        .filter(RmsApplicationStatusHistory.application_id == application_id)
        .order_by(RmsApplicationStatusHistory.id.desc())
        .all()
    )
    return [status_history_to_dict(r) for r in rows]
