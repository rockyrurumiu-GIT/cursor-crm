"""Delivery Interviews business logic — migrated from main.py (Phase 5C)."""
from __future__ import annotations

import csv
import io
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple, Type

from fastapi import HTTPException
from sqlalchemy.orm import Session

from schemas.delivery_interviews import (
    INTERVIEW_EXPORT_HEADERS,
    INTERVIEW_HEADER_MAP,
)


def normalize_interview_person_name(raw: Any) -> str:
    """与前端员工访谈提示 normalizePersonName 一致：strip + 合并连续空白。"""
    s = str(raw or "").strip()
    return re.sub(r"\s+", " ", s)


def interview_mark_left_for_normalized_name_keys(
    db: Session,
    client_id: int,
    name_keys: Set[str],
    InterviewEntry: Type,
) -> int:
    """访谈标离职（免校验）：仅写 employment_status；不 commit。name_keys 须已规范化。"""
    if client_id <= 0 or not name_keys:
        return 0
    rows = (
        db.query(InterviewEntry)
        .filter(InterviewEntry.client_id == client_id)
        .order_by(InterviewEntry.id)
        .all()
    )
    matched = 0
    for inv in rows:
        if normalize_interview_person_name(inv.full_name) not in name_keys:
            continue
        matched += 1
        inv.employment_status = "离职"
    return matched


def interview_entry_to_dict(e) -> Dict[str, Any]:
    return {
        "id": e.id,
        "client_id": e.client_id,
        "serial_no": e.serial_no or "",
        "full_name": e.full_name or "",
        "employment_status": e.employment_status or "",
        "contact": e.contact or "",
        "project_name": e.project_name or "",
        "position": e.position or "",
        "employee_q1": e.employee_q1 or "",
        "onboarding_time": e.onboarding_time or "",
        "interview_date": e.interview_date or "",
        "satisfaction": e.satisfaction or "",
        "delivery_judgment": e.delivery_judgment or "",
        "employee_requests": e.employee_requests or "",
        "delivery_todos": e.delivery_todos or "",
        "work_location": e.work_location or "",
        "hometown": e.hometown or "",
        "followup_1d": e.followup_1d or "",
        "followup_7d": e.followup_7d or "",
        "followup_30d": e.followup_30d or "",
        "followup_90d": e.followup_90d or "",
    }


def normalize_interview_payload(d: Dict[str, Any]) -> Dict[str, str]:
    keys = [
        "full_name",
        "employment_status",
        "contact",
        "project_name",
        "position",
        "employee_q1",
        "onboarding_time",
        "interview_date",
        "satisfaction",
        "delivery_judgment",
        "employee_requests",
        "delivery_todos",
        "work_location",
        "hometown",
        "followup_1d",
        "followup_7d",
        "followup_30d",
        "followup_90d",
    ]
    out: Dict[str, str] = {}
    for k in keys:
        v = d.get(k, "")
        if v is None:
            v = ""
        out[k] = str(v).strip()
    return out


def validate_interview_business_fields(data: Dict[str, str]) -> None:
    if len(str(data.get("delivery_judgment", "")).strip()) < 20:
        raise HTTPException(status_code=400, detail="交付判断至少需要填写20个字")
    if len(str(data.get("delivery_todos", "")).strip()) < 10:
        raise HTTPException(status_code=400, detail="交付待办事项至少需要填写10个字")


def assert_interview_delivery_judgment_unique(
    db: Session,
    client_id: int,
    full_name: str,
    delivery_judgment: str,
    InterviewEntry: Type,
    exclude_row_id: Optional[int] = None,
) -> None:
    name = str(full_name or "").strip()
    judgment = str(delivery_judgment or "").strip()
    if not name or not judgment:
        return
    q = db.query(InterviewEntry).filter(InterviewEntry.client_id == client_id)
    if exclude_row_id is not None:
        q = q.filter(InterviewEntry.id != exclude_row_id)
    for row in q.all():
        if str(row.full_name or "").strip() == name and str(row.delivery_judgment or "").strip() == judgment:
            raise HTTPException(status_code=409, detail="同一员工的多条访谈记录中，交付判断内容不能重复")


def resequence_interview_serial_no(db: Session, client_id: int, InterviewEntry: Type) -> None:
    rows = (
        db.query(InterviewEntry)
        .filter(InterviewEntry.client_id == client_id)
        .order_by(InterviewEntry.id)
        .all()
    )
    for idx, row in enumerate(rows, start=1):
        row.serial_no = str(idx)


def interview_display_serial_pairs(rows: List) -> List[Tuple[int, Any]]:
    """按 id 升序；同一「员工姓名」共用同一序号（首次出现递增，重名复用）。姓名为空时归为同一组。"""
    sorted_rows = sorted(rows, key=lambda e: e.id or 0)
    name_to_sn: Dict[str, int] = {}
    next_sn = 1
    out: List[Tuple[int, Any]] = []
    for e in sorted_rows:
        name = str(e.full_name or "").strip()
        key = name if name else "__empty__"
        if key not in name_to_sn:
            name_to_sn[key] = next_sn
            next_sn += 1
        out.append((name_to_sn[key], e))
    return out


def write_interview_backup_csv(client, rows: List, backup_dir: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(ch for ch in client.name if ch.isalnum() or ch in (" ", "-", "_")).strip() or f"client_{client.id}"
    name = f"interview_backup_{safe_name}__cid{client.id}__{ts}.csv"
    path = os.path.join(backup_dir, name)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(INTERVIEW_EXPORT_HEADERS)
        for sn, e in interview_display_serial_pairs(rows):
            d = interview_entry_to_dict(e)
            cells = [str(sn)] + [d.get(INTERVIEW_HEADER_MAP[h], "") for h in INTERVIEW_EXPORT_HEADERS[1:]]
            writer.writerow(cells)
    return name
