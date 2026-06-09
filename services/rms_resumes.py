"""RMS resume file storage and parse-result persistence."""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Type

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import security_foundation as sec
from auth.service import AuthContext
from schemas.rms import normalize_rms_date, utc_date_str
from services import rms_candidates as cand_svc

RESUME_ALLOWED_SUFFIXES = frozenset({".pdf", ".doc", ".docx", ".txt", ".rtf"})
RESUME_VIEWABLE_SUFFIXES = frozenset({".pdf", ".txt", ".rtf"})
MAX_RESUME_BYTES = 10 * 1024 * 1024

_MEDIA_TYPE_BY_EXT = {
    ".pdf": "application/pdf",
    ".txt": "text/plain; charset=utf-8",
    ".rtf": "application/rtf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

def resume_to_dict(row: Any) -> Dict[str, Any]:
    return {
        "id": row.id,
        "candidate_id": row.candidate_id,
        "file_name": row.file_name or "",
        "file_type": row.file_type or "",
        "created_at": normalize_rms_date(row.created_at),
    }


async def upload_candidate_resume(
    db: Session,
    ctx: AuthContext,
    candidate_id: int,
    upload: UploadFile,
    *,
    upload_dir: str,
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
    RmsResume: Type[Any],
) -> Dict[str, Any]:
    cand_svc.get_candidate(db, ctx, candidate_id, RmsCandidate, RmsApplication, Client)

    raw_name = upload.filename or ""
    ext = os.path.splitext(raw_name)[1].lower()
    if ext not in RESUME_ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型，允许：{', '.join(sorted(RESUME_ALLOWED_SUFFIXES))}",
        )
    content = await upload.read()
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=400, detail="简历文件不能超过 10MB")

    from services.rms_applications import parse_resume_file_for_storage

    parsed_text, parsed_json = parse_resume_file_for_storage(raw_name, content)

    safe = sec.safe_visit_attachment_name(raw_name)
    if not os.path.splitext(safe)[1]:
        safe = safe + ext
    rel = f"rms/resumes/{candidate_id}/{int(time.time() * 1000000)}_{safe}"
    try:
        abs_target = sec.resolve_upload_path(upload_dir, rel)
    except ValueError:
        raise HTTPException(status_code=400, detail="非法文件路径")
    os.makedirs(os.path.dirname(abs_target), exist_ok=True)
    with open(abs_target, "wb") as f:
        f.write(content)

    now = utc_date_str()
    row = RmsResume(
        candidate_id=candidate_id,
        file_name=raw_name or safe,
        file_path=rel,
        file_type=ext.lstrip("."),
        parsed_text=parsed_text,
        parsed_json=parsed_json,
        uploaded_by=ctx.user_id,
        created_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return resume_to_dict(row)


def _resolve_resume_file(
    db: Session,
    ctx: AuthContext,
    resume_id: int,
    *,
    upload_dir: str,
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
    RmsResume: Type[Any],
) -> tuple[Any, str, str, str]:
    row = db.query(RmsResume).filter(RmsResume.id == resume_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="简历不存在")
    cand_svc.get_candidate(
        db,
        ctx,
        int(row.candidate_id),
        RmsCandidate,
        RmsApplication,
        Client,
    )
    rel = (row.file_path or "").strip()
    if not rel:
        raise HTTPException(status_code=404, detail="简历文件不存在")
    try:
        abs_path = sec.resolve_upload_path(upload_dir, rel)
    except ValueError:
        raise HTTPException(status_code=404, detail="简历文件不存在")
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="简历文件不存在")
    filename = (row.file_name or os.path.basename(abs_path) or "resume").strip()
    ext = os.path.splitext(filename)[1].lower()
    if not ext:
        ext = os.path.splitext(abs_path)[1].lower()
    return row, abs_path, filename, ext


def view_resume(
    db: Session,
    ctx: AuthContext,
    resume_id: int,
    *,
    upload_dir: str,
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
    RmsResume: Type[Any],
) -> FileResponse:
    _row, abs_path, filename, ext = _resolve_resume_file(
        db,
        ctx,
        resume_id,
        upload_dir=upload_dir,
        RmsCandidate=RmsCandidate,
        RmsApplication=RmsApplication,
        Client=Client,
        RmsResume=RmsResume,
    )
    if ext not in RESUME_VIEWABLE_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="该格式不支持在线阅读，请使用下载后在本地查看",
        )
    media_type = _MEDIA_TYPE_BY_EXT.get(ext, "application/octet-stream")
    return FileResponse(
        abs_path,
        media_type=media_type,
        filename=filename,
        content_disposition_type="inline",
    )


def download_resume(
    db: Session,
    ctx: AuthContext,
    resume_id: int,
    *,
    upload_dir: str,
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
    RmsResume: Type[Any],
) -> FileResponse:
    _row, abs_path, filename, ext = _resolve_resume_file(
        db,
        ctx,
        resume_id,
        upload_dir=upload_dir,
        RmsCandidate=RmsCandidate,
        RmsApplication=RmsApplication,
        Client=Client,
        RmsResume=RmsResume,
    )
    media_type = _MEDIA_TYPE_BY_EXT.get(ext, "application/octet-stream")
    return FileResponse(
        abs_path,
        media_type=media_type,
        filename=filename,
        content_disposition_type="attachment",
    )
