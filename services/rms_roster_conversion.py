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

OFFER_FINANCIAL_ROSTER_KEYS = (
    "monthly_quote_tax",
    "pre_tax_salary",
    "gms",
    "gm_pct",
)

ROSTER_MONTHLY_WORK_DAYS = 20.67
ROSTER_MONTHLY_HOURS = 165.36


def _format_amount_display(amount: Any) -> str:
    raw = str(amount or "").strip().replace(",", "")
    if not raw:
        return ""
    try:
        n = float(raw)
    except ValueError:
        return raw
    if abs(n - round(n)) < 1e-9:
        return f"{int(round(n)):,}"
    text = f"{n:,.2f}".rstrip("0").rstrip(".")
    return text


def _format_quote_tax_display(amount: Any, unit: Any) -> str:
    _ = unit
    return _format_amount_display(amount)


def _parse_offer_amount(raw: Any) -> float:
    text = str(raw or "").strip().replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        raise HTTPException(status_code=400, detail="Offer 报价格式无效")


def _format_roster_amount_storage(amount: float) -> str:
    if amount <= 0:
        return ""
    if abs(amount - round(amount)) < 1e-9:
        return str(int(round(amount)))
    return f"{amount:.2f}".rstrip("0").rstrip(".")


def offer_quote_to_roster_monthly_amount(amount: Any, unit: Any) -> str:
    raw = _parse_offer_amount(amount)
    if raw <= 0:
        return ""
    u = str(unit or "").strip()
    if u == "人天":
        monthly = raw * ROSTER_MONTHLY_WORK_DAYS
    elif u == "人时":
        monthly = raw * ROSTER_MONTHLY_HOURS
    else:
        monthly = raw
    return _format_roster_amount_storage(monthly)


def _format_gm_pct_for_roster(val: Any) -> str:
    s = str(val or "").strip().replace("\uff05", "%")
    if not s:
        return ""
    if s.endswith("%"):
        return s
    return f"{s}%"


def _approved_offer_for_application(
    db: Session,
    application_id: int,
    RmsOfferRecord: Type[Any],
) -> Any:
    return (
        db.query(RmsOfferRecord)
        .filter(
            RmsOfferRecord.application_id == int(application_id),
            RmsOfferRecord.status == "approved",
        )
        .order_by(RmsOfferRecord.id.desc())
        .first()
    )


def _apply_offer_financials_to_roster_payload(payload: Dict[str, str], offer_record: Any) -> Dict[str, str]:
    out = dict(payload)
    out["monthly_quote_tax"] = offer_quote_to_roster_monthly_amount(
        getattr(offer_record, "monthly_quote_tax", None),
        getattr(offer_record, "quote_tax_unit", None),
    )
    out["pre_tax_salary"] = str(getattr(offer_record, "pre_tax_salary", None) or "").strip()
    out["gms"] = str(getattr(offer_record, "gm_amount", None) or "").strip()
    out["gm_pct"] = _format_gm_pct_for_roster(getattr(offer_record, "gm_pct", None))
    return out


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


def _build_roster_payload_prefill(
    application: Any,
    candidate: Any,
    job: Any,
    client: Any,
    *,
    offer_record: Any = None,
) -> Dict[str, str]:
    hired_at = (getattr(application, "hired_at", None) or "").strip()
    entry_date = hired_at[:10] if hired_at else utc_date_str()
    if offer_record is not None:
        planned = str(getattr(offer_record, "planned_onboard_date", None) or "").strip()
        if planned:
            entry_date = planned[:10]
    app_id = int(application.id)
    source = (getattr(candidate, "source", None) or "").strip()
    payload = {
        "employment_status": "在职",
        "full_name": (getattr(candidate, "name", None) or "").strip(),
        "contact_info": (getattr(candidate, "phone", None) or "").strip(),
        "customer_name": (getattr(client, "name", None) or "").strip(),
        "work_location": (getattr(job, "location", None) or "").strip(),
        "position_title": (getattr(job, "title", None) or "").strip(),
        "business_line": "",
        "entry_date": entry_date,
        "regularization_status": "未转正",
        "monthly_quote_tax": "",
        "pre_tax_salary": "",
        "gms": "",
        "gm_pct": "",
        "zntx_onboarding_channel": source,
        "remarks": f"来自 RMS application #{app_id}",
    }
    if offer_record is not None:
        payload = _apply_offer_financials_to_roster_payload(payload, offer_record)
    return payload


def get_roster_draft(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    *,
    RmsApplication: Type[Any],
    RmsCandidate: Type[Any],
    RmsJob: Type[Any],
    RmsOfferRecord: Type[Any],
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
    offer = _approved_offer_for_application(db, application_id, RmsOfferRecord)
    if not offer:
        raise HTTPException(status_code=400, detail="未找到已通过的 Offer 审批，无法转入花名册")
    payload = _build_roster_payload_prefill(
        app,
        candidate,
        job,
        client,
        offer_record=offer,
    )
    return {
        "application_id": app.id,
        "converted_to_roster_entry_id": getattr(app, "converted_to_roster_entry_id", None),
        "client_id": int(app.client_id),
        "offer_financial_locked": True,
        "quote_tax_unit": str(getattr(offer, "quote_tax_unit", None) or "").strip(),
        "quote_tax_display": _format_amount_display(payload["monthly_quote_tax"]),
        "roster_payload": payload,
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
    RmsOfferRecord: Type[Any],
    AuditLog: Type[Any],
) -> Dict[str, Any]:
    app, candidate, _job, _client = _load_convertible_application(
        db,
        ctx,
        application_id,
        scope_action="write",
        RmsApplication=RmsApplication,
        RmsCandidate=RmsCandidate,
        RmsJob=RmsJob,
        Client=Client,
    )
    offer = _approved_offer_for_application(db, application_id, RmsOfferRecord)
    if not offer:
        raise HTTPException(status_code=400, detail="未找到已通过的 Offer 审批，无法转入花名册")
    request_body = body if isinstance(body, dict) else {}
    merged = dict(request_body)
    merged = _apply_offer_financials_to_roster_payload(merged, offer)
    data = _validate_roster_create_payload(db, int(app.client_id), merged, RosterEntry, Client)
    if not str(data.get("zntx_onboarding_channel", "")).strip():
        source = (getattr(candidate, "source", None) or "").strip()
        if source:
            data["zntx_onboarding_channel"] = source

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
