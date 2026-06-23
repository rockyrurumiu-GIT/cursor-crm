"""Delivery employee file business logic."""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Type

from fastapi import HTTPException
from sqlalchemy.orm import Session

from schemas.delivery_employee_files import (
    EMPLOYEE_FILE_STATUS_SET,
    LABOR_CONTRACT_DOCUMENT_TYPE,
)
from services.delivery_handbook import handbook_dt_iso, handbook_suffix_to_media_kind
from services.delivery_roster import contact_dedup_key


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


def labor_contract_year(contract_sign_date: Optional[str]) -> int:
    s = str(contract_sign_date or "").strip()
    if len(s) >= 4 and s[:4].isdigit():
        return int(s[:4])
    return datetime.now().year


def labor_contract_no_prefix(throme_staff_no: str, year: int) -> str:
    return f"TRM-LC-{throme_staff_no}-{year}-"


def resolve_roster_entry_by_name_phone(
    db: Session,
    client_id: int,
    full_name: str,
    phone: str,
    RosterEntry: Type[Any],
) -> Any:
    nm = str(full_name or "").strip()
    if not nm:
        raise HTTPException(status_code=400, detail="请填写员工姓名")
    phone_key = contact_dedup_key(phone)
    if not phone_key:
        raise HTTPException(status_code=400, detail="请填写手机号")

    rows = (
        db.query(RosterEntry)
        .filter(RosterEntry.client_id == int(client_id), RosterEntry.full_name == nm)
        .all()
    )
    matches = [r for r in rows if contact_dedup_key(getattr(r, "contact_info", None)) == phone_key]

    if not matches:
        raise HTTPException(status_code=409, detail="未匹配到花名册员工，请确认姓名和手机号")
    if len(matches) > 1:
        raise HTTPException(status_code=409, detail="匹配到多个花名册员工，请联系管理员处理")

    entry = matches[0]
    throme = str(getattr(entry, "throme_staff_no", None) or "").strip()
    if not throme:
        raise HTTPException(status_code=409, detail="员工缺少索摩工号，请先补齐花名册工号")
    return entry


def count_same_year_labor_contracts(
    db: Session,
    throme_staff_no: str,
    year: int,
    DeliveryEmployeeFile: Type[Any],
) -> int:
    prefix = labor_contract_no_prefix(throme_staff_no, year)
    return (
        db.query(DeliveryEmployeeFile)
        .filter(DeliveryEmployeeFile.labor_contract_no.like(f"{prefix}%"))
        .count()
    )


def generate_labor_contract_no(
    db: Session,
    throme_staff_no: str,
    year: int,
    DeliveryEmployeeFile: Type[Any],
) -> str:
    prefix = labor_contract_no_prefix(throme_staff_no, year)
    rows = (
        db.query(DeliveryEmployeeFile.labor_contract_no)
        .filter(DeliveryEmployeeFile.labor_contract_no.like(f"{prefix}%"))
        .all()
    )
    max_seq = 0
    for (no,) in rows:
        tail = (no or "")[len(prefix) :]
        if tail.isdigit():
            max_seq = max(max_seq, int(tail))
    return f"{prefix}{max_seq + 1:02d}"


def prepare_labor_contract_upload(
    db: Session,
    *,
    client_id: int,
    employee_full_name: str,
    employee_contact_info: str,
    contract_sign_date: str,
    contract_valid_until: str = "",
    confirm_same_year_renewal: int,
    RosterEntry: Type[Any],
    DeliveryEmployeeFile: Type[Any],
) -> Dict[str, Any]:
    entry = resolve_roster_entry_by_name_phone(
        db, client_id, employee_full_name, employee_contact_info, RosterEntry
    )
    throme = str(entry.throme_staff_no or "").strip()
    year = labor_contract_year(contract_sign_date)
    existing_count = count_same_year_labor_contracts(db, throme, year, DeliveryEmployeeFile)
    if existing_count > 0 and int(confirm_same_year_renewal or 0) != 1:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "same_year_labor_contract_exists",
                "message": "该员工已在本年上传过合同，是否为同年续约？",
                "existing_count": existing_count,
            },
        )
    labor_no = generate_labor_contract_no(db, throme, year, DeliveryEmployeeFile)
    sign_date = str(contract_sign_date or "").strip()
    valid_until = str(contract_valid_until or "").strip()
    return {
        "document_type": LABOR_CONTRACT_DOCUMENT_TYPE,
        "employee_full_name": str(employee_full_name or "").strip(),
        "employee_contact_info": str(employee_contact_info or "").strip(),
        "roster_entry_id": int(entry.id),
        "throme_staff_no": throme,
        "labor_contract_no": labor_no,
        "contract_sign_date": sign_date,
        "contract_valid_until": valid_until,
    }


def is_labor_contract_row(row) -> bool:
    return str(getattr(row, "document_type", None) or "").strip() == LABOR_CONTRACT_DOCUMENT_TYPE


def labor_contract_delete_is_hard(row) -> bool:
    """草稿劳动合同误传可真删，释放编号；已发布/已作废仍保留记录。"""
    if not is_labor_contract_row(row):
        return False
    return employee_file_normalize_status(getattr(row, "status", None)) == "draft"


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
        "document_type": getattr(r, "document_type", None) or "",
        "employee_full_name": getattr(r, "employee_full_name", None) or "",
        "employee_contact_info": getattr(r, "employee_contact_info", None) or "",
        "roster_entry_id": getattr(r, "roster_entry_id", None),
        "throme_staff_no": getattr(r, "throme_staff_no", None) or "",
        "labor_contract_no": getattr(r, "labor_contract_no", None) or "",
        "contract_sign_date": getattr(r, "contract_sign_date", None) or "",
        "contract_valid_until": getattr(r, "contract_valid_until", None) or "",
        "created_at": r.created_at.isoformat() if r.created_at else "",
        "updated_at": handbook_dt_iso(getattr(r, "updated_at", None)),
    }
