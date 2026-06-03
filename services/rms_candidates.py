"""RMS candidates business logic (Phase 2)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type

from fastapi import HTTPException
from sqlalchemy.orm import Session

from auth.service import AuthContext
from services import rms_scope as rms_ds


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


def candidate_to_dict(ctx: AuthContext, row: Any) -> Dict[str, Any]:
    can_view_contacts = ctx.is_super or "rms.contacts.view" in ctx.permissions
    phone = row.phone or ""
    email = row.email or ""
    wechat = row.wechat or ""
    if not can_view_contacts:
        phone = _mask_phone(phone)
        email = _mask_email(email)
        wechat = _mask_wechat(wechat)
    return {
        "id": row.id,
        "name": row.name or "",
        "phone": phone,
        "email": email,
        "wechat": wechat,
        "current_company": row.current_company or "",
        "current_title": row.current_title or "",
        "city": row.city or "",
        "source": row.source or "",
        "tags": row.tags or "[]",
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


def list_candidates(
    db: Session,
    ctx: AuthContext,
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
    *,
    q_text: Optional[str] = None,
) -> List[Dict[str, Any]]:
    q = _filtered_candidates_query(db, ctx, RmsCandidate, RmsApplication, Client)
    if q_text:
        like = f"%{q_text.strip()}%"
        q = q.filter(RmsCandidate.name.like(like))
    rows = q.order_by(RmsCandidate.id.desc()).all()
    return [candidate_to_dict(ctx, r) for r in rows]


def get_candidate(
    db: Session,
    ctx: AuthContext,
    candidate_id: int,
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
) -> Dict[str, Any]:
    row = _filtered_candidates_query(db, ctx, RmsCandidate, RmsApplication, Client).filter(
        RmsCandidate.id == candidate_id
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="候选人不存在")
    return candidate_to_dict(ctx, row)


def create_candidate(
    db: Session,
    ctx: AuthContext,
    data: Dict[str, Any],
    RmsCandidate: Type[Any],
) -> Dict[str, Any]:
    now = _utc_now_str()
    row = RmsCandidate(
        name=str(data.get("name") or "").strip(),
        phone=str(data.get("phone") or "").strip(),
        email=str(data.get("email") or "").strip(),
        wechat=str(data.get("wechat") or "").strip(),
        current_company=str(data.get("current_company") or "").strip(),
        current_title=str(data.get("current_title") or "").strip(),
        city=str(data.get("city") or "").strip(),
        source=str(data.get("source") or "").strip(),
        tags=str(data.get("tags") or "[]").strip() or "[]",
        created_by_user_id=ctx.user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return candidate_to_dict(ctx, row)


def update_candidate(
    db: Session,
    ctx: AuthContext,
    candidate_id: int,
    data: Dict[str, Any],
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
) -> Dict[str, Any]:
    row = _filtered_candidates_query(db, ctx, RmsCandidate, RmsApplication, Client).filter(
        RmsCandidate.id == candidate_id
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="候选人不存在")
    for field in (
        "name", "phone", "email", "wechat", "current_company",
        "current_title", "city", "source", "tags",
    ):
        if data.get(field) is not None:
            setattr(row, field, str(data[field]).strip())
    row.updated_at = _utc_now_str()
    db.commit()
    db.refresh(row)
    return candidate_to_dict(ctx, row)
