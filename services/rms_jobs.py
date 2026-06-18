"""RMS jobs business logic (Phase 2)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Type

from fastapi import HTTPException
from sqlalchemy import case, func, text
from sqlalchemy.orm import Session

from auth import service as auth_svc
from auth.service import AuthContext
from schemas.rms import (
    JOB_ACTIVE_RECOMMENDATION_RAW_STATUSES,
    JOB_PRIORITIES,
    JOB_SALARY_CAP_MAX,
    JOB_SALARY_CAP_MIN,
    JOB_STATUSES,
    JOB_WRITABLE_STR_FIELDS,
    normalize_rms_date,
    utc_date_str,
)
from services import rms_scope as rms_ds

def _ensure_user_exists(db: Session, user_id: int) -> None:
    row = db.execute(text("SELECT 1 FROM sys_user WHERE id = :uid LIMIT 1"), {"uid": user_id}).fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="用户不存在")


def _user_label(db: Session, user_id: Optional[int]) -> str:
    if user_id is None:
        return ""
    row = db.execute(
        text("SELECT username, display_name FROM sys_user WHERE id = :uid"),
        {"uid": user_id},
    ).fetchone()
    if not row:
        return ""
    dn = str(row[1] or "").strip()
    un = str(row[0] or "").strip()
    return dn or un


def _validate_job_enums(data: Dict[str, Any]) -> None:
    status = data.get("status")
    if status is not None:
        status = str(status).strip()
        if status and status not in JOB_STATUSES:
            raise HTTPException(status_code=400, detail=f"无效状态: {status}")
    priority = data.get("priority")
    if priority is not None:
        priority = str(priority).strip()
        if priority and priority not in JOB_PRIORITIES:
            raise HTTPException(status_code=400, detail=f"无效优先级: {priority}")


def _validate_salary_cap(data: Dict[str, Any]) -> None:
    if "salary_cap" not in data:
        return
    raw = str(data.get("salary_cap") or "").replace(",", "").strip()
    if not raw:
        data["salary_cap"] = ""
        return
    if not raw.isdigit():
        raise HTTPException(status_code=400, detail="薪资帽须为整数，不支持字母或特殊符号")
    value = int(raw)
    if value < JOB_SALARY_CAP_MIN or value > JOB_SALARY_CAP_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"薪资帽须在 {JOB_SALARY_CAP_MIN:,}–{JOB_SALARY_CAP_MAX:,} 之间",
        )
    data["salary_cap"] = str(value)


def _job_core_dict(job: Any) -> Dict[str, Any]:
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
        "priority": getattr(job, "priority", None) or "medium",
        "salary_cap": getattr(job, "salary_cap", None) or "",
        "years_required": getattr(job, "years_required", None) or "",
        "education": getattr(job, "education", None) or "",
        "overtime_travel": getattr(job, "overtime_travel", None) or "",
        "interviewer": getattr(job, "interviewer", None) or "",
        "note": getattr(job, "note", None) or "",
        "owner_user_id": job.owner_user_id,
        "created_at": normalize_rms_date(job.created_at),
        "updated_at": normalize_rms_date(job.updated_at),
    }


def job_to_dict(
    job: Any,
    *,
    client: Any = None,
    db: Optional[Session] = None,
    recommendation_counts: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    d = _job_core_dict(job)
    sales_uid = None
    delivery_uid = None
    client_name = ""
    if client is not None:
        client_name = str(getattr(client, "name", None) or "")
        sales_uid = getattr(client, "owner_user_id", None)
        delivery_uid = getattr(client, "delivery_owner_user_id", None)
    d["client_name"] = client_name
    d["sales_owner_user_id"] = sales_uid
    d["delivery_owner_user_id"] = delivery_uid
    d["recruitment_owner_user_id"] = job.owner_user_id
    if db is not None:
        d["sales_owner_label"] = _user_label(db, sales_uid)
        d["delivery_owner_label"] = _user_label(db, delivery_uid)
        d["recruitment_owner_label"] = _user_label(db, job.owner_user_id)
    else:
        d["sales_owner_label"] = ""
        d["delivery_owner_label"] = ""
        d["recruitment_owner_label"] = ""
    counts = recommendation_counts or {}
    d["active_recommendation_count"] = int(counts.get("active_recommendation_count", 0) or 0)
    d["historical_recommendation_count"] = int(counts.get("historical_recommendation_count", 0) or 0)
    return d


def _clients_by_id(db: Session, Client: Type[Any], client_ids: Set[int]) -> Dict[int, Any]:
    if not client_ids:
        return {}
    rows = db.query(Client).filter(Client.id.in_(client_ids)).all()
    return {int(c.id): c for c in rows}


def _application_recommendation_counts_by_job(
    db: Session,
    ctx: AuthContext,
    RmsApplication: Type[Any],
    Client: Type[Any],
    job_ids: Set[int],
) -> Dict[int, Dict[str, int]]:
    if not job_ids:
        return {}
    active_case = case(
        (RmsApplication.status.in_(tuple(JOB_ACTIVE_RECOMMENDATION_RAW_STATUSES)), 1),
        else_=0,
    )
    q = rms_ds.scoped_applications_query(db, ctx, RmsApplication, Client, action="read")
    rows = (
        q.filter(RmsApplication.job_id.in_(job_ids))
        .with_entities(
            RmsApplication.job_id,
            func.count(RmsApplication.id).label("total"),
            func.sum(active_case).label("active"),
        )
        .group_by(RmsApplication.job_id)
        .all()
    )
    out: Dict[int, Dict[str, int]] = {}
    for job_id, total, active in rows:
        out[int(job_id)] = {
            "active_recommendation_count": int(active or 0),
            "historical_recommendation_count": int(total or 0),
        }
    return out


def list_jobs(
    db: Session,
    ctx: AuthContext,
    RmsJob: Type[Any],
    Client: Type[Any],
    RmsApplication: Type[Any],
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
    client_map = _clients_by_id(db, Client, {int(r.client_id) for r in rows if r.client_id is not None})
    job_ids = {int(r.id) for r in rows}
    count_map = _application_recommendation_counts_by_job(db, ctx, RmsApplication, Client, job_ids)
    return [
        job_to_dict(
            r,
            client=client_map.get(int(r.client_id)),
            db=db,
            recommendation_counts=count_map.get(int(r.id)),
        )
        for r in rows
    ]


def get_job(
    db: Session,
    ctx: AuthContext,
    job_id: int,
    RmsJob: Type[Any],
    Client: Type[Any],
    RmsApplication: Optional[Type[Any]] = None,
) -> Dict[str, Any]:
    row = rms_ds.scoped_jobs_query(db, ctx, RmsJob, Client, action="read").filter(RmsJob.id == job_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="岗位不存在")
    client = db.query(Client).filter(Client.id == row.client_id).first()
    count_map: Dict[int, Dict[str, int]] = {}
    if RmsApplication is not None:
        count_map = _application_recommendation_counts_by_job(
            db, ctx, RmsApplication, Client, {int(job_id)}
        )
    return job_to_dict(row, client=client, db=db, recommendation_counts=count_map.get(int(job_id)))


def _apply_client_owners_from_job_data(db: Session, client: Any, data: Dict[str, Any]) -> None:
    sales_owner_user_id = data.get("sales_owner_user_id")
    if sales_owner_user_id is not None:
        sales_owner_user_id = int(sales_owner_user_id)
        _ensure_user_exists(db, sales_owner_user_id)
        client.owner_user_id = sales_owner_user_id

    owner_user_id = data.get("owner_user_id")
    if owner_user_id is not None:
        owner_user_id = int(owner_user_id)
        _ensure_user_exists(db, owner_user_id)
        client.recruitment_owner_user_id = owner_user_id
        _, primary_dept = auth_svc.get_user_dept_ids(db, owner_user_id)
        if primary_dept is not None:
            client.recruitment_dept_id = primary_dept


def create_job(
    db: Session,
    ctx: AuthContext,
    data: Dict[str, Any],
    RmsJob: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
) -> Dict[str, Any]:
    _validate_job_enums(data)
    _validate_salary_cap(data)
    client_id = int(data["client_id"])
    owner_user_id = int(data["owner_user_id"])
    _ensure_user_exists(db, owner_user_id)

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="客户不存在")

    existing_count = db.query(RmsJob).filter(RmsJob.client_id == client_id).count()

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

    _apply_client_owners_from_job_data(db, client, data)

    now = utc_date_str()
    job_kwargs: Dict[str, Any] = {
        "client_id": client_id,
        "owner_user_id": owner_user_id,
        "headcount": int(data.get("headcount") or 1),
        "created_at": now,
        "updated_at": now,
    }
    for field in JOB_WRITABLE_STR_FIELDS:
        if field in data:
            job_kwargs[field] = str(data.get(field) or "").strip()
        else:
            default = "open" if field == "status" else "medium" if field == "priority" else ""
            job_kwargs[field] = default

    job = RmsJob(**job_kwargs)
    db.add(job)
    db.commit()
    db.refresh(job)
    db.refresh(client)
    return job_to_dict(job, client=client, db=db)


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
    _validate_job_enums(data)
    _validate_salary_cap(data)
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

    for field in JOB_WRITABLE_STR_FIELDS:
        if data.get(field) is not None:
            setattr(job, field, str(data[field]).strip())
    if data.get("headcount") is not None:
        job.headcount = int(data["headcount"])

    job.updated_at = utc_date_str()
    db.commit()
    db.refresh(job)
    client = db.query(Client).filter(Client.id == job.client_id).first()
    return job_to_dict(job, client=client, db=db)
