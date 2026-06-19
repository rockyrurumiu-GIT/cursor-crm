"""Delivery employee file business logic."""
from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict

from schemas.delivery_employee_files import EMPLOYEE_FILE_STATUS_SET
from services.delivery_handbook import handbook_dt_iso, handbook_suffix_to_media_kind


def employee_file_normalize_status(raw: str) -> str:
    v = str(raw or "").strip().lower()
    if v in EMPLOYEE_FILE_STATUS_SET:
        return v
    return "draft"


def employee_file_client_dir_rel(client) -> str:
    return f"employee_files/client_{client.id}"


def safe_employee_file_filename(name: str) -> str:
    base = os.path.basename(str(name or "")).strip()
    if not base:
        base = "employee_file.bin"
    base = re.sub(r"[^\w\-. \u4e00-\u9fff]", "_", base)
    return (base[:200] if len(base) > 200 else base) or "employee_file.bin"


def employee_file_row_to_dict(r, file_access_url_fn: Callable[[str], str]) -> Dict[str, Any]:
    sp = (r.stored_path or "").strip()
    mk = (getattr(r, "media_kind", None) or "").strip()
    if not mk:
        mk = handbook_suffix_to_media_kind(os.path.splitext(r.original_filename or "")[1].lower())
    return {
        "id": r.id,
        "client_id": r.client_id,
        "original_filename": r.original_filename or "",
        "stored_path": sp,
        "preview_url": file_access_url_fn(sp),
        "status": employee_file_normalize_status(getattr(r, "status", None) or "draft"),
        "media_kind": mk,
        "created_at": r.created_at.isoformat() if r.created_at else "",
        "updated_at": handbook_dt_iso(getattr(r, "updated_at", None)),
    }
