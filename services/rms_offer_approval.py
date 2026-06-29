"""RMS Offer approval workflow (Phase 6B)."""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional, Set, Type

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

import security_foundation as sec
from auth.service import AuthContext
from schemas.rms import (
    OFFER_APPROVAL_REQUIRED_FIELDS,
    OFFER_APPROVAL_REQUIRED_LABELS,
    OFFER_PROBATION_DISCOUNT_MONTHS,
    OFFER_QUOTE_TAX_UNITS,
    OFFER_RECORD_TAB_STATUSES,
    normalize_rms_date,
    utc_date_str,
)
from services import rms_applications as app_svc
from services import rms_scope as rms_ds
from services.rms_offer_approvers import (
    STEP_DEPT_SUPERIOR,
    STEP_GM,
    STEP_OPS_HEAD,
    approval_node_label,
)
from services.rms_offer_approval_config import approval_step_short_label, resolve_offer_approvers
from services.rms_roster_conversion import _build_roster_payload_prefill
from services.quote_finance import apply_offer_quote_fields, compute_monthly_quote_tax


def _username_for_user_id(db: Session, user_id: Optional[int]) -> str:
    if user_id is None:
        return ""
    row = db.execute(
        text("SELECT username FROM sys_user WHERE id = :uid LIMIT 1"),
        {"uid": int(user_id)},
    ).first()
    return (row[0] or "").strip() if row else ""


def _display_name_for_user_id(db: Session, user_id: Optional[int]) -> str:
    if user_id is None:
        return ""
    row = db.execute(
        text("SELECT display_name, username FROM sys_user WHERE id = :uid LIMIT 1"),
        {"uid": int(user_id)},
    ).first()
    if not row:
        return ""
    dn = (row[0] or "").strip()
    un = (row[1] or "").strip()
    return dn or un


def _user_label_for_user_id(db: Session, user_id: Optional[int]) -> str:
    return _display_name_for_user_id(db, user_id)


def _offer_link(offer_record_id: int) -> str:
    return f"/rms?tab=offerManagement&offer={offer_record_id}"


def _add_notification(
    db: Session,
    CrmNotification: Type[Any],
    *,
    username: str,
    ntype: str,
    message: str,
    client_id: Optional[int] = None,
    application_id: Optional[int] = None,
    offer_record_id: Optional[int] = None,
    link_url: str = "",
) -> None:
    if not username:
        return
    db.add(
        CrmNotification(
            username=username,
            ntype=ntype,
            handoff_id=None,
            client_id=client_id,
            application_id=application_id,
            offer_record_id=offer_record_id,
            link_url=link_url or "",
            message=message,
        )
    )


def _get_readable_application_row(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    RmsApplication: Type[Any],
    Client: Type[Any],
) -> Any:
    row = (
        rms_ds.scoped_applications_query(db, ctx, RmsApplication, Client, action="read")
        .filter(RmsApplication.id == application_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="推荐记录不存在")
    return row


def _load_application_bundle(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    *,
    scope_action: str,
    RmsApplication: Type[Any],
    RmsCandidate: Type[Any],
    RmsJob: Type[Any],
    Client: Type[Any],
) -> tuple[Any, Any, Any, Any]:
    if scope_action == "write":
        row = app_svc._get_writable_application(db, ctx, application_id, RmsApplication, Client)
    else:
        row = _get_readable_application_row(db, ctx, application_id, RmsApplication, Client)
    candidate = db.query(RmsCandidate).filter(RmsCandidate.id == row.candidate_id).first()
    job = db.query(RmsJob).filter(RmsJob.id == row.job_id).first()
    client = db.query(Client).filter(Client.id == row.client_id).first()
    if not candidate:
        raise HTTPException(status_code=400, detail="候选人不存在")
    if not job:
        raise HTTPException(status_code=400, detail="岗位不存在")
    if not client:
        raise HTTPException(status_code=400, detail="客户不存在")
    return row, candidate, job, client


OFFER_QUOTE_ATTACHMENT_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"})
MAX_OFFER_QUOTE_ATTACHMENT_BYTES = 10 * 1024 * 1024
OFFER_QUOTE_ATTACHMENT_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


async def upload_offer_quote_attachment(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    upload: UploadFile,
    *,
    upload_dir: str,
    RmsApplication: Type[Any],
    Client: Type[Any],
) -> Dict[str, str]:
    """Store a客户报价确认 image attachment for an offer approval submission."""
    app = app_svc._get_writable_application(db, ctx, application_id, RmsApplication, Client)
    raw_name = upload.filename or ""
    ext = os.path.splitext(raw_name)[1].lower()
    if ext not in OFFER_QUOTE_ATTACHMENT_SUFFIXES:
        raise HTTPException(status_code=400, detail="仅支持图片格式（png/jpg/jpeg/gif/webp/bmp）")
    content = await upload.read()
    if len(content) > MAX_OFFER_QUOTE_ATTACHMENT_BYTES:
        raise HTTPException(status_code=400, detail="图片不能超过 10MB")
    safe = sec.safe_visit_attachment_name(raw_name)
    if not os.path.splitext(safe)[1]:
        safe = safe + ext
    rel = f"rms/offer_quotes/{int(app.id)}/{int(time.time() * 1000000)}_{safe}"
    try:
        abs_target = sec.resolve_upload_path(upload_dir, rel)
    except ValueError:
        raise HTTPException(status_code=400, detail="非法文件路径")
    os.makedirs(os.path.dirname(abs_target), exist_ok=True)
    with open(abs_target, "wb") as f:
        f.write(content)
    return {"path": rel, "file_name": raw_name or safe}


def _offer_form_dict(record: Any) -> Dict[str, str]:
    raw = getattr(record, "form_json", "") or ""
    if not raw:
        return {}
    try:
        form = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    if not isinstance(form, dict):
        return {}
    return {str(k): str(v or "").strip() for k, v in form.items()}


def _offer_quote_attachment_path(record: Any) -> str:
    return _offer_form_dict(record).get("quote_confirm_attachment", "")


def _submission_remark(record: Any) -> str:
    return _offer_form_dict(record).get("submission_remark", "")


def view_offer_quote_attachment(
    db: Session,
    ctx: AuthContext,
    offer_record_id: int,
    *,
    upload_dir: str,
    RmsOfferRecord: Type[Any],
    RmsOfferApprovalStep: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
) -> FileResponse:
    record = _get_offer_record_or_404(db, offer_record_id, RmsOfferRecord)
    approver_offer_ids = _pending_approver_offer_record_ids(
        db, ctx, [int(record.id)], RmsOfferApprovalStep=RmsOfferApprovalStep
    )
    scoped = rms_ds.scoped_applications_query(db, ctx, RmsApplication, Client, action="read")
    allowed_app_ids = {
        int(a.id)
        for a in scoped.filter(RmsApplication.id == int(record.application_id)).all()
    }
    client = (
        db.query(Client).filter(Client.id == int(record.client_id)).first()
        if record.client_id is not None
        else None
    )
    if not _can_view_offer_record(
        ctx,
        record,
        allowed_app_ids=allowed_app_ids,
        approver_offer_ids=approver_offer_ids,
        db=db,
        client=client,
    ):
        raise HTTPException(status_code=403, detail="无权查看该附件")
    rel = _offer_quote_attachment_path(record)
    if not rel:
        raise HTTPException(status_code=404, detail="无客户报价确认附件")
    try:
        abs_path = sec.resolve_upload_path(upload_dir, rel)
    except ValueError:
        raise HTTPException(status_code=400, detail="非法文件路径")
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="附件文件不存在")
    ext = os.path.splitext(abs_path)[1].lower()
    media_type = OFFER_QUOTE_ATTACHMENT_MEDIA_TYPES.get(ext, "application/octet-stream")
    return FileResponse(abs_path, media_type=media_type, content_disposition_type="inline")


def _validate_offer_body(body: Dict[str, Any]) -> Dict[str, str]:
    data = {k: str(body.get(k) or "").strip() for k in OFFER_APPROVAL_REQUIRED_FIELDS}
    missing = [k for k in OFFER_APPROVAL_REQUIRED_FIELDS if not data[k]]
    if missing:
        labels = [OFFER_APPROVAL_REQUIRED_LABELS.get(k, k) for k in missing]
        raise HTTPException(status_code=400, detail=f"以下必填项未填写：{'、'.join(labels)}")
    if data["probation_discount_months"] not in OFFER_PROBATION_DISCOUNT_MONTHS:
        raise HTTPException(status_code=400, detail="折扣月数须为不打折、1、2 或 3")
    if data["quote_tax_unit"] not in OFFER_QUOTE_TAX_UNITS:
        raise HTTPException(status_code=400, detail="报价单位须为人月、人天或人时")
    apply_offer_quote_fields(data)
    return data


def _pending_record_exists(db: Session, application_id: int, RmsOfferRecord: Type[Any]) -> bool:
    return (
        db.query(RmsOfferRecord)
        .filter(
            RmsOfferRecord.application_id == application_id,
            RmsOfferRecord.status == "pending",
        )
        .first()
        is not None
    )


def _write_status_history(
    db: Session,
    RmsApplicationStatusHistory: Type[Any],
    *,
    application_id: int,
    from_status: str,
    to_status: str,
    reason: str,
    note: str,
    changed_by: Optional[int],
) -> None:
    now = utc_date_str()
    db.add(
        RmsApplicationStatusHistory(
            application_id=application_id,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            note=note,
            changed_by=changed_by,
            changed_at=now,
        )
    )


def get_offer_approval_draft(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    *,
    RmsApplication: Type[Any],
    RmsCandidate: Type[Any],
    RmsJob: Type[Any],
    Client: Type[Any],
) -> Dict[str, Any]:
    app, candidate, job, client = _load_application_bundle(
        db,
        ctx,
        application_id,
        scope_action="read",
        RmsApplication=RmsApplication,
        RmsCandidate=RmsCandidate,
        RmsJob=RmsJob,
        Client=Client,
    )
    rms_ds.assert_can_submit_offer_approval(db, ctx, client)
    prefill = _build_roster_payload_prefill(app, candidate, job, client)
    return {
        "application_id": app.id,
        "status": app.status,
        "client_id": int(app.client_id),
        "offer_payload": {
            "full_name": prefill.get("full_name", ""),
            "contact_info": prefill.get("contact_info", ""),
            "customer_name": prefill.get("customer_name", ""),
            "work_location": prefill.get("work_location", ""),
            "position_title": prefill.get("position_title", ""),
            "monthly_quote_tax": prefill.get("monthly_quote_tax", ""),
            "quote_tax_unit": "",
            "pre_tax_salary": prefill.get("pre_tax_salary", ""),
            "probation_days": "",
            "probation_discount_months": "",
            "gm_amount": prefill.get("gms", ""),
            "gm_pct": prefill.get("gm_pct", ""),
            "planned_onboard_date": prefill.get("entry_date", ""),
        },
    }


def submit_offer_approval(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    body: Dict[str, Any],
    *,
    RmsApplication: Type[Any],
    RmsApplicationStatusHistory: Type[Any],
    RmsCandidate: Type[Any],
    RmsJob: Type[Any],
    RmsOfferRecord: Type[Any],
    RmsOfferApprovalStep: Type[Any],
    RmsOfferApprovalConfig: Type[Any],
    Client: Type[Any],
    CrmNotification: Type[Any],
) -> Dict[str, Any]:
    app, candidate, job, client = _load_application_bundle(
        db,
        ctx,
        application_id,
        scope_action="write",
        RmsApplication=RmsApplication,
        RmsCandidate=RmsCandidate,
        RmsJob=RmsJob,
        Client=Client,
    )
    if (app.status or "").strip() != "pending_offer":
        raise HTTPException(status_code=400, detail="仅待offer推荐记录可发起 Offer 审批")
    if _pending_record_exists(db, application_id, RmsOfferRecord):
        raise HTTPException(status_code=409, detail="该推荐记录已有进行中的 Offer 审批")

    rms_ds.assert_can_submit_offer_approval(db, ctx, client)

    validated = _validate_offer_body(body)
    applicant_user_id = ctx.user_id
    if applicant_user_id is None:
        raise HTTPException(status_code=400, detail="无法识别申请人")

    steps = resolve_offer_approvers(
        db,
        int(applicant_user_id),
        validated["gm_pct"],
        RmsOfferApprovalConfig=RmsOfferApprovalConfig,
    )
    from services.rms_offer_records import supersede_approved_offers

    supersede_approved_offers(
        db,
        application_id,
        reason="resubmitted",
        RmsOfferRecord=RmsOfferRecord,
    )
    now = utc_date_str()
    form = {k: str(body.get(k) or "").strip() for k in body.keys()} if isinstance(body, dict) else {}
    first_step = steps[0]

    record = RmsOfferRecord(
        application_id=application_id,
        candidate_id=int(candidate.id),
        job_id=int(job.id),
        client_id=int(client.id),
        status="pending",
        current_approval_node=first_step.step_type,
        gm_pct=validated["gm_pct"],
        gm_amount=validated["gm_amount"],
        monthly_quote_tax=validated["monthly_quote_tax"],
        quote_tax_unit=validated["quote_tax_unit"],
        quote_amount_tax=validated["quote_amount_tax"],
        monthly_billable_days=validated["monthly_billable_days"],
        daily_billable_hours=validated["daily_billable_hours"],
        pre_tax_salary=validated["pre_tax_salary"],
        probation_days=validated["probation_days"],
        probation_discount_months=validated["probation_discount_months"],
        planned_onboard_date=validated["planned_onboard_date"],
        reason="",
        form_json=json.dumps(form, ensure_ascii=False),
        created_by=ctx.user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    db.flush()

    for spec in steps:
        db.add(
            RmsOfferApprovalStep(
                offer_record_id=int(record.id),
                step_order=spec.step_order,
                step_type=spec.step_type,
                approver_user_id=spec.approver_user_id,
                status="pending" if spec.step_order == first_step.step_order else "waiting",
                comment="",
                acted_at="",
            )
        )

    raw_from = (app.status or "").strip()
    app.status = "offer_approval_pending"
    app.current_stage = "offer_approval_pending"
    app.last_activity_at = now
    app.updated_at = now
    _write_status_history(
        db,
        RmsApplicationStatusHistory,
        application_id=application_id,
        from_status=raw_from,
        to_status="offer_approval_pending",
        reason="offer_approval_submitted",
        note="",
        changed_by=ctx.user_id,
    )

    cand_name = (candidate.name or "").strip() or f"#{candidate.id}"
    approver_username = _username_for_user_id(db, first_step.approver_user_id)
    link = _offer_link(int(record.id))
    _add_notification(
        db,
        CrmNotification,
        username=approver_username,
        ntype="rms_offer_pending",
        message=f"待审批 Offer：{cand_name}（{client.name}）",
        client_id=int(client.id),
        application_id=application_id,
        offer_record_id=int(record.id),
        link_url=link,
    )
    db.commit()
    db.refresh(record)
    return offer_record_to_dict(db, record, RmsOfferApprovalStep=RmsOfferApprovalStep)


def _get_pending_step(db: Session, offer_record_id: int, RmsOfferApprovalStep: Type[Any]) -> Any:
    return (
        db.query(RmsOfferApprovalStep)
        .filter(
            RmsOfferApprovalStep.offer_record_id == offer_record_id,
            RmsOfferApprovalStep.status == "pending",
        )
        .order_by(RmsOfferApprovalStep.step_order.asc())
        .first()
    )


def _assert_pending_step_consistency(
    db: Session,
    record: Any,
    step: Any,
    *,
    RmsOfferApprovalStep: Type[Any],
) -> None:
    pending_count = (
        db.query(RmsOfferApprovalStep)
        .filter(
            RmsOfferApprovalStep.offer_record_id == int(record.id),
            RmsOfferApprovalStep.status == "pending",
        )
        .count()
    )
    if pending_count != 1:
        raise HTTPException(status_code=400, detail="审批节点状态异常，请联系管理员")
    node = (record.current_approval_node or "").strip()
    step_type = (step.step_type or "").strip()
    if node and step_type and node != step_type:
        raise HTTPException(status_code=400, detail="审批节点状态不一致")


def _can_view_offer_record(
    ctx: AuthContext,
    record: Any,
    *,
    allowed_app_ids: Set[int],
    approver_offer_ids: Set[int],
    db: Optional[Session] = None,
    client: Any = None,
) -> bool:
    if ctx.is_super:
        return True
    if db is not None and client is not None and rms_ds.can_view_offer_detail(db, ctx, client):
        return True
    record_id = int(record.id)
    app_id = int(record.application_id)
    status = (record.status or "").strip()
    if status == "pending":
        if record_id in approver_offer_ids:
            return True
        if ctx.user_id is not None and int(record.created_by or 0) == int(ctx.user_id):
            return True
        return False
    return app_id in allowed_app_ids


def _can_view_offer_detail_row(
    ctx: AuthContext,
    record: Any,
    *,
    approver_offer_ids: Set[int],
    db: Session,
    client: Any,
    can_approve: bool,
) -> bool:
    if can_approve:
        return True
    if rms_ds.can_view_offer_detail(db, ctx, client):
        return True
    status = (record.status or "").strip()
    return (
        status == "pending"
        and ctx.user_id is not None
        and int(record.created_by or 0) == int(ctx.user_id)
    )


def _can_approve_offer_record(
    ctx: AuthContext,
    record: Any,
    *,
    approver_offer_ids: Set[int],
) -> bool:
    if (record.status or "").strip() != "pending":
        return False
    return int(record.id) in approver_offer_ids


def _assert_step_approver(ctx: AuthContext, step: Any) -> None:
    if ctx.user_id is None or int(step.approver_user_id or 0) != int(ctx.user_id):
        raise HTTPException(status_code=403, detail="仅当前节点审批人可操作")


def _get_offer_record_or_404(db: Session, offer_record_id: int, RmsOfferRecord: Type[Any]) -> Any:
    row = db.query(RmsOfferRecord).filter(RmsOfferRecord.id == offer_record_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Offer 审批单不存在")
    return row


def approve_offer_step(
    db: Session,
    ctx: AuthContext,
    offer_record_id: int,
    comment: str,
    *,
    RmsApplication: Type[Any],
    RmsApplicationStatusHistory: Type[Any],
    RmsOfferRecord: Type[Any],
    RmsOfferApprovalStep: Type[Any],
    Client: Type[Any],
    CrmNotification: Type[Any],
) -> Dict[str, Any]:
    record = _get_offer_record_or_404(db, offer_record_id, RmsOfferRecord)
    if (record.status or "").strip() != "pending":
        raise HTTPException(status_code=400, detail="该 Offer 审批单不可审批")

    step = _get_pending_step(db, offer_record_id, RmsOfferApprovalStep)
    if not step:
        raise HTTPException(status_code=400, detail="无待审批节点")
    _assert_pending_step_consistency(db, record, step, RmsOfferApprovalStep=RmsOfferApprovalStep)
    _assert_step_approver(ctx, step)

    now = utc_date_str()
    step.status = "approved"
    step.comment = (comment or "").strip()
    step.acted_at = now

    next_step = (
        db.query(RmsOfferApprovalStep)
        .filter(
            RmsOfferApprovalStep.offer_record_id == offer_record_id,
            RmsOfferApprovalStep.status == "waiting",
        )
        .order_by(RmsOfferApprovalStep.step_order.asc())
        .first()
    )

    app = db.query(RmsApplication).filter(RmsApplication.id == record.application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="推荐记录不存在")

    if next_step:
        next_step.status = "pending"
        record.current_approval_node = next_step.step_type
        record.updated_at = now
        approver_username = _username_for_user_id(db, next_step.approver_user_id)
        link = _offer_link(int(record.id))
        _add_notification(
            db,
            CrmNotification,
            username=approver_username,
            ntype="rms_offer_pending",
            message=f"待审批 Offer（{approval_node_label(next_step.step_type)}）",
            client_id=int(record.client_id) if record.client_id else None,
            application_id=int(record.application_id),
            offer_record_id=int(record.id),
            link_url=link,
        )
    else:
        record.status = "approved"
        record.current_approval_node = ""
        record.updated_at = now
        raw_from = (app.status or "").strip()
        app.status = "onboarding"
        app.current_stage = "onboarding"
        app.last_activity_at = now
        app.updated_at = now
        _write_status_history(
            db,
            RmsApplicationStatusHistory,
            application_id=int(app.id),
            from_status=raw_from,
            to_status="onboarding",
            reason="offer_approval_passed",
            note="",
            changed_by=ctx.user_id,
        )
        applicant_username = _username_for_user_id(db, record.created_by)
        _add_notification(
            db,
            CrmNotification,
            username=applicant_username,
            ntype="rms_offer_approved",
            message="Offer 审批已通过，推荐记录已进入在途",
            client_id=int(record.client_id) if record.client_id else None,
            application_id=int(record.application_id),
            offer_record_id=int(record.id),
            link_url=_offer_link(int(record.id)),
        )

    db.commit()
    db.refresh(record)
    return offer_record_to_dict(db, record, RmsOfferApprovalStep=RmsOfferApprovalStep)


def reject_offer_step(
    db: Session,
    ctx: AuthContext,
    offer_record_id: int,
    reason: str,
    *,
    RmsApplication: Type[Any],
    RmsApplicationStatusHistory: Type[Any],
    RmsOfferRecord: Type[Any],
    RmsOfferApprovalStep: Type[Any],
    CrmNotification: Type[Any],
) -> Dict[str, Any]:
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="驳回原因必填")

    record = _get_offer_record_or_404(db, offer_record_id, RmsOfferRecord)
    if (record.status or "").strip() != "pending":
        raise HTTPException(status_code=400, detail="该 Offer 审批单不可驳回")

    step = _get_pending_step(db, offer_record_id, RmsOfferApprovalStep)
    if not step:
        raise HTTPException(status_code=400, detail="无待审批节点")
    _assert_pending_step_consistency(db, record, step, RmsOfferApprovalStep=RmsOfferApprovalStep)
    _assert_step_approver(ctx, step)

    now = utc_date_str()
    step.status = "rejected"
    step.comment = reason
    step.acted_at = now
    record.status = "rejected"
    record.current_approval_node = ""
    record.reason = reason
    record.updated_at = now

    app = db.query(RmsApplication).filter(RmsApplication.id == record.application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="推荐记录不存在")
    raw_from = (app.status or "").strip()
    app.status = "pending_offer"
    app.current_stage = "pending_offer"
    app.last_activity_at = now
    app.updated_at = now
    _write_status_history(
        db,
        RmsApplicationStatusHistory,
        application_id=int(app.id),
        from_status=raw_from,
        to_status="pending_offer",
        reason="offer_approval_rejected",
        note=reason,
        changed_by=ctx.user_id,
    )

    applicant_username = _username_for_user_id(db, record.created_by)
    _add_notification(
        db,
        CrmNotification,
        username=applicant_username,
        ntype="rms_offer_rejected",
        message=f"Offer 审批已驳回：{reason}",
        client_id=int(record.client_id) if record.client_id else None,
        application_id=int(record.application_id),
        offer_record_id=int(record.id),
        link_url=_offer_link(int(record.id)),
    )

    db.commit()
    db.refresh(record)
    return offer_record_to_dict(db, record, RmsOfferApprovalStep=RmsOfferApprovalStep)


def drop_offer(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    reason: str,
    *,
    RmsApplication: Type[Any],
    RmsApplicationStatusHistory: Type[Any],
    RmsCandidate: Type[Any],
    RmsJob: Type[Any],
    RmsOfferRecord: Type[Any],
    Client: Type[Any],
) -> Dict[str, Any]:
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="弃offer原因必填")

    app, candidate, job, client = _load_application_bundle(
        db,
        ctx,
        application_id,
        scope_action="write",
        RmsApplication=RmsApplication,
        RmsCandidate=RmsCandidate,
        RmsJob=RmsJob,
        Client=Client,
    )
    if (app.status or "").strip() != "pending_offer":
        raise HTTPException(status_code=400, detail="仅待offer推荐记录可弃offer")

    now = utc_date_str()
    raw_from = (app.status or "").strip()
    app.status = "offer_dropped"
    app.current_stage = "offer_dropped"
    app.last_activity_at = now
    app.updated_at = now
    _write_status_history(
        db,
        RmsApplicationStatusHistory,
        application_id=application_id,
        from_status=raw_from,
        to_status="offer_dropped",
        reason="offer_dropped",
        note=reason,
        changed_by=ctx.user_id,
    )

    record = RmsOfferRecord(
        application_id=application_id,
        candidate_id=int(candidate.id),
        job_id=int(job.id),
        client_id=int(client.id),
        status="offer_dropped",
        current_approval_node="",
        reason=reason,
        created_by=ctx.user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"application": app_svc.application_to_dict(app), "offer_record_id": record.id}


def mark_transit_lost(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    reason: str,
    *,
    RmsApplication: Type[Any],
    RmsApplicationStatusHistory: Type[Any],
    RmsCandidate: Type[Any],
    RmsJob: Type[Any],
    RmsOfferRecord: Type[Any],
    Client: Type[Any],
) -> Dict[str, Any]:
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="在途流失原因必填")

    app, candidate, job, client = _load_application_bundle(
        db,
        ctx,
        application_id,
        scope_action="write",
        RmsApplication=RmsApplication,
        RmsCandidate=RmsCandidate,
        RmsJob=RmsJob,
        Client=Client,
    )
    if (app.status or "").strip() != "onboarding":
        raise HTTPException(status_code=400, detail="仅在途推荐记录可标记在途流失")

    now = utc_date_str()
    raw_from = (app.status or "").strip()
    app.status = "onboarding_lost"
    app.current_stage = "onboarding_lost"
    app.last_activity_at = now
    app.updated_at = now
    _write_status_history(
        db,
        RmsApplicationStatusHistory,
        application_id=application_id,
        from_status=raw_from,
        to_status="onboarding_lost",
        reason="onboarding_lost",
        note=reason,
        changed_by=ctx.user_id,
    )

    approved = (
        db.query(RmsOfferRecord)
        .filter(
            RmsOfferRecord.application_id == application_id,
            RmsOfferRecord.status == "approved",
        )
        .order_by(RmsOfferRecord.id.desc())
        .first()
    )
    record = approved or RmsOfferRecord(
        application_id=application_id,
        candidate_id=int(candidate.id),
        job_id=int(job.id),
        client_id=int(client.id),
        created_by=ctx.user_id,
        created_at=now,
    )
    record.status = "onboarding_lost"
    record.reason = reason
    record.updated_at = now
    if record.id is None:
        db.add(record)
    db.commit()
    if record.id is not None:
        db.refresh(record)
    return {"application": app_svc.application_to_dict(app), "offer_record_id": getattr(record, "id", None)}


def _format_amount_display(amount: Any) -> str:
    raw = str(amount or "").strip().replace(",", "")
    if not raw:
        return ""
    try:
        n = float(raw)
    except ValueError:
        return str(amount or "").strip()
    if abs(n - round(n)) < 1e-9:
        return f"{int(round(n)):,}"
    text = f"{n:,.2f}".rstrip("0").rstrip(".")
    return text


def _format_quote_tax_display(amount: Any, unit: Any) -> str:
    amt = _format_amount_display(amount)
    u = str(unit or "").strip()
    if not amt:
        return ""
    return f"{amt} ({u})" if u else amt


def _prior_approval_comments(
    db: Session,
    offer_record_id: int,
    *,
    RmsOfferApprovalStep: Type[Any],
) -> List[Dict[str, str]]:
    """Approved steps before the current pending node (for 二/三级审批弹窗展示)."""
    steps = (
        db.query(RmsOfferApprovalStep)
        .filter(
            RmsOfferApprovalStep.offer_record_id == int(offer_record_id),
            RmsOfferApprovalStep.status == "approved",
        )
        .order_by(RmsOfferApprovalStep.step_order.asc())
        .all()
    )
    out: List[Dict[str, str]] = []
    for step in steps:
        out.append(
            {
                "step_type": (step.step_type or "").strip(),
                "step_label": approval_step_short_label(step.step_type),
                "approver_label": _display_name_for_user_id(db, step.approver_user_id),
                "comment": (step.comment or "").strip(),
                "acted_at": normalize_rms_date(getattr(step, "acted_at", None) or ""),
            }
        )
    return out


def offer_record_to_dict(
    db: Session,
    record: Any,
    *,
    RmsOfferApprovalStep: Type[Any],
) -> Dict[str, Any]:
    pending_step = _get_pending_step(db, int(record.id), RmsOfferApprovalStep)
    node = (record.current_approval_node or "").strip()
    quote_attachment_path = _offer_quote_attachment_path(record)
    submission_remark = _submission_remark(record)
    created_at = normalize_rms_date(getattr(record, "created_at", None) or "") or (
        str(getattr(record, "created_at", None) or "").strip()[:10]
    )
    quote_tax_unit = record.quote_tax_unit or ""
    raw_amount = str(getattr(record, "quote_amount_tax", None) or "").strip()
    if not raw_amount:
        raw_amount = str(record.monthly_quote_tax or "").strip()
    days = str(getattr(record, "monthly_billable_days", None) or "20.67")
    hours = str(getattr(record, "daily_billable_hours", None) or "8")
    converted_monthly = compute_monthly_quote_tax(
        raw_amount,
        quote_tax_unit,
        days,
        hours,
    )
    return {
        "id": record.id,
        "application_id": record.application_id,
        "candidate_id": record.candidate_id,
        "job_id": record.job_id,
        "client_id": record.client_id,
        "status": record.status,
        "status_label": _offer_status_label(record.status),
        "current_approval_node": node,
        "current_approval_node_label": approval_node_label(node) if node else "",
        "gm_pct": record.gm_pct or "",
        "gm_amount": record.gm_amount or "",
        "quote_amount_tax": raw_amount,
        "monthly_quote_tax": converted_monthly,
        "quote_tax_unit": quote_tax_unit,
        "monthly_billable_days": days,
        "daily_billable_hours": hours,
        "converted_monthly_quote_tax": converted_monthly,
        "quote_tax_display": _format_quote_tax_display(raw_amount, quote_tax_unit),
        "pre_tax_salary": record.pre_tax_salary or "",
        "probation_days": record.probation_days or "",
        "probation_discount_months": record.probation_discount_months or "",
        "planned_onboard_date": record.planned_onboard_date or "",
        "quote_confirm_attachment": quote_attachment_path,
        "quote_confirm_attachment_url": (
            f"/api/rms/offers/{int(record.id)}/quote-attachment" if quote_attachment_path else ""
        ),
        "reason": record.reason or "",
        "submission_remark": submission_remark,
        "submission_submitted_at": created_at,
        "created_by": record.created_by,
        "created_at": record.created_at or "",
        "updated_at": record.updated_at or "",
        "pending_step_id": pending_step.id if pending_step else None,
        "pending_approver_user_id": pending_step.approver_user_id if pending_step else None,
        "pending_approver_label": _user_label_for_user_id(
            db, pending_step.approver_user_id if pending_step else None
        ),
        "prior_approval_comments": _prior_approval_comments(
            db,
            int(record.id),
            RmsOfferApprovalStep=RmsOfferApprovalStep,
        ),
    }


def offer_planned_onboard_by_application_ids(
    db: Session,
    application_ids: List[int],
    *,
    RmsOfferRecord: Type[Any],
) -> Dict[int, str]:
    """Latest pending/approved offer record's planned onboard date per application."""
    ids = sorted({int(i) for i in application_ids if i is not None})
    if not ids:
        return {}

    records = (
        db.query(RmsOfferRecord)
        .filter(
            RmsOfferRecord.application_id.in_(ids),
            RmsOfferRecord.status.in_(("pending", "approved")),
        )
        .order_by(RmsOfferRecord.id.desc())
        .all()
    )
    out: Dict[int, str] = {}
    for record in records:
        app_id = int(record.application_id)
        if app_id in out:
            continue
        raw = str(getattr(record, "planned_onboard_date", None) or "").strip()
        if raw:
            out[app_id] = raw
    return out


def pending_approval_info_by_application_ids(
    db: Session,
    application_ids: List[int],
    *,
    RmsOfferRecord: Type[Any],
    RmsOfferApprovalStep: Type[Any],
) -> Dict[int, Dict[str, str]]:
    ids = sorted({int(i) for i in application_ids if i is not None})
    if not ids:
        return {}

    records = (
        db.query(RmsOfferRecord)
        .filter(
            RmsOfferRecord.application_id.in_(ids),
            RmsOfferRecord.status == "pending",
        )
        .order_by(RmsOfferRecord.id.desc())
        .all()
    )
    latest_by_app: Dict[int, Any] = {}
    for record in records:
        app_id = int(record.application_id)
        if app_id not in latest_by_app:
            latest_by_app[app_id] = record

    out: Dict[int, Dict[str, str]] = {}
    for app_id, record in latest_by_app.items():
        pending_step = _get_pending_step(db, int(record.id), RmsOfferApprovalStep)
        node = (record.current_approval_node or "").strip()
        out[app_id] = {
            "offer_current_approval_node_label": approval_node_label(node) if node else "",
            "offer_pending_approver_label": _user_label_for_user_id(
                db, pending_step.approver_user_id if pending_step else None
            ),
        }
    return out


def _offer_status_label(status: str) -> str:
    labels = {
        "pending": "审批中",
        "approved": "已通过",
        "offer_dropped": "弃offer",
        "onboarding_lost": "在途流失",
        "rejected": "已驳回",
        "superseded": "已作废",
    }
    return labels.get((status or "").strip(), status or "")


def _pending_approver_offer_record_ids(
    db: Session,
    ctx: AuthContext,
    offer_record_ids: List[int],
    *,
    RmsOfferApprovalStep: Type[Any],
) -> Set[int]:
    if ctx.user_id is None or not offer_record_ids:
        return set()
    rows = (
        db.query(RmsOfferApprovalStep.offer_record_id)
        .filter(
            RmsOfferApprovalStep.offer_record_id.in_(offer_record_ids),
            RmsOfferApprovalStep.status == "pending",
            RmsOfferApprovalStep.approver_user_id == int(ctx.user_id),
        )
        .all()
    )
    return {int(r[0]) for r in rows}


def list_offer_records(
    db: Session,
    ctx: AuthContext,
    *,
    status: Optional[str] = None,
    RmsOfferRecord: Type[Any],
    RmsOfferApprovalStep: Type[Any],
    RmsApplication: Type[Any],
    RmsCandidate: Type[Any],
    RmsJob: Type[Any],
    Client: Type[Any],
) -> List[Dict[str, Any]]:
    q = db.query(RmsOfferRecord).filter(RmsOfferRecord.status.in_(OFFER_RECORD_TAB_STATUSES))
    if status:
        st = status.strip()
        if st and st in OFFER_RECORD_TAB_STATUSES:
            q = q.filter(RmsOfferRecord.status == st)

    rows = q.order_by(RmsOfferRecord.id.desc()).limit(500).all()
    if not rows:
        return []

    app_ids = {int(r.application_id) for r in rows}
    scoped = rms_ds.scoped_applications_query(db, ctx, RmsApplication, Client, action="read")
    allowed_app_ids = {
        int(a.id)
        for a in scoped.filter(RmsApplication.id.in_(app_ids)).all()
    }
    client_ids = {int(r.client_id) for r in rows if r.client_id is not None}
    clients_by_id: Dict[int, Any] = {}
    if client_ids:
        clients_by_id = {
            int(c.id): c for c in db.query(Client).filter(Client.id.in_(client_ids)).all()
        }
    approver_offer_ids = _pending_approver_offer_record_ids(
        db,
        ctx,
        [int(r.id) for r in rows],
        RmsOfferApprovalStep=RmsOfferApprovalStep,
    )

    out: List[Dict[str, Any]] = []
    for record in rows:
        record_id = int(record.id)
        client = clients_by_id.get(int(record.client_id)) if record.client_id is not None else None
        if not _can_view_offer_record(
            ctx,
            record,
            allowed_app_ids=allowed_app_ids,
            approver_offer_ids=approver_offer_ids,
            db=db,
            client=client,
        ):
            continue
        item = offer_record_to_dict(db, record, RmsOfferApprovalStep=RmsOfferApprovalStep)
        item["can_approve"] = _can_approve_offer_record(
            ctx,
            record,
            approver_offer_ids=approver_offer_ids,
        )
        item["can_view_detail"] = _can_view_offer_detail_row(
            ctx,
            record,
            approver_offer_ids=approver_offer_ids,
            db=db,
            client=client,
            can_approve=bool(item["can_approve"]),
        )
        app = db.query(RmsApplication).filter(RmsApplication.id == record.application_id).first()
        candidate = (
            db.query(RmsCandidate).filter(RmsCandidate.id == record.candidate_id).first()
            if record.candidate_id
            else None
        )
        job = db.query(RmsJob).filter(RmsJob.id == record.job_id).first() if record.job_id else None
        if client is None and record.client_id is not None:
            client = db.query(Client).filter(Client.id == record.client_id).first()
        item["candidate_name"] = (candidate.name or "").strip() if candidate else ""
        item["job_title"] = (job.title or "").strip() if job else ""
        item["client_name"] = (client.name or "").strip() if client else ""
        item["recommended_by"] = app.recommended_by if app else None
        item["recommended_by_label"] = _display_name_for_user_id(db, app.recommended_by if app else None)
        item["created_by_label"] = _display_name_for_user_id(db, record.created_by)
        out.append(item)
    return out
