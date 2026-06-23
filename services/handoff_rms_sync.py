"""Sync approved handoff requirement positions into RMS jobs."""
from __future__ import annotations

from typing import Any, Dict, Type

from fastapi import HTTPException
from sqlalchemy.orm import Session

from handoff_core import parse_requirement_json
from schemas.rms import utc_date_str


def _resolve_owner_user_id(handoff: Any, operator_user_id: int) -> int:
    owner = int(getattr(handoff, "delivery_owner_user_id", None) or 0)
    if owner > 0:
        return owner
    if operator_user_id > 0:
        return operator_user_id
    raise HTTPException(status_code=400, detail="交接单未指定交付负责人，无法同步到 RMS")


def sync_handoff_positions_to_rms_jobs(
    db: Session,
    handoff: Any,
    *,
    RmsJob: Type[Any],
    operator_user_id: int,
) -> Dict[str, int]:
    req = parse_requirement_json(handoff.requirement_json)
    positions = req.get("positions") or []
    location = str((req.get("context") or {}).get("location") or "").strip()
    owner_user_id = _resolve_owner_user_id(handoff, operator_user_id)
    now = utc_date_str()
    created = 0
    updated = 0

    for p in positions:
        title = str(p.get("role") or "").strip()
        if not title:
            continue
        try:
            headcount = max(1, int(p.get("headcount") or 1))
        except (TypeError, ValueError):
            headcount = 1

        q = db.query(RmsJob).filter(
            RmsJob.client_id == handoff.client_id,
            RmsJob.title == title,
        )
        if location:
            q = q.filter(RmsJob.location == location)
        existing = q.first()

        if existing:
            existing.headcount = headcount
            existing.updated_at = now
            if location and not str(existing.location or "").strip():
                existing.location = location
            updated += 1
        else:
            db.add(
                RmsJob(
                    client_id=handoff.client_id,
                    title=title,
                    location=location,
                    headcount=headcount,
                    owner_user_id=owner_user_id,
                    status="open",
                    priority="medium",
                    created_at=now,
                    updated_at=now,
                )
            )
            created += 1

    return {"created": created, "updated": updated, "synced": created + updated}
