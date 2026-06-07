"""RMS hired applications vs roster consistency checks."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Type

from sqlalchemy.orm import Session

from auth.service import AuthContext
from services.date_utils import parse_loose_date
from services.delivery_roster import contact_dedup_key


def _normalize_hired_date(value: str) -> str:
    d = parse_loose_date(value)
    if d is None:
        return (value or "").strip()
    return d.strftime("%Y-%m-%d")


def _roster_entry_date_str(entry: Any) -> str:
    raw = getattr(entry, "entry_date", None) or ""
    d = parse_loose_date(raw)
    if d is None:
        return str(raw).strip()
    return d.strftime("%Y-%m-%d")


def _match_roster_by_phone(
    db: Session,
    phone: str,
    RosterEntry: Type[Any],
) -> List[Any]:
    key = contact_dedup_key(phone)
    if not key:
        return []
    rows = db.query(RosterEntry).all()
    return [r for r in rows if contact_dedup_key(getattr(r, "contact_info", None)) == key]


def _match_roster_by_name_client(
    db: Session,
    client_id: int,
    name: str,
    RosterEntry: Type[Any],
) -> List[Any]:
    nm = (name or "").strip()
    if not nm:
        return []
    return (
        db.query(RosterEntry)
        .filter(RosterEntry.client_id == client_id, RosterEntry.full_name == nm)
        .all()
    )


def check_hired_roster_match(
    db: Session,
    ctx: AuthContext,
    application: Any,
    RmsCandidate: Type[Any],
    RosterEntry: Type[Any],
    Client: Type[Any],
) -> Dict[str, Any]:
    hired_at = _normalize_hired_date(getattr(application, "hired_at", None) or "")
    candidate = (
        db.query(RmsCandidate)
        .filter(RmsCandidate.id == application.candidate_id)
        .first()
    )
    phone = getattr(candidate, "phone", None) or "" if candidate else ""
    name = getattr(candidate, "name", None) or "" if candidate else ""

    matches: List[Any] = []
    if phone.strip():
        matches = _match_roster_by_phone(db, phone, RosterEntry)
    if not matches:
        matches = _match_roster_by_name_client(
            db, int(application.client_id), name, RosterEntry
        )

    base = {
        "rms_hired_at": hired_at,
        "roster_entry_date": "",
        "roster_row_id": None,
        "message": "",
    }

    if not matches:
        return {
            **base,
            "status": "missing",
            "message": "花名册尚无该人员，请后续创建员工档案",
        }

    if len(matches) > 1:
        return {
            **base,
            "status": "ambiguous",
            "message": "花名册存在多条疑似匹配人员，请人工核对",
        }

    entry = matches[0]
    entry_date = _roster_entry_date_str(entry)
    base["roster_entry_date"] = entry_date
    base["roster_row_id"] = entry.id

    if entry_date == hired_at:
        return {
            **base,
            "status": "matched",
            "message": "花名册入职时间一致",
        }

    return {
        **base,
        "status": "date_mismatch",
        "message": "RMS 入职时间与花名册入职时间不一致，请人工确认",
    }


def list_hired_roster_checks(
    db: Session,
    ctx: AuthContext,
    RmsApplication: Type[Any],
    RmsCandidate: Type[Any],
    RmsJob: Type[Any],
    RosterEntry: Type[Any],
    Client: Type[Any],
    *,
    client_id: Optional[int] = None,
    job_id: Optional[int] = None,
    recruiter_user_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    from services import rms_scope as rms_ds

    q = rms_ds.scoped_applications_query(db, ctx, RmsApplication, Client, action="read")
    q = q.filter(RmsApplication.status == "hired")
    if client_id is not None:
        q = q.filter(RmsApplication.client_id == client_id)
    if job_id is not None:
        q = q.filter(RmsApplication.job_id == job_id)
    if recruiter_user_id is not None:
        q = q.filter(RmsApplication.recommended_by == recruiter_user_id)
    if date_from:
        q = q.filter(RmsApplication.hired_at >= date_from)
    if date_to:
        q = q.filter(RmsApplication.hired_at <= date_to)

    apps = q.order_by(RmsApplication.id.desc()).all()
    clients = {c.id: c for c in db.query(Client).all()}
    jobs = {j.id: j for j in db.query(RmsJob).all()}
    candidates = {
        c.id: c for c in db.query(RmsCandidate).filter(
            RmsCandidate.id.in_([a.candidate_id for a in apps] or [-1])
        ).all()
    }

    items: List[Dict[str, Any]] = []
    summary = {"total_hired": 0, "matched": 0, "missing": 0, "date_mismatch": 0, "ambiguous": 0}

    for app in apps:
        chk = check_hired_roster_match(db, ctx, app, RmsCandidate, RosterEntry, Client)
        cand = candidates.get(app.candidate_id)
        job = jobs.get(app.job_id)
        client = clients.get(app.client_id)
        status = chk["status"]
        summary["total_hired"] += 1
        summary[status] = summary.get(status, 0) + 1
        items.append({
            "application_id": app.id,
            "candidate_id": app.candidate_id,
            "candidate_name": getattr(cand, "name", None) or "",
            "candidate_phone": getattr(cand, "phone", None) or "",
            "client_id": app.client_id,
            "client_name": getattr(client, "name", None) or "",
            "job_id": app.job_id,
            "job_title": getattr(job, "title", None) or "",
            "recommended_by": app.recommended_by,
            "hired_at": normalize_rms_date(app.hired_at),
            "roster_status": status,
            "roster_row_id": chk.get("roster_row_id"),
            "roster_entry_date": chk.get("roster_entry_date") or "",
            "message": chk.get("message") or "",
        })

    return {"summary": summary, "items": items}
