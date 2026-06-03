"""RMS candidates business logic (Phase 2)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type

from fastapi import HTTPException
from sqlalchemy.orm import Session

from auth.service import AuthContext
from schemas.rms import (
    CANDIDATE_EDUCATION_LEVELS,
    CANDIDATE_GENDERS,
    CANDIDATE_MARITAL_STATUSES,
    CANDIDATE_SOURCES,
)
from services import rms_jobs as jobs_svc
from services import rms_scope as rms_ds

PHONE_RE = re.compile(r"^1\d{10}$")


def _utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mask_phone(value: str) -> str:
    s = (value or "").strip()
    if len(s) <= 7:
        return "***"
    return f"{s[:3]}****{s[-4:]}"


def _mask_email(value: str) -> str:
    s = (value or "").strip()
    if "@" not in s:
        return "***"
    local, _, domain = s.partition("@")
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def _mask_wechat(value: str) -> str:
    s = (value or "").strip()
    if len(s) <= 2:
        return "**"
    return f"{s[0]}***{s[-1]}"


def _mask_email_wechat(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    if "@" in s:
        return _mask_email(s)
    return _mask_wechat(s)


def _sync_email_wechat_fields(data: Dict[str, Any]) -> None:
    if "email_wechat" not in data:
        return
    ew = str(data.get("email_wechat") or "").strip()
    data["email_wechat"] = ew
    if ew:
        if "@" in ew:
            data["email"] = ew
        else:
            data["wechat"] = ew


def _normalize_phone(phone: Any, *, required: bool = True) -> str:
    p = str(phone or "").strip()
    if not p:
        if required:
            raise HTTPException(status_code=400, detail="请填写手机号")
        return ""
    if not PHONE_RE.match(p):
        raise HTTPException(status_code=400, detail="手机号须为11位数字且以1开头")
    return p


def _validate_target_open_job(
    db: Session,
    ctx: AuthContext,
    job_id: Any,
    RmsJob: Type[Any],
    Client: Type[Any],
) -> int:
    if job_id is None or job_id == "":
        raise HTTPException(status_code=400, detail="请选择应聘岗位")
    try:
        jid = int(job_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="应聘岗位无效")
    job = jobs_svc.get_job(db, ctx, jid, RmsJob, Client)
    if (job.get("status") or "").strip() != "open":
        raise HTTPException(status_code=400, detail="应聘岗位须为 open 状态")
    return jid


def _validate_candidate_enums(data: Dict[str, Any]) -> None:
    edu = data.get("education_level")
    if edu is not None:
        edu = str(edu).strip()
        if edu and edu not in CANDIDATE_EDUCATION_LEVELS:
            raise HTTPException(status_code=400, detail=f"无效学历: {edu}")
    gender = data.get("gender")
    if gender is not None:
        gender = str(gender).strip()
        if gender and gender not in CANDIDATE_GENDERS:
            raise HTTPException(status_code=400, detail=f"无效性别: {gender}")
    marital = data.get("marital_status")
    if marital is not None:
        marital = str(marital).strip()
        if marital and marital not in CANDIDATE_MARITAL_STATUSES:
            raise HTTPException(status_code=400, detail=f"无效婚姻状况: {marital}")
    source = data.get("source")
    if source is not None:
        source = str(source).strip()
        if source and source not in CANDIDATE_SOURCES:
            raise HTTPException(status_code=400, detail=f"无效来源: {source}")


def _latest_resumes_by_candidate(db: Session, RmsResume: Type[Any], candidate_ids: List[int]) -> Dict[int, Any]:
    if not candidate_ids:
        return {}
    rows = (
        db.query(RmsResume)
        .filter(RmsResume.candidate_id.in_(candidate_ids))
        .order_by(RmsResume.candidate_id, RmsResume.id.desc())
        .all()
    )
    out: Dict[int, Any] = {}
    for row in rows:
        if row.candidate_id not in out:
            out[row.candidate_id] = row
    return out


def _job_titles_by_id(db: Session, job_ids: List[int], RmsJob: Type[Any]) -> Dict[int, str]:
    if not job_ids:
        return {}
    rows = db.query(RmsJob.id, RmsJob.title).filter(RmsJob.id.in_(job_ids)).all()
    return {int(r[0]): str(r[1] or "") for r in rows}


def _client_names_by_id(db: Session, client_ids: List[int], Client: Type[Any]) -> Dict[int, str]:
    if not client_ids:
        return {}
    rows = db.query(Client.id, Client.name).filter(Client.id.in_(client_ids)).all()
    return {int(r[0]): str(r[1] or "") for r in rows}


def candidate_to_dict(
    ctx: AuthContext,
    row: Any,
    *,
    resume_row: Any = None,
    job_title: str = "",
    client_name: str = "",
) -> Dict[str, Any]:
    can_view_contacts = ctx.is_super or "rms.contacts.view" in ctx.permissions
    phone = row.phone or ""
    email = row.email or ""
    wechat = row.wechat or ""
    email_wechat = (row.email_wechat or "").strip()
    if not email_wechat:
        email_wechat = email or wechat
    if not can_view_contacts:
        phone = _mask_phone(phone)
        email = _mask_email(email)
        wechat = _mask_wechat(wechat)
        email_wechat = _mask_email_wechat(email_wechat)
    return {
        "id": row.id,
        "name": row.name or "",
        "age": getattr(row, "age", None) or "",
        "work_years": getattr(row, "work_years", None) or "",
        "phone": phone,
        "email": email,
        "wechat": wechat,
        "email_wechat": email_wechat,
        "target_job_id": getattr(row, "target_job_id", None),
        "target_client_id": getattr(row, "target_client_id", None),
        "target_job_title": job_title,
        "target_client_name": client_name,
        "current_salary": getattr(row, "current_salary", None) or "",
        "expected_salary": getattr(row, "expected_salary", None) or "",
        "available_date": getattr(row, "available_date", None) or "",
        "education_level": getattr(row, "education_level", None) or "",
        "school": getattr(row, "school", None) or "",
        "major": getattr(row, "major", None) or "",
        "gender": getattr(row, "gender", None) or "",
        "marital_status": getattr(row, "marital_status", None) or "",
        "current_company": row.current_company or "",
        "current_title": row.current_title or "",
        "city": row.city or "",
        "source": row.source or "",
        "tags": row.tags or "[]",
        "resume_id": resume_row.id if resume_row else None,
        "resume_file_name": (resume_row.file_name or "") if resume_row else "",
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at or "",
        "updated_at": row.updated_at or "",
    }


def _filtered_candidates_query(
    db: Session,
    ctx: AuthContext,
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
):
    q = db.query(RmsCandidate)
    visible = rms_ds.visible_candidate_ids(db, ctx, RmsCandidate, RmsApplication, Client)
    if visible is not None:
        if not visible:
            q = q.filter(RmsCandidate.id == -1)
        else:
            q = q.filter(RmsCandidate.id.in_(visible))
    return q


def _rows_to_dicts(
    db: Session,
    ctx: AuthContext,
    rows: List[Any],
    *,
    RmsResume: Optional[Type[Any]] = None,
    RmsJob: Optional[Type[Any]] = None,
    Client: Optional[Type[Any]] = None,
) -> List[Dict[str, Any]]:
    ids = [r.id for r in rows]
    resume_map = _latest_resumes_by_candidate(db, RmsResume, ids) if RmsResume else {}
    job_ids = [int(r.target_job_id) for r in rows if getattr(r, "target_job_id", None)]
    client_ids = [int(r.target_client_id) for r in rows if getattr(r, "target_client_id", None)]
    job_titles = _job_titles_by_id(db, job_ids, RmsJob) if RmsJob else {}
    client_names = _client_names_by_id(db, client_ids, Client) if Client else {}
    out: List[Dict[str, Any]] = []
    for row in rows:
        jid = getattr(row, "target_job_id", None)
        cid = getattr(row, "target_client_id", None)
        out.append(
            candidate_to_dict(
                ctx,
                row,
                resume_row=resume_map.get(row.id),
                job_title=job_titles.get(int(jid), "") if jid else "",
                client_name=client_names.get(int(cid), "") if cid else "",
            )
        )
    return out


def list_candidates(
    db: Session,
    ctx: AuthContext,
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
    *,
    RmsResume: Optional[Type[Any]] = None,
    RmsJob: Optional[Type[Any]] = None,
    q_text: Optional[str] = None,
) -> List[Dict[str, Any]]:
    q = _filtered_candidates_query(db, ctx, RmsCandidate, RmsApplication, Client)
    if q_text:
        like = f"%{q_text.strip()}%"
        q = q.filter(RmsCandidate.name.like(like))
    rows = q.order_by(RmsCandidate.id.desc()).all()
    return _rows_to_dicts(
        db,
        ctx,
        rows,
        RmsResume=RmsResume,
        RmsJob=RmsJob,
        Client=Client,
    )


def get_candidate(
    db: Session,
    ctx: AuthContext,
    candidate_id: int,
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
    *,
    RmsResume: Optional[Type[Any]] = None,
    RmsJob: Optional[Type[Any]] = None,
) -> Dict[str, Any]:
    row = _filtered_candidates_query(db, ctx, RmsCandidate, RmsApplication, Client).filter(
        RmsCandidate.id == candidate_id
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="候选人不存在")
    items = _rows_to_dicts(
        db,
        ctx,
        [row],
        RmsResume=RmsResume,
        RmsJob=RmsJob,
        Client=Client,
    )
    return items[0]


def _apply_candidate_fields(row: Any, data: Dict[str, Any]) -> None:
    str_fields = (
        "name", "phone", "email", "wechat", "email_wechat", "age", "work_years",
        "current_salary", "expected_salary", "available_date", "education_level",
        "school", "major", "gender", "marital_status",
        "current_company", "current_title", "city", "source", "tags",
    )
    for field in str_fields:
        if data.get(field) is not None:
            setattr(row, field, str(data[field]).strip())
    if "target_job_id" in data:
        row.target_job_id = data["target_job_id"]
    if "target_client_id" in data:
        row.target_client_id = data["target_client_id"]


def create_candidate(
    db: Session,
    ctx: AuthContext,
    data: Dict[str, Any],
    RmsCandidate: Type[Any],
    *,
    RmsResume: Optional[Type[Any]] = None,
    RmsJob: Optional[Type[Any]] = None,
    Client: Optional[Type[Any]] = None,
    RmsApplication: Optional[Type[Any]] = None,
) -> Dict[str, Any]:
    if RmsJob is None or Client is None:
        raise HTTPException(status_code=500, detail="RMS 岗位校验未配置")
    data["phone"] = _normalize_phone(data.get("phone"), required=True)
    data["target_job_id"] = _validate_target_open_job(
        db, ctx, data.get("target_job_id"), RmsJob, Client
    )
    _validate_candidate_enums(data)
    _sync_email_wechat_fields(data)
    now = _utc_now_str()
    row = RmsCandidate(
        created_by_user_id=ctx.user_id,
        created_at=now,
        updated_at=now,
    )
    _apply_candidate_fields(row, data)
    db.add(row)
    db.commit()
    db.refresh(row)
    if RmsApplication and Client:
        return get_candidate(
            db, ctx, row.id, RmsCandidate, RmsApplication, Client,
            RmsResume=RmsResume, RmsJob=RmsJob,
        )
    return candidate_to_dict(ctx, row)


def update_candidate(
    db: Session,
    ctx: AuthContext,
    candidate_id: int,
    data: Dict[str, Any],
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
    *,
    RmsResume: Optional[Type[Any]] = None,
    RmsJob: Optional[Type[Any]] = None,
) -> Dict[str, Any]:
    row = _filtered_candidates_query(db, ctx, RmsCandidate, RmsApplication, Client).filter(
        RmsCandidate.id == candidate_id
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="候选人不存在")
    if data.get("phone") is not None:
        data["phone"] = _normalize_phone(data.get("phone"), required=False)
    if "target_job_id" in data and data.get("target_job_id") is not None:
        data["target_job_id"] = _validate_target_open_job(
            db, ctx, data["target_job_id"], RmsJob, Client
        )
    _validate_candidate_enums(data)
    _sync_email_wechat_fields(data)
    _apply_candidate_fields(row, data)
    row.updated_at = _utc_now_str()
    db.commit()
    db.refresh(row)
    return get_candidate(
        db, ctx, candidate_id, RmsCandidate, RmsApplication, Client,
        RmsResume=RmsResume, RmsJob=RmsJob,
    )


def delete_candidate(
    db: Session,
    ctx: AuthContext,
    candidate_id: int,
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
    *,
    upload_dir: str,
    RmsResume: Optional[Type[Any]] = None,
) -> Dict[str, Any]:
    row = _filtered_candidates_query(db, ctx, RmsCandidate, RmsApplication, Client).filter(
        RmsCandidate.id == candidate_id
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="候选人不存在")
    app_count = (
        db.query(RmsApplication)
        .filter(RmsApplication.candidate_id == candidate_id)
        .count()
    )
    if app_count:
        raise HTTPException(status_code=409, detail="该候选人有关联推荐记录，无法删除")
    if RmsResume is not None:
        import os

        import security_foundation as sec

        resumes = db.query(RmsResume).filter(RmsResume.candidate_id == candidate_id).all()
        for resume in resumes:
            rel = (resume.file_path or "").strip()
            if rel:
                try:
                    abs_path = sec.resolve_upload_path(upload_dir, rel)
                    if os.path.isfile(abs_path):
                        os.remove(abs_path)
                except (ValueError, OSError):
                    pass
            db.delete(resume)
    db.delete(row)
    db.commit()
    return {"ok": True, "id": candidate_id}
