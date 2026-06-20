"""Company materials library business logic."""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Type

from fastapi import HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import desc, or_, text
from sqlalchemy.orm import Session

import security_foundation as sec
from auth import service as auth_svc
from auth.service import AuthContext
from schemas.company_materials import (
    MATERIAL_CATEGORIES,
    MATERIAL_CONFIDENTIALITY,
    MATERIAL_OFFICE_CONVERT_SUFFIXES,
    MATERIAL_PREVIEWABLE_SUFFIXES,
    MATERIAL_PREVIEW_CONVERSION_FAILED_MSG,
    MATERIAL_PREVIEW_UNSUPPORTED_MSG,
    MATERIAL_STATUS,
    MaterialUpdateBody,
    category_label,
    confidentiality_label,
    normalize_category,
    normalize_confidentiality,
    normalize_status,
    status_label,
)
from services.material_preview_conversion import (
    MaterialPreviewConversionError,
    convert_office_to_preview_pdf,
)

_CHUNK_SIZE = 1024 * 1024

_MEDIA_TYPE_BY_EXT = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def _has_admin_read(ctx: AuthContext) -> bool:
    return auth_svc.user_has_permission(ctx, "materials.read")


def can_read_confidentiality(ctx: AuthContext, level: str) -> bool:
    conf = str(level or "").strip().lower()
    if _has_admin_read(ctx):
        return True
    if conf == "public":
        return auth_svc.user_has_permission(ctx, "materials.public.read")
    if conf == "internal":
        return auth_svc.user_has_permission(ctx, "materials.internal.read")
    return False


def can_preview_confidentiality(ctx: AuthContext, level: str) -> bool:
    conf = str(level or "").strip().lower()
    if _has_admin_read(ctx):
        return True
    if conf == "confidential":
        return False
    if conf == "public":
        return auth_svc.user_has_permission(ctx, "materials.public.preview")
    if conf == "internal":
        return auth_svc.user_has_permission(ctx, "materials.internal.preview")
    return False


def can_download_confidentiality(ctx: AuthContext, level: str) -> bool:
    conf = str(level or "").strip().lower()
    if auth_svc.user_has_permission(ctx, "materials.download"):
        return True
    if conf == "confidential":
        return False
    if conf == "public":
        return auth_svc.user_has_permission(ctx, "materials.public.download")
    if conf == "internal":
        return auth_svc.user_has_permission(ctx, "materials.internal.download")
    return False


def _readable_confidentiality_levels(ctx: AuthContext) -> List[str]:
    if _has_admin_read(ctx):
        return ["public", "internal", "confidential"]
    levels: List[str] = []
    if auth_svc.user_has_permission(ctx, "materials.public.read"):
        levels.append("public")
    if auth_svc.user_has_permission(ctx, "materials.internal.read"):
        levels.append("internal")
    return levels


def _action_flags(ctx: AuthContext, row: Any) -> Dict[str, bool]:
    conf = str(getattr(row, "confidentiality", "") or "").strip().lower()
    return {
        "can_preview": can_preview_confidentiality(ctx, conf),
        "can_download": can_download_confidentiality(ctx, conf),
        "can_write": auth_svc.user_has_permission(ctx, "materials.write"),
        "can_delete": auth_svc.user_has_permission(ctx, "materials.delete"),
    }


def safe_material_filename(name: str) -> str:
    base = os.path.basename(str(name or "")).strip()
    if not base:
        base = "material.bin"
    base = re.sub(r"[^\w\-. \u4e00-\u9fff]", "_", base)
    return (base[:200] if len(base) > 200 else base) or "material.bin"


def material_stored_path_rel(filename: str) -> str:
    now = datetime.now()
    safe = safe_material_filename(filename)
    return f"materials/{now.year:04d}/{now.month:02d}/{uuid.uuid4().hex}_{safe}"


def _date_str(dt: Any) -> str:
    if dt is None:
        return ""
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d")
    s = str(dt).strip()
    if not s:
        return ""
    return s[:10] if len(s) >= 10 else s


def _dt_iso(dt: Any) -> str:
    if dt is None:
        return ""
    if isinstance(dt, datetime):
        return dt.isoformat(timespec="seconds")
    return str(dt)


def _load_dept_names(db: Session, dept_ids: List[int]) -> Dict[int, str]:
    ids = sorted({int(i) for i in dept_ids if i})
    if not ids:
        return {}
    placeholders = ", ".join(f":d{i}" for i in range(len(ids)))
    params = {f"d{i}": did for i, did in enumerate(ids)}
    rows = db.execute(
        text(f"SELECT id, name FROM sys_dept WHERE id IN ({placeholders})"),
        params,
    ).fetchall()
    return {int(r[0]): str(r[1] or "") for r in rows}


def _load_user_names(db: Session, user_ids: List[int]) -> Dict[int, str]:
    ids = sorted({int(i) for i in user_ids if i})
    if not ids:
        return {}
    placeholders = ", ".join(f":u{i}" for i in range(len(ids)))
    params = {f"u{i}": uid for i, uid in enumerate(ids)}
    rows = db.execute(
        text(f"SELECT id, username FROM sys_user WHERE id IN ({placeholders})"),
        params,
    ).fetchall()
    return {int(r[0]): str(r[1] or "") for r in rows}


def row_to_dict(row: Any, ctx: AuthContext, *, dept_names: Optional[Dict[int, str]] = None,
                user_names: Optional[Dict[int, str]] = None) -> Dict[str, Any]:
    flags = _action_flags(ctx, row)
    owner_dept_id = getattr(row, "owner_dept_id", None)
    uploaded_by = getattr(row, "uploaded_by", None)
    owner_name = ""
    if owner_dept_id is not None and dept_names is not None:
        owner_name = dept_names.get(int(owner_dept_id), "")
    uploaded_name = ""
    if uploaded_by is not None and user_names is not None:
        uploaded_name = user_names.get(int(uploaded_by), "")
    return {
        "id": row.id,
        "title": row.title or "",
        "category": row.category or "",
        "category_label": category_label(row.category or ""),
        "description": row.description or "",
        "confidentiality": row.confidentiality or "",
        "confidentiality_label": confidentiality_label(row.confidentiality or ""),
        "owner_dept_id": owner_dept_id,
        "owner_dept_name": owner_name,
        "file_name": row.file_name or "",
        "mime_type": row.mime_type or "",
        "file_size": int(row.file_size or 0),
        "status": row.status or "active",
        "status_label": status_label(row.status or "active"),
        "expires_at": row.expires_at or "",
        "uploaded_by": uploaded_by,
        "uploaded_by_name": uploaded_name,
        "created_at": _date_str(row.created_at),
        "updated_at": _date_str(row.updated_at),
        "archived_at": _dt_iso(getattr(row, "archived_at", None)) if getattr(row, "archived_at", None) else "",
        **flags,
    }


def _rows_to_dicts(db: Session, ctx: AuthContext, rows: List[Any]) -> List[Dict[str, Any]]:
    dept_ids = [int(r.owner_dept_id) for r in rows if getattr(r, "owner_dept_id", None)]
    user_ids = [int(r.uploaded_by) for r in rows if getattr(r, "uploaded_by", None)]
    dept_names = _load_dept_names(db, dept_ids)
    user_names = _load_user_names(db, user_ids)
    return [row_to_dict(r, ctx, dept_names=dept_names, user_names=user_names) for r in rows]


def _validate_dept_id(db: Session, dept_id: Optional[int]) -> None:
    if dept_id is None:
        return
    row = db.execute(text("SELECT 1 FROM sys_dept WHERE id = :id LIMIT 1"), {"id": int(dept_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="归属部门不存在")


def list_form_options(db: Session) -> Dict[str, Any]:
    depts = db.execute(
        text(
            "SELECT id, name, code FROM sys_dept WHERE status = 'active' ORDER BY path"
        )
    ).mappings().all()
    return {
        "categories": [{"value": k, "label": v} for k, v in MATERIAL_CATEGORIES.items()],
        "confidentiality_levels": [{"value": k, "label": v} for k, v in MATERIAL_CONFIDENTIALITY.items()],
        "statuses": [{"value": k, "label": v} for k, v in MATERIAL_STATUS.items()],
        "depts": [{"id": int(d["id"]), "name": str(d["name"] or ""), "code": str(d["code"] or "")} for d in depts],
    }


def list_materials(
    db: Session,
    ctx: AuthContext,
    CompanyMaterial: Type[Any],
    *,
    q_text: Optional[str] = None,
    category: Optional[str] = None,
    confidentiality: Optional[str] = None,
    status_filter: Optional[str] = None,
    owner_dept_id: Optional[int] = None,
    expires_before: Optional[str] = None,
) -> Dict[str, Any]:
    q = db.query(CompanyMaterial)
    st = (status_filter or "").strip().lower()
    if st:
        q = q.filter(CompanyMaterial.status == normalize_status(st))
    else:
        q = q.filter(CompanyMaterial.status == "active")
    if category:
        q = q.filter(CompanyMaterial.category == normalize_category(category))
    if owner_dept_id is not None:
        q = q.filter(CompanyMaterial.owner_dept_id == int(owner_dept_id))
    if expires_before:
        q = q.filter(CompanyMaterial.expires_at != None).filter(CompanyMaterial.expires_at <= expires_before.strip())  # noqa: E711
    allowed_levels = _readable_confidentiality_levels(ctx)
    if not allowed_levels:
        return {"items": []}
    q = q.filter(CompanyMaterial.confidentiality.in_(allowed_levels))
    if confidentiality:
        req = normalize_confidentiality(confidentiality)
        if req not in allowed_levels:
            return {"items": []}
        q = q.filter(CompanyMaterial.confidentiality == req)
    if q_text and q_text.strip():
        like = f"%{q_text.strip()}%"
        q = q.filter(or_(
            CompanyMaterial.title.ilike(like),
            CompanyMaterial.description.ilike(like),
            CompanyMaterial.file_name.ilike(like),
        ))
    rows = q.order_by(desc(CompanyMaterial.updated_at), desc(CompanyMaterial.id)).all()
    return {"items": _rows_to_dicts(db, ctx, rows)}


def get_material(db: Session, ctx: AuthContext, CompanyMaterial: Type[Any], material_id: int) -> Dict[str, Any]:
    row = db.query(CompanyMaterial).filter(CompanyMaterial.id == material_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="资料不存在")
    if not can_read_confidentiality(ctx, str(row.confidentiality or "")):
        raise HTTPException(status_code=404, detail="资料不存在")
    return _rows_to_dicts(db, ctx, [row])[0]


def _resolve_material_file(
    row: Any,
    *,
    upload_dir: str,
) -> tuple[str, str]:
    sp = (row.stored_path or "").strip()
    if not sp:
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        abs_path = sec.resolve_upload_path(upload_dir, sp)
    except ValueError:
        raise HTTPException(status_code=400, detail="非法文件路径")
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    filename = row.file_name or os.path.basename(abs_path)
    ext = os.path.splitext(filename)[1].lower()
    if not ext:
        ext = os.path.splitext(abs_path)[1].lower()
    return abs_path, ext


async def _write_upload_chunked(
    upload: UploadFile,
    abs_path: str,
    *,
    max_file_size: int,
    allowed_suffixes: Set[str],
) -> tuple[str, str, int]:
    raw_name = upload.filename or ""
    if not raw_name.strip():
        raise HTTPException(status_code=400, detail="文件名不能为空")
    ext = os.path.splitext(raw_name)[1].lower()
    if ext not in allowed_suffixes:
        raise HTTPException(status_code=400, detail="不支持的文件类型")
    safe = safe_material_filename(raw_name)
    if not os.path.splitext(safe)[1] and ext:
        safe = safe + ext
    mime = (upload.content_type or "").strip() or "application/octet-stream"
    total = 0
    try:
        with open(abs_path, "wb") as out:
            while True:
                chunk = await upload.read(_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_file_size:
                    raise HTTPException(status_code=413, detail="文件大小不能超过 100MB")
                out.write(chunk)
    except HTTPException:
        if os.path.isfile(abs_path):
            try:
                os.remove(abs_path)
            except OSError:
                pass
        raise
    except Exception:
        if os.path.isfile(abs_path):
            try:
                os.remove(abs_path)
            except OSError:
                pass
        raise
    return raw_name or safe, mime, total


async def create_material(
    db: Session,
    ctx: AuthContext,
    CompanyMaterial: Type[Any],
    *,
    title: str,
    category: str,
    confidentiality: str,
    description: str,
    owner_dept_id: Optional[int],
    expires_at: str,
    upload: UploadFile,
    upload_dir: str,
    max_file_size: int,
    allowed_suffixes: Set[str],
) -> Dict[str, Any]:
    t = str(title or "").strip()
    if not t:
        raise HTTPException(status_code=400, detail="请填写资料名称")
    cat = normalize_category(category)
    conf = normalize_confidentiality(confidentiality)
    _validate_dept_id(db, owner_dept_id)
    stored_rel = material_stored_path_rel(upload.filename or "material.bin")
    try:
        abs_path = sec.resolve_upload_path(upload_dir, stored_rel)
    except ValueError:
        raise HTTPException(status_code=400, detail="非法文件路径")
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    file_name, mime_type, file_size = await _write_upload_chunked(
        upload, abs_path, max_file_size=max_file_size, allowed_suffixes=allowed_suffixes,
    )
    exp = str(expires_at or "").strip() or None
    now = datetime.now()
    row = CompanyMaterial(
        title=t,
        category=cat,
        description=str(description or "").strip(),
        confidentiality=conf,
        owner_dept_id=owner_dept_id,
        file_name=file_name,
        stored_path=stored_rel,
        mime_type=mime_type,
        file_size=file_size,
        status="active",
        expires_at=exp,
        uploaded_by=ctx.user_id,
        created_at=now,
        updated_at=now,
    )
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        if os.path.isfile(abs_path):
            try:
                os.remove(abs_path)
            except OSError:
                pass
        raise
    return get_material(db, ctx, CompanyMaterial, int(row.id))


def update_material(
    db: Session,
    ctx: AuthContext,
    CompanyMaterial: Type[Any],
    material_id: int,
    patch: MaterialUpdateBody,
    fields_set: Set[str],
) -> Dict[str, Any]:
    row = db.query(CompanyMaterial).filter(CompanyMaterial.id == material_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="资料不存在")
    if "title" in fields_set:
        t = str(patch.title or "").strip()
        if not t:
            raise HTTPException(status_code=400, detail="请填写资料名称")
        row.title = t
    if "category" in fields_set:
        row.category = normalize_category(str(patch.category or ""))
    if "description" in fields_set:
        row.description = str(patch.description or "").strip()
    if "confidentiality" in fields_set:
        row.confidentiality = normalize_confidentiality(str(patch.confidentiality or ""))
    if "owner_dept_id" in fields_set:
        if patch.owner_dept_id is None:
            row.owner_dept_id = None
        else:
            _validate_dept_id(db, int(patch.owner_dept_id))
            row.owner_dept_id = int(patch.owner_dept_id)
    if "expires_at" in fields_set:
        exp = patch.expires_at
        if exp is None:
            pass
        elif str(exp).strip() == "":
            row.expires_at = None
        else:
            row.expires_at = str(exp).strip()
    row.updated_at = datetime.now()
    db.commit()
    db.refresh(row)
    return get_material(db, ctx, CompanyMaterial, material_id)


async def replace_material_file(
    db: Session,
    ctx: AuthContext,
    CompanyMaterial: Type[Any],
    material_id: int,
    *,
    upload: UploadFile,
    upload_dir: str,
    max_file_size: int,
    allowed_suffixes: Set[str],
) -> Dict[str, Any]:
    row = db.query(CompanyMaterial).filter(CompanyMaterial.id == material_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="资料不存在")
    if (row.status or "active") != "active":
        raise HTTPException(status_code=400, detail="已删除资料不可替换文件")

    old_stored_path = (row.stored_path or "").strip()
    old_abs_path = None
    if old_stored_path:
        try:
            old_abs_path = sec.resolve_upload_path(upload_dir, old_stored_path)
        except ValueError:
            old_abs_path = None

    stored_rel = material_stored_path_rel(upload.filename or "material.bin")
    try:
        new_abs_path = sec.resolve_upload_path(upload_dir, stored_rel)
    except ValueError:
        raise HTTPException(status_code=400, detail="非法文件路径")
    os.makedirs(os.path.dirname(new_abs_path), exist_ok=True)

    file_name, mime_type, file_size = await _write_upload_chunked(
        upload,
        new_abs_path,
        max_file_size=max_file_size,
        allowed_suffixes=allowed_suffixes,
    )

    row.file_name = file_name
    row.mime_type = mime_type
    row.file_size = file_size
    row.stored_path = stored_rel
    row.updated_at = datetime.now()

    try:
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        if os.path.isfile(new_abs_path):
            try:
                os.remove(new_abs_path)
            except OSError:
                pass
        raise

    if old_abs_path and os.path.isfile(old_abs_path):
        try:
            os.remove(old_abs_path)
        except OSError:
            pass

    return get_material(db, ctx, CompanyMaterial, material_id)


def archive_material(
    db: Session,
    ctx: AuthContext,
    CompanyMaterial: Type[Any],
    material_id: int,
) -> Dict[str, Any]:
    row = db.query(CompanyMaterial).filter(CompanyMaterial.id == material_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="资料不存在")
    now = datetime.now()
    row.status = "archived"
    row.archived_at = now
    row.archived_by = ctx.user_id
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return get_material(db, ctx, CompanyMaterial, material_id)


def download_material(
    db: Session,
    ctx: AuthContext,
    CompanyMaterial: Type[Any],
    material_id: int,
    *,
    upload_dir: str,
) -> FileResponse:
    row = db.query(CompanyMaterial).filter(CompanyMaterial.id == material_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="资料不存在")
    conf = str(row.confidentiality or "").strip().lower()
    if not can_read_confidentiality(ctx, conf):
        raise HTTPException(status_code=404, detail="资料不存在")
    if not can_download_confidentiality(ctx, conf):
        raise HTTPException(status_code=403, detail="缺少下载权限")
    abs_path, _ext = _resolve_material_file(row, upload_dir=upload_dir)
    mime = (row.mime_type or "").strip() or "application/octet-stream"
    return FileResponse(abs_path, media_type=mime, filename=row.file_name or os.path.basename(abs_path))


def preview_material(
    db: Session,
    ctx: AuthContext,
    CompanyMaterial: Type[Any],
    material_id: int,
    *,
    upload_dir: str,
) -> FileResponse:
    row = db.query(CompanyMaterial).filter(CompanyMaterial.id == material_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="资料不存在")
    conf = str(row.confidentiality or "").strip().lower()
    if not can_read_confidentiality(ctx, conf):
        raise HTTPException(status_code=404, detail="资料不存在")
    if not can_preview_confidentiality(ctx, conf):
        raise HTTPException(status_code=403, detail="缺少预览权限")
    abs_path, ext = _resolve_material_file(row, upload_dir=upload_dir)
    if ext in MATERIAL_PREVIEWABLE_SUFFIXES:
        media_type = _MEDIA_TYPE_BY_EXT.get(ext, "application/octet-stream")
        filename = row.file_name or os.path.basename(abs_path)
        return FileResponse(
            abs_path,
            media_type=media_type,
            filename=filename,
            content_disposition_type="inline",
        )
    if ext in MATERIAL_OFFICE_CONVERT_SUFFIXES:
        try:
            pdf_abs = convert_office_to_preview_pdf(
                source_abs=abs_path,
                upload_dir=upload_dir,
                material_id=int(row.id),
                updated_at=row.updated_at,
            )
        except MaterialPreviewConversionError:
            raise HTTPException(status_code=400, detail=MATERIAL_PREVIEW_CONVERSION_FAILED_MSG)
        stem = os.path.splitext(row.file_name or os.path.basename(abs_path))[0] or "preview"
        return FileResponse(
            pdf_abs,
            media_type="application/pdf",
            filename=f"{stem}.pdf",
            content_disposition_type="inline",
        )
    raise HTTPException(status_code=400, detail=MATERIAL_PREVIEW_UNSUPPORTED_MSG)
