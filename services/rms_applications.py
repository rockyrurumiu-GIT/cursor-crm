"""RMS applications business logic (Phase 2)."""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple, Type

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth.service import AuthContext
from schemas.rms import ALLOWED_TRANSITIONS, APPLICATION_TERMINAL
from services import rms_scope as rms_ds
from services.rms_resumes import MAX_RESUME_BYTES

PARSE_DRAFT_ALLOWED_SUFFIXES = frozenset({".pdf", ".txt", ".rtf"})
PARSE_DRAFT_WORD_SUFFIXES = frozenset({".doc", ".docx"})
PARSE_DRAFT_TEXT_MAX = 2000
_WORD_UNSUPPORTED_MSG = "Word 文档暂不支持自动解析，请手动填写或上传 PDF/TXT"

_RE_PHONE = re.compile(r"1[3-9]\d{9}")
_RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_RE_NAME = re.compile(r"姓名\s*[:：]\s*(\S+)")
_RE_AGE = re.compile(r"年龄\s*[:：]\s*(\d{1,2})")
_RE_WORK_YEARS = re.compile(r"工作年限\s*[:：]\s*(\d+\s*年?)")
_RE_CURRENT_SALARY = re.compile(r"(?:当前薪资|目前薪资|现薪资)\s*[:：]\s*([^\n\r]{1,40})")
_RE_EXPECTED_SALARY = re.compile(r"(?:期望薪资|期望工资|期望薪酬)\s*[:：]\s*([^\n\r]{1,40})")
_RE_EDUCATION = re.compile(r"(博士研究生|博士|硕士研究生|硕士|本科|大专|专科|高中|中专|MBA|EMBA)")
_RE_SCHOOL = re.compile(r"(?:毕业院校|学校|院校)\s*[:：]\s*([^\n\r]{2,40})")
_RE_MAJOR = re.compile(r"专业\s*[:：]\s*([^\n\r]{2,40})")
_RE_GENDER = re.compile(r"性别\s*[:：]\s*(男|女)")


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


def _extract_pdf_text(content: bytes) -> str:
    text = ""
    try:
        import fitz
    except ImportError:
        fitz = None  # type: ignore[assignment]
    if fitz is not None:
        try:
            doc = fitz.open(stream=content, filetype="pdf")
            try:
                parts: List[str] = []
                for i in range(len(doc)):
                    try:
                        parts.append(doc.load_page(i).get_text() or "")
                    except Exception:
                        parts.append("")
                text = "\n".join(parts).strip()
            finally:
                try:
                    doc.close()
                except Exception:
                    pass
        except Exception:
            text = ""
    if text:
        return text
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                parts.append("")
        return "\n".join(parts).strip()
    except Exception:
        return ""


def _extract_resume_text(file_name: str, content: bytes) -> Tuple[str, Optional[str]]:
    ext = os.path.splitext(file_name or "")[1].lower()
    if ext in PARSE_DRAFT_WORD_SUFFIXES:
        return "", _WORD_UNSUPPORTED_MSG
    if ext not in PARSE_DRAFT_ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="该文件类型不支持自动解析")
    if ext == ".pdf":
        return _extract_pdf_text(content), None
    return content.decode("utf-8", errors="replace").strip(), None


def _first_match(pattern: re.Pattern[str], text: str) -> str:
    m = pattern.search(text)
    if not m:
        return ""
    return (m.group(1) if m.lastindex else m.group(0)).strip()


def _normalize_work_years(raw: str) -> str:
    val = (raw or "").strip()
    if not val:
        return ""
    if val.endswith("年"):
        return val.replace(" ", "")
    return f"{val}年"


def _extract_draft_fields_from_text(text: str) -> Dict[str, str]:
    src = (text or "").strip()
    fields: Dict[str, str] = {}
    if not src:
        return fields

    phone_m = _RE_PHONE.search(src)
    if phone_m:
        fields["phone"] = phone_m.group(0)

    email_m = _RE_EMAIL.search(src)
    if email_m:
        fields["email_wechat"] = email_m.group(0)

    name = _first_match(_RE_NAME, src)
    if name:
        fields["name"] = name

    age = _first_match(_RE_AGE, src)
    if age:
        fields["age"] = age

    work_years = _first_match(_RE_WORK_YEARS, src)
    if work_years:
        fields["work_years"] = _normalize_work_years(work_years)

    current_salary = _first_match(_RE_CURRENT_SALARY, src)
    if current_salary:
        fields["current_salary"] = current_salary

    expected_salary = _first_match(_RE_EXPECTED_SALARY, src)
    if expected_salary:
        fields["expected_salary"] = expected_salary

    edu_m = _RE_EDUCATION.search(src)
    if edu_m:
        fields["education_level"] = edu_m.group(1)

    school = _first_match(_RE_SCHOOL, src)
    if school:
        fields["school"] = school

    major = _first_match(_RE_MAJOR, src)
    if major:
        fields["major"] = major

    gender = _first_match(_RE_GENDER, src)
    if gender:
        fields["gender"] = gender

    return fields


def parse_resume_draft(file_name: str, content: bytes) -> Dict[str, Any]:
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=400, detail="简历文件不能超过 10MB")

    text, word_msg = _extract_resume_text(file_name, content)
    if word_msg:
        return {"draft_fields": {}, "parsed_text": "", "message": word_msg}

    parsed_text = text[:PARSE_DRAFT_TEXT_MAX] if text else ""
    draft_fields = _extract_draft_fields_from_text(text)
    return {"draft_fields": draft_fields, "parsed_text": parsed_text, "message": ""}
