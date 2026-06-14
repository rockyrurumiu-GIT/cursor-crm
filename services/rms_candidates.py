"""RMS candidates business logic (Phase 2)."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Type

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from auth.service import AuthContext
from schemas.rms import (
    CANDIDATE_EDUCATION_LEVELS,
    CANDIDATE_GENDERS,
    CANDIDATE_MARITAL_STATUSES,
    CANDIDATE_SOURCE_PRESETS,
    normalize_rms_date,
    utc_date_str,
)
from services import rms_jobs as jobs_svc
from services import rms_scope as rms_ds

PHONE_RE = re.compile(r"^1\d{10}$")

_CANDIDATE_CREATE_REQUIRED = (
    ("name", "姓名"),
    ("city", "城市"),
    ("current_salary", "当前薪资"),
    ("expected_salary", "期望薪资"),
    ("age", "年龄"),
    ("work_years", "年限"),
    ("email_wechat", "邮箱/微信"),
    ("available_date", "到岗时间"),
    ("education_level", "学历"),
    ("source", "来源"),
    ("school", "学校"),
    ("major", "专业"),
    ("gender", "性别"),
    ("marital_status", "婚姻状况"),
)

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


_RESUME_PARSE_SUMMARY_KEYS = (
    "name",
    "age",
    "work_years",
    "school",
    "major",
    "education_level",
    "city",
    "current_company",
    "current_title",
    "gender",
    "marital_status",
    "source",
    "phone",
    "email",
    "wechat",
    "email_wechat",
)


def _latest_resume_parse_summary(resume_row: Any, *, can_view_contacts: bool) -> Dict[str, str]:
    if not resume_row:
        return {}
    try:
        raw = json.loads(resume_row.parsed_json or "{}")
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    summary = {
        k: str(raw.get(k) or "").strip()
        for k in _RESUME_PARSE_SUMMARY_KEYS
        if str(raw.get(k) or "").strip()
    }
    if not summary:
        return {}
    if not can_view_contacts:
        if "phone" in summary:
            summary["phone"] = _mask_phone(summary["phone"])
        if "email" in summary:
            summary["email"] = _mask_email(summary["email"])
        if "wechat" in summary:
            summary["wechat"] = _mask_wechat(summary["wechat"])
        if "email_wechat" in summary:
            summary["email_wechat"] = _mask_email_wechat(summary["email_wechat"])
    return summary


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
        if source == "其他":
            raise HTTPException(status_code=400, detail="请填写具体来源")
        if source and source not in CANDIDATE_SOURCE_PRESETS and len(source) > 64:
            raise HTTPException(status_code=400, detail="来源过长")


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


def _strip_salary_field(value: Any) -> str:
    return str(value or "").replace(",", "").strip()


def validate_candidate_create_payload(data: Dict[str, Any]) -> None:
    for key, label in _CANDIDATE_CREATE_REQUIRED:
        if key in ("current_salary", "expected_salary"):
            val = _strip_salary_field(data.get(key))
        else:
            val = str(data.get(key) or "").strip()
        if not val:
            raise HTTPException(status_code=400, detail=f"请填写{label}")


def _find_duplicate_candidate(
    db: Session,
    RmsCandidate: Type[Any],
    *,
    name: str,
    phone: str,
) -> Optional[Any]:
    if not name or not phone:
        return None
    return (
        db.query(RmsCandidate)
        .filter(
            RmsCandidate.name == name,
            RmsCandidate.phone == phone,
        )
        .first()
    )


def detect_duplicate_candidate(
    db: Session,
    RmsCandidate: Type[Any],
    *,
    name: str,
    phone: str,
) -> bool:
    """True when name+phone match an existing candidate (same rules as create)."""
    name = str(name or "").strip()
    if not name:
        return False
    try:
        normalized_phone = _normalize_phone(phone, required=False)
    except HTTPException:
        return False
    if not normalized_phone:
        return False
    return _find_duplicate_candidate(
        db, RmsCandidate, name=name, phone=normalized_phone
    ) is not None


def detect_duplicate_candidate_for_parse(
    db: Session,
    RmsCandidate: Type[Any],
    *,
    name: str,
    phone: str,
) -> bool:
    """Parse-time hint: name+phone match, or phone alone matches an existing row."""
    if detect_duplicate_candidate(db, RmsCandidate, name=name, phone=phone):
        return True
    try:
        normalized_phone = _normalize_phone(phone, required=False)
    except HTTPException:
        return False
    if not normalized_phone:
        return False
    return (
        db.query(RmsCandidate)
        .filter(RmsCandidate.phone == normalized_phone)
        .first()
    ) is not None


def _recommended_at_by_candidate(
    db: Session,
    RmsApplication: Type[Any],
    rows: List[Any],
) -> Dict[int, str]:
    candidate_ids = [r.id for r in rows]
    if not candidate_ids:
        return {}
    app_rows = (
        db.query(RmsApplication)
        .filter(RmsApplication.candidate_id.in_(candidate_ids))
        .order_by(RmsApplication.candidate_id, RmsApplication.id.desc())
        .all()
    )
    apps_by_candidate: Dict[int, List[Any]] = {}
    for app in app_rows:
        apps_by_candidate.setdefault(app.candidate_id, []).append(app)
    target_job_by_candidate = {
        r.id: getattr(r, "target_job_id", None) for r in rows
    }
    out: Dict[int, str] = {}
    for cid in candidate_ids:
        apps = apps_by_candidate.get(cid, [])
        if not apps:
            continue
        target_job_id = target_job_by_candidate.get(cid)
        chosen = None
        if target_job_id:
            for app in apps:
                if app.job_id == target_job_id:
                    chosen = app
                    break
        if chosen is None:
            chosen = apps[0]
        rec_at = (chosen.recommended_at or "").strip()
        if rec_at:
            out[cid] = rec_at
    return out


def candidate_to_dict(
    ctx: AuthContext,
    row: Any,
    *,
    resume_row: Any = None,
    job_title: str = "",
    client_name: str = "",
    recommended_at: str = "",
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
        "available_date": normalize_rms_date(getattr(row, "available_date", None)),
        "education_level": getattr(row, "education_level", None) or "",
        "school": getattr(row, "school", None) or "",
        "major": getattr(row, "major", None) or "",
        "gender": getattr(row, "gender", None) or "",
        "marital_status": getattr(row, "marital_status", None) or "",
        "current_company": row.current_company or "",
        "current_title": row.current_title or "",
        "city": row.city or "",
        "source": row.source or "",
        "recommended_at": normalize_rms_date(recommended_at),
        "tags": row.tags or "[]",
        "resume_id": resume_row.id if resume_row else None,
        "resume_file_name": (resume_row.file_name or "") if resume_row else "",
        "created_by_user_id": row.created_by_user_id,
        "created_at": normalize_rms_date(row.created_at),
        "updated_at": normalize_rms_date(row.updated_at),
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


def _apply_candidate_keyword_search(
    db: Session,
    q: Any,
    q_text: Optional[str],
    ctx: AuthContext,
    RmsCandidate: Type[Any],
    *,
    RmsResume: Optional[Type[Any]] = None,
    RmsJob: Optional[Type[Any]] = None,
    Client: Optional[Type[Any]] = None,
) -> Any:
    keyword = (q_text or "").strip()
    if not keyword:
        return q
    like = f"%{keyword}%"
    conditions = [
        RmsCandidate.name.like(like),
        RmsCandidate.city.like(like),
        RmsCandidate.source.like(like),
        RmsCandidate.education_level.like(like),
        RmsCandidate.school.like(like),
        RmsCandidate.major.like(like),
        RmsCandidate.current_company.like(like),
        RmsCandidate.current_title.like(like),
    ]
    if RmsJob is not None:
        job_ids = db.query(RmsJob.id).filter(RmsJob.title.like(like))
        conditions.append(RmsCandidate.target_job_id.in_(job_ids))
    if Client is not None:
        client_ids = db.query(Client.id).filter(Client.name.like(like))
        conditions.append(RmsCandidate.target_client_id.in_(client_ids))
    can_view_contacts = ctx.is_super or "rms.contacts.view" in ctx.permissions
    if can_view_contacts and RmsResume is not None:
        resume_cids = db.query(RmsResume.candidate_id).filter(RmsResume.parsed_text.like(like))
        conditions.append(RmsCandidate.id.in_(resume_cids))
    return q.filter(or_(*conditions))


def _rows_to_dicts(
    db: Session,
    ctx: AuthContext,
    rows: List[Any],
    *,
    RmsResume: Optional[Type[Any]] = None,
    RmsJob: Optional[Type[Any]] = None,
    Client: Optional[Type[Any]] = None,
    RmsApplication: Optional[Type[Any]] = None,
    resume_map: Optional[Dict[int, Any]] = None,
) -> List[Dict[str, Any]]:
    ids = [r.id for r in rows]
    if resume_map is None:
        resume_map = _latest_resumes_by_candidate(db, RmsResume, ids) if RmsResume else {}
    recommended_map = (
        _recommended_at_by_candidate(db, RmsApplication, rows) if RmsApplication else {}
    )
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
                recommended_at=recommended_map.get(row.id, ""),
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
    q = _apply_candidate_keyword_search(
        db,
        q,
        q_text,
        ctx,
        RmsCandidate,
        RmsResume=RmsResume,
        RmsJob=RmsJob,
        Client=Client,
    )
    rows = q.order_by(RmsCandidate.id.desc()).all()
    return _rows_to_dicts(
        db,
        ctx,
        rows,
        RmsResume=RmsResume,
        RmsJob=RmsJob,
        Client=Client,
        RmsApplication=RmsApplication,
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
    resume_map = _latest_resumes_by_candidate(db, RmsResume, [row.id]) if RmsResume else {}
    items = _rows_to_dicts(
        db,
        ctx,
        [row],
        RmsResume=RmsResume,
        RmsJob=RmsJob,
        Client=Client,
        RmsApplication=RmsApplication,
        resume_map=resume_map,
    )
    result = items[0]
    can_view_contacts = ctx.is_super or "rms.contacts.view" in ctx.permissions
    result["latest_resume_parse_summary"] = _latest_resume_parse_summary(
        resume_map.get(row.id),
        can_view_contacts=can_view_contacts,
    )
    return result


def _apply_candidate_fields(row: Any, data: Dict[str, Any]) -> None:
    str_fields = (
        "name", "phone", "email", "wechat", "email_wechat", "age", "work_years",
        "current_salary", "expected_salary", "available_date", "education_level",
        "school", "major", "gender", "marital_status",
        "current_company", "current_title", "city", "source", "tags",
    )
    for field in str_fields:
        if data.get(field) is not None:
            val = str(data[field]).strip()
            if field == "available_date":
                val = normalize_rms_date(val)
            setattr(row, field, val)
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
    data["name"] = str(data.get("name") or "").strip()
    data["phone"] = _normalize_phone(data.get("phone"), required=True)
    validate_candidate_create_payload(data)
    raw_job = data.get("target_job_id")
    if raw_job is None or raw_job == "":
        data["target_job_id"] = None
    else:
        data["target_job_id"] = _validate_target_open_job(
            db, ctx, raw_job, RmsJob, Client
        )
    _validate_candidate_enums(data)
    _sync_email_wechat_fields(data)
    if _find_duplicate_candidate(
        db, RmsCandidate, name=data["name"], phone=data["phone"]
    ):
        raise HTTPException(status_code=409, detail="人选已存在系统中")
    now = utc_date_str()
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
    if "target_job_id" in data:
        raw = data.get("target_job_id")
        if raw is None or raw == "":
            data["target_job_id"] = None
        else:
            try:
                jid = int(raw)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="应聘岗位无效")
            current = int(row.target_job_id) if row.target_job_id is not None else None
            if jid != current:
                data["target_job_id"] = _validate_target_open_job(
                    db, ctx, jid, RmsJob, Client
                )
            else:
                data["target_job_id"] = jid
    _validate_candidate_enums(data)
    _sync_email_wechat_fields(data)
    _apply_candidate_fields(row, data)
    row.updated_at = utc_date_str()
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
