"""RMS jobs business logic (Phase 2)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth import service as auth_svc
from auth.service import AuthContext
from services import rms_scope as rms_ds


def _utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_user_exists(db: Session, user_id: int) -> None:
    row = db.execute(text("SELECT 1 FROM sys_user WHERE id = :uid LIMIT 1"), {"uid": user_id}).fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="用户不存在")


def job_to_dict(job: Any) -> Dict[str, Any]:
    return {
        "id": job.id,
        "client_id": job.client_id,
        "title": job.title or "",
        "department": job.department or "",
        "location": job.location or "",
        "headcount": int(job.headcount or 1),
        "job_description": job.job_description or "",
        "requirements": job.requirements or "",
        "status": job.status or "open",
        "owner_user_id": job.owner_user_id,
        "created_at": job.created_at or "",
        "updated_at": job.updated_at or "",
    }


def list_jobs(
    db: Session,
    ctx: AuthContext,
    RmsJob: Type[Any],
    Client: Type[Any],
    *,
    client_id: Optional[int] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    q = rms_ds.scoped_jobs_query(db, ctx, RmsJob, Client, action="read")
    if client_id is not None:
        q = q.filter(RmsJob.client_id == client_id)
    if status:
        q = q.filter(RmsJob.status == status)
    rows = q.order_by(RmsJob.id.desc()).all()
    return [job_to_dict(r) for r in rows]


def get_job(
    db: Session,
    ctx: AuthContext,
    job_id: int,
    RmsJob: Type[Any],
    Client: Type[Any],
) -> Dict[str, Any]:
    row = rms_ds.scoped_jobs_query(db, ctx, RmsJob, Client, action="read").filter(RmsJob.id == job_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return job_to_dict(row)


def create_job(
    db: Session,
    ctx: AuthContext,
    data: Dict[str, Any],
    RmsJob: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
) -> Dict[str, Any]:
    client_id = int(data["client_id"])
    owner_user_id = int(data["owner_user_id"])
    _ensure_user_exists(db, owner_user_id)

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="客户不存在")

    sales_owner_user_id = data.get("sales_owner_user_id")
    if sales_owner_user_id is not None:
        sales_owner_user_id = int(sales_owner_user_id)
        _ensure_user_exists(db, sales_owner_user_id)
        client.owner_user_id = sales_owner_user_id

    existing_count = db.query(RmsJob).filter(RmsJob.client_id == client_id).count()
    now = _utc_now_str()

    if client.delivery_owner_user_id is None and existing_count == 0:
        rms_ds.assert_crm_client_visible_for_trial(db, ctx, client_id, Client)
        delivery_owner_user_id = data.get("delivery_owner_user_id")
        if delivery_owner_user_id is None:
            raise HTTPException(status_code=400, detail="首个岗位须指定交付/招聘对接人 delivery_owner_user_id")
        delivery_owner_user_id = int(delivery_owner_user_id)
        _ensure_user_exists(db, delivery_owner_user_id)
        _, primary_dept = auth_svc.get_user_dept_ids(db, delivery_owner_user_id)
        client.delivery_owner_user_id = delivery_owner_user_id
        if primary_dept is not None:
            client.delivery_dept_id = primary_dept
    else:
        rms_ds.assert_rms_client_writable_regular(db, ctx, client_id, Client)

    job = RmsJob(
        client_id=client_id,
        title=str(data.get("title") or "").strip(),
        department=str(data.get("department") or "").strip(),
        location=str(data.get("location") or "").strip(),
        headcount=int(data.get("headcount") or 1),
        job_description=str(data.get("job_description") or "").strip(),
        requirements=str(data.get("requirements") or "").strip(),
        status=str(data.get("status") or "open").strip() or "open",
        owner_user_id=owner_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job_to_dict(job)


def _sync_applications_client_for_job(
    db: Session,
    job_id: int,
    client_id: int,
    RmsApplication: Type[Any],
) -> None:
    db.query(RmsApplication).filter(RmsApplication.job_id == job_id).update(
        {RmsApplication.client_id: client_id},
        synchronize_session=False,
    )


def update_job(
    db: Session,
    ctx: AuthContext,
    job_id: int,
    data: Dict[str, Any],
    RmsJob: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
) -> Dict[str, Any]:
    job = rms_ds.assert_job_writable(db, ctx, job_id, RmsJob, Client)
    new_client_id = data.get("client_id")
    if new_client_id is not None:
        new_client_id = int(new_client_id)
        if new_client_id != job.client_id:
            rms_ds.assert_rms_client_writable_regular(db, ctx, new_client_id, Client)
            job.client_id = new_client_id
            _sync_applications_client_for_job(db, job_id, new_client_id, RmsApplication)

    if data.get("owner_user_id") is not None:
        owner_user_id = int(data["owner_user_id"])
        _ensure_user_exists(db, owner_user_id)
        job.owner_user_id = owner_user_id

    for field in ("title", "department", "location", "job_description", "requirements", "status"):
        if data.get(field) is not None:
            setattr(job, field, str(data[field]).strip())
    if data.get("headcount") is not None:
        job.headcount = int(data["headcount"])

    job.updated_at = _utc_now_str()
    db.commit()
    db.refresh(job)
    return job_to_dict(job)
