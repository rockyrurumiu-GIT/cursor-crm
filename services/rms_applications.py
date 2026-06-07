"""RMS applications business logic (Phase 2)."""
from __future__ import annotations

import os
import re
from datetime import date
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple, Type

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth.service import AuthContext
from schemas.rms import (
    ALLOWED_TRANSITIONS,
    APPLICATION_PROGRESS_STATUSES,
    APPLICATION_TERMINAL,
    is_pipeline_eligible_application,
    normalize_application_status,
    normalize_rms_date,
    utc_date_str,
    validate_hired_at,
    validate_status_correction_note,
)
from services import rms_scope as rms_ds
from services.rms_resumes import MAX_RESUME_BYTES

PARSE_DRAFT_ALLOWED_SUFFIXES = frozenset({".pdf", ".txt", ".rtf"})
PARSE_DRAFT_WORD_SUFFIXES = frozenset({".doc", ".docx"})
PARSE_DRAFT_TEXT_MAX = 2000
_WORD_UNSUPPORTED_MSG = "Word 文档暂不支持自动解析，请手动填写或上传 PDF/TXT"

_RE_PHONE = re.compile(r"1[3-9]\d{9}")
_RE_PHONE_LABEL = re.compile(
    r"(?:手机|电话|联系电话|mobile|tel)\s*[:：]?\s*([0-9][0-9\s\-()]{10,24})",
    re.IGNORECASE,
)
_RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_RE_NAME = re.compile(
    r"姓名\s*[:：]\s*([^\n\r:：|｜,，;；\d]{2,20}?)"
    r"(?=(?:\s*(?:电话|手机|mobile|tel|email|邮箱|微信|性别|年龄|工作年限|年限)\s*[:：])"
    r"|[\s,，;；|｜]|$)",
    re.IGNORECASE,
)
_RE_AGE = re.compile(r"年龄\s*[:：]\s*(\d{1,2})")
_RE_AGE_PROFILE = re.compile(r"(?:男|女)\s*[|｜]\s*(\d{1,2})\s*岁")
_RE_AGE_PROFILE_BARE = re.compile(r"(?:男|女)\s*[|｜]\s*(\d{1,2})(?:\s*[|｜]|$)")
_RE_AGE_PIPE = re.compile(r"[|｜]\s*(\d{1,2})\s*岁\s*[|｜]")
_RE_AGE_GENDER_NEAR = re.compile(r"(?:男|女)[^|\n]{0,20}(\d{1,2})\s*岁")
_RE_AGE_LOOSE = re.compile(r"(?<![0-9])(\d{1,2})\s*岁(?!\s*(?:工作|以上)?经验)")
_RE_GENDER_PROFILE = re.compile(r"(?:^|[|｜]\s*)(男|女)(?:\s*[|｜])")
_RE_NAME_STANDALONE = re.compile(r"^[\u4e00-\u9fa5·]{2,6}$")
_RE_PROFILE_LINE = re.compile(
    r"(?:男|女).*(?:\d{1,2}岁|1[3-9]\d{9})|"
    r"(?:\d{1,2}岁|1[3-9]\d{9}).*(?:男|女)|"
    r"^(?:男|女)\s*[|｜]\s*\d{1,2}(?:\s*[|｜]|$)",
    re.MULTILINE,
)
_NAME_HEADER_SKIP = frozenset({
    "个人信息",
    "基本资料",
    "联系方式",
    "求职意向",
    "自我评价",
    "工作经历",
    "工作经验",
    "教育经历",
    "教育背景",
    "项目经历",
})
_RE_WORK_YEARS_LABEL = re.compile(
    r"工作年限\s*[:：]\s*(\d+\s*(?:年(?:以上)?)?)"
)
_RE_WORK_YEARS_EXPERIENCE = re.compile(
    r"(?<![0-9])(\d+\s*年(?:以上)?)\s*(?:工作)?经验"
)
_DATE_TOKEN = r"(?:\d{4}[./]\d{1,2}|\d{4}年\d{1,2}月?)"
_END_TOKEN = rf"(?:至今|现在|present|current|{_DATE_TOKEN})"
WORK_PERIOD_RE = re.compile(
    rf"(?P<start>{_DATE_TOKEN})\s*(?:[-—–~至]\s*)?(?P<end>{_END_TOKEN})",
    re.IGNORECASE,
)
_WORK_SECTION_START = re.compile(
    r"^(?:工作经历|工作经验|项目经历|实习经历|自我描述)\s*$"
)
_WORK_SECTION_STOP = re.compile(
    r"^(?:教育(?:背景|经历)|工作经历|工作经验|项目经历|实习经历|自我描述|"
    r"专业技能|自我评价|毕业论文|毕业设计)\s*$"
)
_RE_CURRENT_SALARY = re.compile(r"(?:当前薪资|目前薪资|现薪资)\s*[:：]\s*([^\n\r]{1,40})")
_RE_EXPECTED_SALARY = re.compile(r"(?:期望薪资|期望工资|期望薪酬)\s*[:：]\s*([^\n\r]{1,40})")
_RE_EDUCATION = re.compile(r"(博士研究生|博士|硕士研究生|硕士|本科|大专|专科|高中|中专|MBA|EMBA)")
_RE_SCHOOL = re.compile(r"(?:毕业院校|学校|院校)\s*[:：]\s*([^\n\r]{2,40})")
_RE_MAJOR = re.compile(r"专业\s*[:：]\s*([^\n\r]{2,40})")
_RE_GENDER = re.compile(r"性别\s*[:：]\s*(男|女)")

SCHOOL_ENTITY_RE = re.compile(
    r"([\u4e00-\u9fa5A-Za-z](?:[\u4e00-\u9fa5A-Za-z0-9·\s]{0,38}[\u4e00-\u9fa5A-Za-z0-9·])?(?:大学|学院|学校))"
)
_EDU_BLOCK_START = re.compile(r"^教育\s*(?:背景|经历)\s*[:：]?\s*$")
_EDU_BLOCK_STOP = re.compile(
    r"^(?:工作经历|项目经历|专业技能|自我评价|毕业论文|毕业设计)"
)
_DATE_RANGE_RE = re.compile(
    r"\d{4}[./年]\d{1,2}\s*[-—–~至]+\s*\d{4}[./年]\d{1,2}"
)
_YEAR_ONLY_RANGE_RE = re.compile(r"\d{4}\s*[-—–~至]+\s*\d{4}")
_DEGREE_INLINE = re.compile(
    r"[|｜]\s*(博士研究生|博士|硕士研究生|硕士|本科|大专|专科|学士)"
)
_SKILL_LINE = re.compile(r"^(?:\d+[.、)]\s*)?(?:熟悉|精通|掌握|负责|参与|具有|具备)")
_DEGREE_IN_PARENS = re.compile(r"[（(]([^）)]+)[）)]")
_DEGREE_ONLY_LINE = re.compile(
    r"^(?:博士研究生|博士|硕士研究生|硕士|本科|大专|专科|学士)\s*$"
)
_FIELD_LABEL_SPLIT = re.compile(
    r"(?:电话|手机|mobile|tel|email|邮箱|微信|性别|年龄|工作年限|年限)\s*[:：]?",
    re.IGNORECASE,
)
_FIELD_BOUNDARY = "\uE000"

_RE_CJK = re.compile(r"[\u4e00-\u9fff]")
_RE_TRACKING_LINE = re.compile(r"^[A-Za-z0-9\-]{20,}$")
_RE_WATERMARK_LINE = re.compile(r"^(?:试用水印|水印)\s*$")


def _collapse_chinese_spaces(text: str) -> str:
    src = text or ""
    protected = re.sub(
        r"(?<=[\u4e00-\u9fa5])\s*(?=(?:电话|手机|邮箱|微信|性别|年龄|email|mobile|tel)\s*[:：])",
        _FIELD_BOUNDARY,
        src,
        flags=re.IGNORECASE,
    )
    collapsed = re.sub(r"(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])", "", protected)
    return collapsed.replace(_FIELD_BOUNDARY, " ")


def _normalize_resume_line(line: str) -> str:
    return _collapse_chinese_spaces(re.sub(r"[ \t]+", " ", (line or "").strip()))


def _normalize_resume_digits(text: str) -> str:
    return (text or "").translate(str.maketrans("０１２３４５６７８９", "0123456789"))


def _normalize_resume_text(text: str) -> str:
    normalized = _normalize_resume_digits(text)
    return "\n".join(_normalize_resume_line(line) for line in normalized.splitlines())


def _normalize_school_name(name: str) -> str:
    val = _collapse_chinese_spaces(re.sub(r"\s+", "", (name or "").strip()))
    return re.sub(r"^[\d.\-/年月至—–~ ]+", "", val)


def _search_school_entity(text: str) -> Optional[re.Match[str]]:
    if not text:
        return None
    normalized = _collapse_chinese_spaces(text.strip())
    match = SCHOOL_ENTITY_RE.search(normalized)
    if match:
        return match
    compact = re.sub(r"\s+", "", text)
    return SCHOOL_ENTITY_RE.search(compact)


def application_to_dict(row: Any) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "id": row.id,
        "job_id": row.job_id,
        "candidate_id": row.candidate_id,
        "client_id": row.client_id,
        "resume_id": row.resume_id,
        "status": row.status or "",
        "recommended_by": row.recommended_by,
        "recommended_at": normalize_rms_date(row.recommended_at),
        "current_stage": row.current_stage or "",
        "last_activity_at": normalize_rms_date(row.last_activity_at),
        "created_at": normalize_rms_date(row.created_at),
        "updated_at": normalize_rms_date(row.updated_at),
        "receive_status": getattr(row, "receive_status", None) or "pending",
        "delivery_review_status": getattr(row, "delivery_review_status", None) or "pending",
        "hired_at": normalize_rms_date(getattr(row, "hired_at", None)),
    }
    return d


def status_history_to_dict(row: Any) -> Dict[str, Any]:
    return {
        "id": row.id,
        "application_id": row.application_id,
        "from_status": row.from_status or "",
        "to_status": row.to_status or "",
        "reason": row.reason or "",
        "note": row.note or "",
        "changed_by": row.changed_by,
        "changed_at": normalize_rms_date(row.changed_at),
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
    now = utc_date_str()
    row = RmsApplication(
        job_id=job_id,
        candidate_id=candidate_id,
        client_id=int(job.client_id),
        resume_id=data.get("resume_id"),
        status="recommended",
        receive_status="pending",
        delivery_review_status="pending",
        hired_at="",
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

    row.updated_at = utc_date_str()
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
    *,
    RmsCandidate: Optional[Type[Any]] = None,
    RosterEntry: Optional[Type[Any]] = None,
) -> Dict[str, Any]:
    row = _get_writable_application(db, ctx, application_id, RmsApplication, Client)
    raw_from = (row.status or "").strip() or "recommended"
    if raw_from == "recommended":
        raise HTTPException(
            status_code=400,
            detail="推荐记录须先通过交付内审后方可变更招聘进展",
        )
    from_status = normalize_application_status(raw_from)
    to_status = str(data.get("to_status") or "").strip()
    mode = str(data.get("mode") or "transition").strip() or "transition"
    if not to_status:
        raise HTTPException(status_code=400, detail="to_status 不能为空")
    if to_status == from_status:
        raise HTTPException(status_code=400, detail="目标状态与当前状态相同")
    if to_status not in APPLICATION_PROGRESS_STATUSES:
        raise HTTPException(status_code=400, detail=f"非法招聘进展状态 {to_status}")

    if mode == "transition":
        if from_status in APPLICATION_TERMINAL:
            raise HTTPException(status_code=400, detail=f"终态 {from_status} 不可再流转")
        allowed = ALLOWED_TRANSITIONS.get(from_status)
        if allowed is None:
            raise HTTPException(status_code=400, detail=f"未知状态 {raw_from}，不可流转")
        if to_status not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"不允许从 {from_status} 变更为 {to_status}",
            )
        hist_reason = str(data.get("reason") or "").strip()
        hist_note = str(data.get("note") or "").strip()
    elif mode == "correction":
        if not is_pipeline_eligible_application(row):
            raise HTTPException(
                status_code=400,
                detail="状态修正仅适用于已接收且内审通过的推荐记录",
            )
        hist_note = validate_status_correction_note(str(data.get("note") or ""))
        hist_reason = "status_correction"
    else:
        raise HTTPException(status_code=400, detail=f"未知 mode {mode}")

    now = utc_date_str()
    if from_status == "hired" and to_status != "hired":
        row.hired_at = ""
    if to_status == "hired":
        row.hired_at = validate_hired_at(str(data.get("hired_at") or ""))
    row.status = to_status
    row.current_stage = to_status
    row.last_activity_at = now
    row.updated_at = now
    hist = RmsApplicationStatusHistory(
        application_id=row.id,
        from_status=raw_from if raw_from != from_status else from_status,
        to_status=to_status,
        reason=hist_reason,
        note=hist_note,
        changed_by=ctx.user_id,
        changed_at=now,
    )
    db.add(hist)
    db.commit()
    db.refresh(row)
    result = application_to_dict(row)
    if to_status == "hired" and RmsCandidate is not None and RosterEntry is not None:
        from services import rms_roster_check as roster_chk

        roster_check = roster_chk.check_hired_roster_match(
            db, ctx, row, RmsCandidate, RosterEntry, Client
        )
        result["roster_check"] = roster_check
    return result


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


def _delete_application_children(
    db: Session,
    application_id: int,
    *,
    RmsApplicationStatusHistory: Type[Any],
    RmsInterview: Optional[Type[Any]] = None,
    RmsOffer: Optional[Type[Any]] = None,
    RmsMatchResult: Optional[Type[Any]] = None,
) -> None:
    db.query(RmsApplicationStatusHistory).filter(
        RmsApplicationStatusHistory.application_id == application_id
    ).delete(synchronize_session=False)
    if RmsInterview is not None:
        db.query(RmsInterview).filter(
            RmsInterview.application_id == application_id
        ).delete(synchronize_session=False)
    if RmsOffer is not None:
        db.query(RmsOffer).filter(
            RmsOffer.application_id == application_id
        ).delete(synchronize_session=False)
    if RmsMatchResult is not None:
        db.query(RmsMatchResult).filter(
            RmsMatchResult.application_id == application_id
        ).delete(synchronize_session=False)


def delete_application(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    RmsApplication: Type[Any],
    RmsApplicationStatusHistory: Type[Any],
    Client: Type[Any],
    *,
    RmsInterview: Optional[Type[Any]] = None,
    RmsOffer: Optional[Type[Any]] = None,
    RmsMatchResult: Optional[Type[Any]] = None,
) -> Dict[str, Any]:
    row = _get_writable_application(db, ctx, application_id, RmsApplication, Client)
    app_id = int(row.id)
    candidate_id = int(row.candidate_id)
    _delete_application_children(
        db,
        app_id,
        RmsApplicationStatusHistory=RmsApplicationStatusHistory,
        RmsInterview=RmsInterview,
        RmsOffer=RmsOffer,
        RmsMatchResult=RmsMatchResult,
    )
    db.delete(row)
    db.commit()
    return {"ok": True, "id": app_id, "candidate_id": candidate_id}


def list_delivery_review_applications(
    db: Session,
    ctx: AuthContext,
    RmsApplication: Type[Any],
    Client: Type[Any],
) -> List[Dict[str, Any]]:
    q = rms_ds.scoped_applications_query(db, ctx, RmsApplication, Client, action="read")
    q = q.filter(RmsApplication.status == "recommended")
    q = q.filter(
        or_(
            RmsApplication.delivery_review_status == "pending",
            RmsApplication.delivery_review_status == "",
            RmsApplication.delivery_review_status.is_(None),
        )
    )
    rows = q.order_by(RmsApplication.id.desc()).all()
    return [application_to_dict(r) for r in rows]


def submit_delivery_review(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    data: Dict[str, Any],
    RmsApplication: Type[Any],
    RmsApplicationStatusHistory: Type[Any],
    Client: Type[Any],
) -> Dict[str, Any]:
    row = _get_writable_application(db, ctx, application_id, RmsApplication, Client)
    result = str(data.get("result") or "").strip()
    now = utc_date_str()
    if result == "passed":
        row.delivery_review_status = "passed"
        row.receive_status = "accepted"
        prev_status = (row.status or "").strip() or "recommended"
        if prev_status in ("", "recommended"):
            row.status = "pending_client_screen"
            row.current_stage = "pending_client_screen"
            row.last_activity_at = now
            hist = RmsApplicationStatusHistory(
                application_id=row.id,
                from_status="recommended",
                to_status="pending_client_screen",
                reason="delivery_review_passed",
                note=str(data.get("note") or "").strip(),
                changed_by=ctx.user_id,
                changed_at=now,
            )
            db.add(hist)
    elif result == "failed":
        row.delivery_review_status = "failed"
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return application_to_dict(row)


def _pdf_blocks_to_text(page: Any) -> str:
    try:
        blocks = page.get_text("blocks", sort=True) or []
    except Exception:
        return ""
    parts: List[str] = []
    for block in blocks:
        if len(block) < 5:
            continue
        text = (block[4] or "").strip()
        if not text:
            continue
        if len(block) > 6 and block[6] == 1:
            continue
        parts.append(text)
    return "\n".join(parts).strip()


def _pdf_words_to_text(page: Any) -> str:
    try:
        words = page.get_text("words", sort=True) or []
    except Exception:
        return ""
    if not words:
        return ""
    lines_by_block: Dict[int, Dict[int, List[str]]] = {}
    for word_entry in words:
        if len(word_entry) < 8:
            continue
        word = str(word_entry[4]).strip()
        if not word:
            continue
        block_no = int(word_entry[5])
        line_no = int(word_entry[6])
        lines_by_block.setdefault(block_no, {}).setdefault(line_no, []).append(word)
    parts: List[str] = []
    for block_no in sorted(lines_by_block.keys()):
        block_lines = lines_by_block[block_no]
        for line_no in sorted(block_lines.keys()):
            parts.append(" ".join(block_lines[line_no]))
    return "\n".join(parts).strip()


def _extract_pdf_page_text(page: Any) -> str:
    text = _pdf_blocks_to_text(page)
    if text:
        return text
    text = _pdf_words_to_text(page)
    if text:
        return text
    try:
        return (page.get_text("text", sort=True) or "").strip()
    except Exception:
        return ""


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
                        parts.append(_extract_pdf_page_text(doc.load_page(i)))
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


def _count_cjk_chars(text: str) -> int:
    return len(_RE_CJK.findall(text or ""))


def _is_noise_line(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped:
        return False
    if _RE_WATERMARK_LINE.match(stripped):
        return True
    if _RE_TRACKING_LINE.match(stripped):
        return True
    if len(stripped) >= 20 and re.fullmatch(r"[A-Za-z0-9\-]+", stripped):
        return True
    if _count_cjk_chars(stripped) == 0 and len(stripped) > 40:
        alnum = sum(1 for ch in stripped if ch.isalnum())
        if alnum / len(stripped) > 0.85:
            return True
    return False


def _clean_resume_text_for_parse(raw_text: str) -> str:
    lines = (raw_text or "").splitlines()
    result: List[str] = []
    prev_nonempty = ""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if result and result[-1] != "":
                result.append("")
            continue
        if _is_noise_line(stripped):
            continue
        if stripped == prev_nonempty:
            continue
        result.append(stripped)
        prev_nonempty = stripped
    while result and result[-1] == "":
        result.pop()
    return "\n".join(result).strip()


def _build_extract_warning(
    raw_text: str,
    cleaned_text: str,
    draft_fields: Dict[str, str],
    *,
    is_pdf: bool = False,
) -> str:
    warnings: List[str] = []
    raw = raw_text or ""
    cleaned = cleaned_text or ""
    if raw and len(cleaned) < len(raw) * 0.5:
        warnings.append("检测到较多噪声文本已过滤")
    if raw and _count_cjk_chars(cleaned) < 50:
        warnings.append("识别到的中文内容较少")
    if raw and not any(
        (draft_fields.get(k) or "").strip()
        for k in ("phone", "name", "email_wechat")
    ):
        warnings.append("未能识别姓名、手机或邮箱")
    if is_pdf and not raw.strip():
        warnings.append("未能从 PDF 提取文本，可能是扫描件图片")
    deduped: List[str] = []
    for item in warnings:
        if item not in deduped:
            deduped.append(item)
    return "；".join(deduped)


def _empty_parse_draft_response(message: str = "") -> Dict[str, Any]:
    return {
        "draft_fields": {},
        "parsed_text": "",
        "parsed_text_raw": "",
        "parsed_text_length": 0,
        "parsed_text_raw_length": 0,
        "extract_warning": "",
        "message": message,
    }


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


def _clean_extracted_name(raw: str) -> str:
    val = (raw or "").strip()
    if not val:
        return ""
    val = _FIELD_LABEL_SPLIT.split(val, maxsplit=1)[0]
    val = re.sub(r"1[3-9][0-9 \-()]{9,20}.*$", "", val)
    val = val.strip(" \t:：,，;；|·")
    return val.strip()


def _extract_name(text: str) -> str:
    match = _RE_NAME.search(text or "")
    if match:
        return _clean_extracted_name(match.group(1))
    return _extract_name_from_header(text or "")


def _extract_name_from_header(text: str) -> str:
    lines = [_normalize_resume_line(line) for line in (text or "").splitlines()]
    nonempty = [line for line in lines if line]
    if not nonempty:
        return ""
    header = nonempty[:10]
    header_text = "\n".join(header)
    if not (
        _RE_PROFILE_LINE.search(header_text)
        or _RE_PHONE.search(header_text)
        or _RE_AGE_LOOSE.search(header_text)
    ):
        return ""
    for line in header[:4]:
        if line in _NAME_HEADER_SKIP:
            continue
        if _RE_NAME_STANDALONE.fullmatch(line):
            return line
    return ""


def _extract_name_from_filename(file_name: str) -> str:
    stem = os.path.splitext(os.path.basename(file_name or ""))[0]
    parts = [part.strip() for part in re.split(r"[-—_]", stem) if part.strip()]
    candidates: List[str] = []
    for part in reversed(parts):
        if not _RE_NAME_STANDALONE.fullmatch(part):
            continue
        if re.search(r"[A-Za-z0-9]", part):
            continue
        candidates.append(part)
    if not candidates:
        return ""
    longish = [candidate for candidate in candidates if len(candidate) >= 3]
    if longish:
        return longish[0]
    return candidates[0]


def _is_plausible_age(raw: str) -> bool:
    try:
        age = int(str(raw or "").strip())
    except ValueError:
        return False
    return 16 <= age <= 70


def _extract_age(text: str) -> str:
    src = text or ""
    for pattern in (
        _RE_AGE,
        _RE_AGE_PROFILE,
        _RE_AGE_PROFILE_BARE,
        _RE_AGE_PIPE,
        _RE_AGE_GENDER_NEAR,
    ):
        age = _first_match(pattern, src)
        if age and _is_plausible_age(age):
            return age
    header = "\n".join((src or "").splitlines()[:12])
    for match in _RE_AGE_LOOSE.finditer(header):
        age = match.group(1)
        if _is_plausible_age(age):
            return age
    return ""


def _extract_gender(text: str) -> str:
    src = text or ""
    gender = _first_match(_RE_GENDER, src)
    if gender:
        return gender
    header_lines = (src or "").splitlines()[:12]
    header = "\n".join(header_lines)
    gender = _first_match(_RE_GENDER_PROFILE, header)
    if gender:
        return gender
    for line in header_lines:
        stripped = _normalize_resume_line(line)
        match = re.match(r"^(男|女)\s*[|｜]", stripped)
        if match:
            return match.group(1)
    return ""


def _normalize_work_years(raw: str) -> str:
    val = re.sub(r"\s+", "", raw or "")
    val = re.sub(r"(?:工作)?经验$", "", val)
    if not val:
        return ""
    if val.endswith("年以上"):
        return val
    if val.endswith("年"):
        return val
    if val.isdigit():
        return f"{val}年"
    return val


def _extract_explicit_work_years(src: str) -> str:
    for pattern in (_RE_WORK_YEARS_LABEL, _RE_WORK_YEARS_EXPERIENCE):
        m = pattern.search(src)
        if m:
            return _normalize_work_years(m.group(1))
    return ""


def _parse_year_month(token: str) -> Optional[Tuple[int, int]]:
    t = (token or "").strip()
    if not t:
        return None
    m = re.match(r"^(\d{4})[./](\d{1,2})$", t, re.IGNORECASE)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return year, month
        return None
    m = re.match(r"^(\d{4})年(\d{1,2})月?$", t)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return year, month
    return None


def _month_index(year: int, month: int) -> int:
    return year * 12 + month


def _parse_work_periods(
    text: str,
    today: Optional[date] = None,
) -> List[Tuple[int, int]]:
    ref = today or date.today()
    periods: List[Tuple[int, int]] = []
    open_end_tokens = {"至今", "现在", "present", "current"}
    for m in WORK_PERIOD_RE.finditer(text or ""):
        start_parsed = _parse_year_month(m.group("start"))
        if not start_parsed:
            continue
        end_raw = (m.group("end") or "").strip()
        if end_raw.lower() in open_end_tokens or end_raw in open_end_tokens:
            end_parsed = (ref.year, ref.month)
        else:
            end_parsed = _parse_year_month(end_raw)
        if not end_parsed:
            continue
        start_idx = _month_index(*start_parsed)
        end_idx = _month_index(*end_parsed)
        if start_idx > end_idx:
            continue
        periods.append((start_idx, end_idx))
    return periods


def _merge_period_months(periods: List[Tuple[int, int]]) -> int:
    if not periods:
        return 0
    merged: List[Tuple[int, int]] = [sorted(periods)[0]]
    for start, end in sorted(periods)[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end + 1:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return sum(end - start + 1 for start, end in merged)


def _format_work_years(total_months: int) -> str:
    if total_months <= 0:
        return ""
    if total_months < 12:
        return f"{total_months}个月"
    years, months = divmod(total_months, 12)
    if months == 0:
        return f"{years}年"
    return f"{years}年{months}个月"


def _text_without_education_block(text: str) -> str:
    lines = (text or "").splitlines()
    result: List[str] = []
    in_edu = False
    for line in lines:
        stripped = line.strip()
        if not in_edu:
            if _EDU_BLOCK_START.match(stripped):
                in_edu = True
                continue
            result.append(line)
            continue
        if _EDU_BLOCK_STOP.match(stripped):
            in_edu = False
            result.append(line)
    return "\n".join(result).strip()


def _extract_work_experience_text(text: str) -> str:
    lines = (text or "").splitlines()
    blocks: List[str] = []
    current: List[str] = []
    in_work = False

    for line in lines:
        stripped = line.strip()
        if _WORK_SECTION_START.match(stripped):
            if in_work and current:
                blocks.append("\n".join(current))
            current = []
            in_work = True
            continue
        if in_work:
            if stripped and _WORK_SECTION_STOP.match(stripped):
                if current:
                    blocks.append("\n".join(current))
                current = []
                in_work = False
                continue
            current.append(stripped)

    if in_work and current:
        blocks.append("\n".join(current))

    if blocks:
        return "\n".join(blocks)

    return _text_without_education_block(text)


def _parse_work_years_from_periods(
    text: str,
    today: Optional[date] = None,
) -> str:
    work_text = _extract_work_experience_text(text)
    if not work_text:
        return ""
    periods = _parse_work_periods(work_text, today=today)
    total = _merge_period_months(periods)
    return _format_work_years(total)


def _extract_education_block(text: str) -> str:
    lines = (text or "").splitlines()
    in_block = False
    block_lines: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not in_block:
            if _EDU_BLOCK_START.match(stripped):
                in_block = True
            continue
        if _EDU_BLOCK_STOP.match(stripped):
            break
        block_lines.append(stripped)
    return "\n".join(block_lines).strip()


def _normalize_phone_candidate(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if _RE_PHONE.fullmatch(digits):
        return digits
    for match in re.finditer(r"1[3-9]\d{9}", digits):
        return match.group(0)
    return ""


def _extract_phone(text: str) -> str:
    src = text or ""
    candidates: List[str] = []
    for match in _RE_PHONE_LABEL.finditer(src):
        candidates.append(match.group(1))
    candidates.extend(re.findall(r"1[3-9][0-9 \-()]{9,20}", src))
    seen: set[str] = set()
    for raw in candidates:
        digits = _normalize_phone_candidate(raw)
        if not digits or digits in seen:
            continue
        seen.add(digits)
        return digits
    return ""


def _education_level_from_line(line: str) -> str:
    stripped = (line or "").strip()
    if not stripped:
        return ""
    for part in _DEGREE_IN_PARENS.findall(stripped):
        normalized = _normalize_education_level(part)
        if normalized:
            return normalized
    pipe_m = _DEGREE_INLINE.search(stripped)
    if pipe_m:
        normalized = _normalize_education_level(pipe_m.group(1))
        if normalized:
            return normalized
    return ""


def _is_education_continuation(prev: str, nxt: str) -> bool:
    if not nxt.strip() or _search_school_entity(nxt):
        return False
    if _DEGREE_ONLY_LINE.match(nxt.strip()):
        return False
    if _SKILL_LINE.match(nxt.strip()):
        return False
    if re.match(r"^(?:毕业论文|毕业设计|项目经历|工作经历|工作经验|实习经历)", nxt.strip()):
        return False
    if len(nxt.strip()) > 60:
        return False
    if _education_level_from_line(prev):
        return False
    if _DEGREE_INLINE.search(nxt):
        return True
    prev_stripped = prev.rstrip()
    nxt_stripped = nxt.lstrip()
    if not prev_stripped or not nxt_stripped:
        return False
    if re.match(r"^\d{4}", nxt_stripped):
        return False
    last = prev_stripped[-1]
    first = nxt_stripped[0]
    if "\u4e00" <= last <= "\u9fff" and "\u4e00" <= first <= "\u9fff":
        return True
    return False


def _merge_education_lines(lines: List[str]) -> List[str]:
    merged: List[str] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if idx + 1 < len(lines) and _is_education_continuation(line, lines[idx + 1]):
            nxt = lines[idx + 1].strip()
            prev_stripped = line.rstrip()
            nxt_stripped = nxt.lstrip()
            if (
                prev_stripped
                and nxt_stripped
                and "\u4e00" <= prev_stripped[-1] <= "\u9fff"
                and "\u4e00" <= nxt_stripped[0] <= "\u9fff"
            ):
                line = prev_stripped + nxt_stripped
            else:
                line = prev_stripped + " " + nxt_stripped
            idx += 1
        merged.append(line)
        idx += 1
    return merged


def _collect_education_lines(text: str) -> List[str]:
    block = _extract_education_block(text)
    source_lines = (
        [line.strip() for line in block.splitlines() if line.strip()]
        if block
        else [line.strip() for line in (text or "").splitlines() if line.strip()]
    )
    lines: List[str] = []
    idx = 0
    while idx < len(source_lines):
        stripped = source_lines[idx]
        if not block:
            if _WORK_SECTION_START.match(stripped) or _EDU_BLOCK_STOP.match(stripped):
                idx += 1
                continue
            if re.match(r"^(?:毕业论文|毕业设计)", stripped):
                idx += 1
                continue
            if not _search_school_entity(stripped):
                idx += 1
                continue
            if _SKILL_LINE.match(stripped):
                idx += 1
                continue
        lines.append(stripped)
        idx += 1
        while idx < len(source_lines) and _is_education_continuation(lines[-1], source_lines[idx]):
            lines.append(source_lines[idx].strip())
            idx += 1
    return lines


def _collect_education_content(text: str) -> str:
    lines = _merge_education_lines(_collect_education_lines(text))
    return "\n".join(lines).strip()


def _normalize_education_level(degree_text: str) -> str:
    t = (degree_text or "").strip()
    if not t:
        return ""
    if "博士" in t:
        return "其他"
    if "硕士" in t:
        return "硕士"
    if "学士" in t or "本科" in t:
        return "统本"
    if "大专" in t or "专科" in t:
        return "专科"
    return ""


def _clean_major(raw: str, school: str = "") -> str:
    val = (raw or "").strip()
    if not val:
        return ""
    val = _DEGREE_IN_PARENS.sub("", val)
    val = _DATE_RANGE_RE.sub("", val)
    val = _YEAR_ONLY_RANGE_RE.sub("", val)
    val = _DEGREE_INLINE.sub("", val)
    if school:
        val = val.replace(school, "")
    val = re.sub(r"专业\s*$", "", val.strip())
    val = re.sub(
        r"(?:博士研究生|博士|硕士研究生|硕士|本科|大专|专科|学士)\s*$",
        "",
        val,
    )
    val = val.strip(" \t:：,，;；|")
    val = val.strip()
    if not val:
        return ""
    if "毕业论文" in val or "毕业设计" in val:
        return ""
    if school and school in val:
        return ""
    if _DATE_RANGE_RE.search(val):
        return ""
    if _search_school_entity(val):
        return ""
    return _collapse_chinese_spaces(val.strip())


def _parse_education_from_text(edu_block: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    pending_school = ""
    if not edu_block:
        return result
    for line in edu_block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^(?:毕业论文|毕业设计)", stripped):
            continue
        school_m = _search_school_entity(stripped)
        if school_m:
            school = _normalize_school_name(school_m.group(1))
            after = stripped[school_m.end():]
            level = _education_level_from_line(stripped)
            major = _clean_major(after, school=school)
            result["school"] = school
            pending_school = school if not major else ""
            if major:
                result["major"] = major
            if level:
                result["education_level"] = level
            continue
        if pending_school and not result.get("major"):
            if _DEGREE_ONLY_LINE.match(stripped):
                level = _normalize_education_level(stripped)
                if level:
                    result["education_level"] = level
                continue
            major = _clean_major(stripped, school=pending_school)
            if major:
                result["major"] = major
                pending_school = ""
            level = _education_level_from_line(stripped)
            if level:
                result["education_level"] = level
    return result


def _extract_draft_fields_from_text(text: str, *, file_name: str = "") -> Dict[str, str]:
    src = _normalize_resume_text(text).strip()
    fields: Dict[str, str] = {}
    if not src:
        return fields

    phone = _extract_phone(src)
    if phone:
        fields["phone"] = phone

    email_m = _RE_EMAIL.search(src)
    if email_m:
        fields["email_wechat"] = email_m.group(0)

    name = _extract_name(src)
    if not name and file_name:
        name = _extract_name_from_filename(file_name)
    if name:
        fields["name"] = name

    age = _extract_age(src)
    if age:
        fields["age"] = age

    work_years = _extract_explicit_work_years(src)
    if work_years:
        fields["work_years"] = work_years
    else:
        parsed = _parse_work_years_from_periods(src)
        if parsed:
            fields["work_years"] = parsed

    current_salary = _first_match(_RE_CURRENT_SALARY, src)
    if current_salary:
        fields["current_salary"] = current_salary

    expected_salary = _first_match(_RE_EXPECTED_SALARY, src)
    if expected_salary:
        fields["expected_salary"] = expected_salary

    edu_content = _collect_education_content(src)
    edu = _parse_education_from_text(edu_content) if edu_content else {}
    if edu.get("school"):
        fields["school"] = edu["school"]
    else:
        school = _first_match(_RE_SCHOOL, src)
        if school:
            fields["school"] = _normalize_school_name(school)
        else:
            for line in src.splitlines():
                school_m = _search_school_entity(line)
                if school_m:
                    fields["school"] = _normalize_school_name(school_m.group(1))
                    break

    if edu.get("major"):
        fields["major"] = edu["major"]
    else:
        major = _first_match(_RE_MAJOR, src)
        if major:
            fields["major"] = major

    if edu.get("education_level"):
        fields["education_level"] = edu["education_level"]
    else:
        edu_m = _RE_EDUCATION.search(src)
        if edu_m:
            normalized = _normalize_education_level(edu_m.group(1))
            if normalized:
                fields["education_level"] = normalized

    gender = _extract_gender(src)
    if gender:
        fields["gender"] = gender

    return fields


def parse_resume_draft(file_name: str, content: bytes) -> Dict[str, Any]:
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=400, detail="简历文件不能超过 10MB")

    ext = os.path.splitext(file_name or "")[1].lower()
    raw_text, word_msg = _extract_resume_text(file_name, content)
    if word_msg:
        return _empty_parse_draft_response(word_msg)

    cleaned_text = _clean_resume_text_for_parse(raw_text)
    draft_fields = _extract_draft_fields_from_text(cleaned_text, file_name=file_name)
    extract_warning = _build_extract_warning(
        raw_text,
        cleaned_text,
        draft_fields,
        is_pdf=ext == ".pdf",
    )
    return {
        "draft_fields": draft_fields,
        "parsed_text": cleaned_text[:PARSE_DRAFT_TEXT_MAX] if cleaned_text else "",
        "parsed_text_raw": raw_text[:PARSE_DRAFT_TEXT_MAX] if raw_text else "",
        "parsed_text_length": len(cleaned_text),
        "parsed_text_raw_length": len(raw_text),
        "extract_warning": extract_warning,
        "message": "",
    }
