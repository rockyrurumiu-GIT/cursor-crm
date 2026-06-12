"""RMS hired application → delivery roster conversion (Phase 5A)."""
from __future__ import annotations

from typing import Any, Dict, Literal, Tuple, Type

from fastapi import HTTPException
from sqlalchemy.orm import Session

from auth.service import AuthContext
from schemas.delivery_roster import (
    ROSTER_CREATE_REQUIRED_FIELDS,
    ROSTER_REQUIRED_LABELS,
)
from schemas.rms import utc_date_str
from services import rms_applications as app_svc
from services import rms_scope as rms_ds
from services.delivery_roster import (
    apply_roster_salary_quote_ratio,
    assert_roster_contact_unique,
    normalize_roster_payload,
    resequence_roster_serial_no,
    resolve_roster_customer_client,
    roster_entry_to_dict,
    validate_roster_business_fields,
)

ScopeAction = Literal["read", "write"]


def _load_convertible_application(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    *,
    scope_action: ScopeAction,
    RmsApplication: Type[Any],
    RmsCandidate: Type[Any],
    RmsJob: Type[Any],
    Client: Type[Any],
) -> Tuple[Any, Any, Any, Any]:
    row = (
        rms_ds.scoped_applications_query(db, ctx, RmsApplication, Client, action=scope_action)
        .filter(RmsApplication.id == application_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="推荐记录不存在")

    if (row.status or "").strip() != "hired":
        raise HTTPException(status_code=400, detail="仅已入职推荐记录可转入花名册")

    if getattr(row, "converted_to_roster_entry_id", None):
        raise HTTPException(status_code=409, detail="该推荐记录已转入花名册")

    candidate = db.query(RmsCandidate).filter(RmsCandidate.id == row.candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=400, detail="候选人不存在")

    job = db.query(RmsJob).filter(RmsJob.id == row.job_id).first()
    if not job:
        raise HTTPException(status_code=400, detail="岗位不存在")

    client = db.query(Client).filter(Client.id == row.client_id).first()
    if not client:
        raise HTTPException(status_code=400, detail="客户不存在")

    return row, candidate, job, client


def _build_roster_payload_prefill(application: Any, candidate: Any, job: Any, client: Any) -> Dict[str, str]:
    hired_at = (getattr(application, "hired_at", None) or "").strip()
    entry_date = hired_at[:10] if hired_at else utc_date_str()
    app_id = int(application.id)
    return {
        "employment_status": "在职",
        "full_name": (getattr(candidate, "name", None) or "").strip(),
        "contact_info": (getattr(candidate, "phone", None) or "").strip(),
        "customer_name": (getattr(client, "name", None) or "").strip(),
        "work_location": (getattr(job, "location", None) or "").strip(),
        "position_title": (getattr(job, "title", None) or "").strip(),
        "business_line": "",
        "entry_date": entry_date,
        "monthly_quote_tax": "",
        "pre_tax_salary": "",
        "gms": "",
        "gm_pct": "",
        "zntx_onboarding_channel": "RMS",
        "remarks": f"来自 RMS application #{app_id}",
    }


def get_roster_draft(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    *,
    RmsApplication: Type[Any],
    RmsCandidate: Type[Any],
    RmsJob: Type[Any],
    Client: Type[Any],
) -> Dict[str, Any]:
    app, candidate, job, client = _load_convertible_application(
        db,
        ctx,
        application_id,
        scope_action="read",
        RmsApplication=RmsApplication,
        RmsCandidate=RmsCandidate,
        RmsJob=RmsJob,
        Client=Client,
    )
    return {
        "application_id": app.id,
        "converted_to_roster_entry_id": getattr(app, "converted_to_roster_entry_id", None),
        "client_id": int(app.client_id),
        "roster_payload": _build_roster_payload_prefill(app, candidate, job, client),
    }


def _validate_roster_create_payload(
    db: Session,
    client_id: int,
    body: Dict[str, Any],
    RosterEntry: Type[Any],
    Client: Type[Any],
) -> Dict[str, str]:
    data = normalize_roster_payload(body if isinstance(body, dict) else {})
    missing = [k for k in ROSTER_CREATE_REQUIRED_FIELDS if not str(data.get(k, "")).strip()]
    if missing:
        labels = [ROSTER_REQUIRED_LABELS.get(k, k) for k in missing]
        raise HTTPException(status_code=400, detail=f"新增失败，以下必填项未填写：{'、'.join(labels)}")
    validate_roster_business_fields(data)
    apply_roster_salary_quote_ratio(data)
    assert_roster_contact_unique(db, client_id, data.get("contact_info", ""), RosterEntry)
    mc, normalized_cn = resolve_roster_customer_client(db, data.get("customer_name", ""), Client)
    if mc:
        data["customer_name"] = normalized_cn
    return data


def convert_application_to_roster(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    body: Dict[str, Any],
    *,
    operator_username: str,
    RmsApplication: Type[Any],
    RmsCandidate: Type[Any],
    RmsJob: Type[Any],
    Client: Type[Any],
    RosterEntry: Type[Any],
    AuditLog: Type[Any],
) -> Dict[str, Any]:
    app, _candidate, _job, _client = _load_convertible_application(
        db,
        ctx,
        application_id,
        scope_action="write",
        RmsApplication=RmsApplication,
        RmsCandidate=RmsCandidate,
        RmsJob=RmsJob,
        Client=Client,
    )
    data = _validate_roster_create_payload(db, int(app.client_id), body, RosterEntry, Client)

    try:
        entry = RosterEntry(client_id=int(app.client_id), **data)
        db.add(entry)
        db.flush()
        app.converted_to_roster_entry_id = entry.id
        app.converted_to_roster_at = utc_date_str()
        app.converted_to_roster_by = ctx.user_id
        resequence_roster_serial_no(db, int(app.client_id), RosterEntry)
        db.add(
            AuditLog(
                client_id=int(app.client_id),
                operator=operator_username,
                action=f"RMS转入花名册: {data.get('full_name') or ('#' + str(entry.id))}",
            )
        )
        db.commit()
        db.refresh(entry)
        db.refresh(app)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return {
        "roster_entry": roster_entry_to_dict(entry),
        "application": app_svc.application_to_dict(app),
    }
