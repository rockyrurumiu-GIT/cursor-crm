"""Handoff API routes — registered from main.py."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from fastapi import Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from auth import data_scope as ds
from auth.data_scope_catalog import RESOURCE_DELIVERY_HANDOFF
from auth.deps import get_current_context, require_permission
from auth import service as auth_service
from auth.service import AuthContext
from handoff_core import (
    HANDOFF_REJECT_CODES,
    HANDOFF_STATUSES,
    HANDOFF_STATUS_LABELS,
    ai_parse_schema_hint,
    compute_completeness,
    empty_requirement,
    generate_brief_markdown,
    is_delivery_reviewer,
    load_delivery_reviewers,
    load_requirement_spec,
    merge_ai_into_requirement,
    parse_requirement_json,
    validate_for_submit,
)
from llm_service import get_llm_service


class HandoffUpdateBody(BaseModel):
    title: Optional[str] = None
    delivery_owner: Optional[str] = None
    source_text: Optional[str] = None
    requirement: Optional[Dict[str, Any]] = None


class HandoffRejectBody(BaseModel):
    code: str
    detail: str = Field(..., min_length=1)


class HandoffAiParseBody(BaseModel):
    text: Optional[str] = None


def _handoff_to_dict(h, client_name: str = "") -> Dict[str, Any]:
    req = parse_requirement_json(h.requirement_json)
    comp = compute_completeness(req)
    try:
        gaps = json.loads(h.ai_gap_flags or "[]")
    except json.JSONDecodeError:
        gaps = []
    return {
        "id": h.id,
        "client_id": h.client_id,
        "client_name": client_name,
        "version": h.version,
        "title": h.title or "",
        "status": h.status,
        "status_label": HANDOFF_STATUS_LABELS.get(h.status, h.status),
        "sales_owner": h.sales_owner or "",
        "delivery_owner": h.delivery_owner or "",
        "delivery_owner_user_id": getattr(h, "delivery_owner_user_id", None),
        "source_text": h.source_text or "",
        "requirement": req,
        "completeness": comp,
        "ai_parsed_json": h.ai_parsed_json or "",
        "ai_brief_md": h.ai_brief_md or "",
        "ai_gap_flags": gaps,
        "ai_status": h.ai_status or "",
        "reject_reason_code": h.reject_reason_code or "",
        "reject_reason_label": HANDOFF_REJECT_CODES.get(h.reject_reason_code, ""),
        "reject_detail": h.reject_detail or "",
        "reviewer": h.reviewer or "",
        "reviewed_at": h.reviewed_at.isoformat() if h.reviewed_at else "",
        "submitted_at": h.submitted_at.isoformat() if h.submitted_at else "",
        "created_at": h.created_at.isoformat() if h.created_at else "",
        "updated_at": h.updated_at.isoformat() if h.updated_at else "",
    }


def _username_for_user_id(db: Session, user_id: Optional[int]) -> str:
    if not user_id:
        return ""
    row = db.execute(
        text("SELECT username FROM sys_user WHERE id = :id AND status = 'active'"),
        {"id": user_id},
    ).fetchone()
    return str(row[0]).strip() if row and row[0] else ""


def register_handoff_routes(
    app,
    *,
    get_db: Callable,
    authenticate: Callable,
    authenticate_admin: Callable,
    effective_admin_username: Callable,
    page_renderer: Callable,
    Client,
    HandoffRequest,
    HandoffReviewLog,
    CrmNotification,
    VisitRecord,
    DeliveryPipelineInsightDemand,
    Contract=None,
    ContractMilestone=None,
    review_dep: Optional[Callable] = None,
):
    if review_dep is not None:

        def _require_reviewer(user: str = Depends(review_dep)):
            return user
    else:

        def _require_reviewer(user: str = Depends(authenticate)):
            if not is_delivery_reviewer(user, effective_admin_username()):
                raise HTTPException(status_code=403, detail="需要交付负责人权限")
            return user

    def _get_handoff_or_404(db: Session, handoff_id: int) -> HandoffRequest:
        h = db.query(HandoffRequest).filter(HandoffRequest.id == handoff_id).first()
        if not h:
            raise HTTPException(status_code=404, detail="交接单不存在")
        return h

    def _get_client_or_404(db: Session, client_id: int, ctx: Optional[AuthContext] = None):
        if ctx is not None:
            ds.assert_client_in_scope(db, ctx, client_id, Client, RESOURCE_DELIVERY_HANDOFF, "read")
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        return c

    def _notify(db: Session, username: str, ntype: str, message: str, handoff_id: int, client_id: int):
        db.add(
            CrmNotification(
                username=username,
                ntype=ntype,
                handoff_id=handoff_id,
                client_id=client_id,
                message=message,
            )
        )

    def _log_review(db: Session, handoff_id: int, client_id: int, operator: str, action: str, detail: str = ""):
        db.add(
            HandoffReviewLog(
                handoff_id=handoff_id,
                client_id=client_id,
                operator=operator,
                action=action,
                detail=detail,
            )
        )

    def _latest_handoff_for_client(db: Session, client_id: int) -> Optional[HandoffRequest]:
        return (
            db.query(HandoffRequest)
            .filter(HandoffRequest.client_id == client_id, HandoffRequest.status != "superseded")
            .order_by(desc(HandoffRequest.version), desc(HandoffRequest.id))
            .first()
        )

    def _pending_handoffs_for_user(db: Session, ctx: AuthContext) -> List[Dict[str, Any]]:
        """待审交接：在数据范围过滤基础上，审核人可见未指派项。"""
        user = ctx.username
        admin = effective_admin_username()
        is_rev = is_delivery_reviewer(user, admin)
        q = (
            db.query(HandoffRequest)
            .filter(HandoffRequest.status == "pending_review")
            .order_by(desc(HandoffRequest.submitted_at))
        )
        if not ctx.is_super and user != admin:
            q = ds.filter_query_by_client_scope(
                q, db, ctx, RESOURCE_DELIVERY_HANDOFF, "read", HandoffRequest.client_id, Client
            )
        rows = q.all()
        out: List[Dict[str, Any]] = []
        for h in rows:
            owner = (h.delivery_owner or "").strip()
            if ctx.is_super or user == admin:
                pass
            elif owner == user or (getattr(h, "delivery_owner_user_id", None) == ctx.user_id):
                pass
            elif is_rev:
                if owner and owner != user:
                    continue
            else:
                continue
            client = db.query(Client).filter(Client.id == h.client_id).first()
            out.append(_handoff_to_dict(h, client.name if client else ""))
        return out

    def _client_gate_status(db: Session, client_id: int) -> Dict[str, Any]:
        latest = _latest_handoff_for_client(db, client_id)
        if not latest:
            return {
                "approved": False,
                "status": "none",
                "status_label": "未提交",
                "message": "该客户尚未提交销售-交付交接单，建议先完成需求审批再开展交付准备。",
            }
        approved = latest.status == "approved"
        return {
            "approved": approved,
            "status": latest.status,
            "status_label": HANDOFF_STATUS_LABELS.get(latest.status, latest.status),
            "handoff_id": latest.id,
            "message": (
                "交接已通过，可开展交付准备。"
                if approved
                else f"交接状态：{HANDOFF_STATUS_LABELS.get(latest.status, latest.status)}。"
            ),
        }

    @app.get("/api/handoff/config")
    async def handoff_config(
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("delivery.handoff.read")),
    ):
        can_review = is_delivery_reviewer(user, effective_admin_username()) or auth_service.user_has_permission(
            ctx, "delivery.handoff.review"
        )
        return {
            "reject_codes": [{"code": k, "label": v} for k, v in HANDOFF_REJECT_CODES.items()],
            "statuses": [{"code": s, "label": HANDOFF_STATUS_LABELS.get(s, s)} for s in sorted(HANDOFF_STATUSES)],
            "spec": load_requirement_spec(),
            "json_schema_path": "/data/requirement_schema.json",
            "reviewers": load_delivery_reviewers(effective_admin_username()),
            "llm_available": get_llm_service().available,
            "is_reviewer": can_review,
        }

    @app.get("/api/clients/{client_id}/handoff-gate")
    async def client_handoff_gate(
        client_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handoff.read")),
    ):
        _get_client_or_404(db, client_id)
        return _client_gate_status(db, client_id)

    @app.get("/api/clients/{client_id}/handoffs")
    async def list_client_handoffs(
        client_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handoff.read")),
    ):
        client = _get_client_or_404(db, client_id)
        rows = (
            db.query(HandoffRequest)
            .filter(HandoffRequest.client_id == client_id)
            .order_by(desc(HandoffRequest.version), desc(HandoffRequest.id))
            .all()
        )
        return [_handoff_to_dict(h, client.name) for h in rows]

    @app.post("/api/clients/{client_id}/handoffs")
    async def create_handoff(
        client_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handoff.write")),
    ):
        client = _get_client_or_404(db, client_id)
        latest = (
            db.query(HandoffRequest)
            .filter(HandoffRequest.client_id == client_id)
            .order_by(desc(HandoffRequest.version))
            .first()
        )
        version = (latest.version + 1) if latest else 1
        if latest and latest.status in ("draft", "pending_review"):
            raise HTTPException(status_code=400, detail="存在未完成的交接单，请先提交或等待审批")
        if latest and latest.status == "approved":
            version = latest.version + 1
        delivery_owner_user_id = getattr(client, "delivery_owner_user_id", None)
        delivery_owner = _username_for_user_id(db, delivery_owner_user_id)
        if not delivery_owner:
            reviewers = load_delivery_reviewers(effective_admin_username())
            delivery_owner = reviewers[0] if reviewers else user
            delivery_owner_user_id = None
        h = HandoffRequest(
            client_id=client_id,
            version=version,
            title=f"{client.name} 交接 v{version}",
            status="draft",
            sales_owner=client.owner or user,
            delivery_owner=delivery_owner,
            delivery_owner_user_id=delivery_owner_user_id,
            requirement_json=json.dumps(empty_requirement(), ensure_ascii=False),
        )
        if latest and latest.status in ("rejected", "approved"):
            latest.status = "superseded"
        db.add(h)
        db.flush()
        _log_review(db, h.id, client_id, user, "create", f"创建交接单 v{version}")
        db.commit()
        db.refresh(h)
        return _handoff_to_dict(h, client.name)

    @app.get("/api/handoffs/pending")
    async def pending_handoffs(
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(_require_reviewer),
    ):
        return _pending_handoffs_for_user(db, ctx)

    @app.get("/api/delivery/handoffs/pending")
    async def delivery_pending_handoffs(
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("delivery.handoff.read")),
    ):
        return _pending_handoffs_for_user(db, ctx)

    @app.get("/api/handoffs/{handoff_id}")
    async def get_handoff(
        handoff_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handoff.read")),
    ):
        h = _get_handoff_or_404(db, handoff_id)
        client = db.query(Client).filter(Client.id == h.client_id).first()
        data = _handoff_to_dict(h, client.name if client else "")
        logs = (
            db.query(HandoffReviewLog)
            .filter(HandoffReviewLog.handoff_id == handoff_id)
            .order_by(desc(HandoffReviewLog.created_at))
            .all()
        )
        data["logs"] = [
            {
                "id": lg.id,
                "operator": lg.operator,
                "action": lg.action,
                "detail": lg.detail,
                "created_at": lg.created_at.isoformat() if lg.created_at else "",
            }
            for lg in logs
        ]
        if client:
            visits = (
                db.query(VisitRecord)
                .filter(VisitRecord.client_id == client.id)
                .order_by(desc(VisitRecord.id))
                .limit(8)
                .all()
            )
            data["recent_visits"] = [
                {"date": v.date, "location": v.location, "content": (v.content or "")[:500]} for v in visits
            ]
        return data

    @app.put("/api/handoffs/{handoff_id}")
    async def update_handoff(
        handoff_id: int,
        body: HandoffUpdateBody,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handoff.write")),
    ):
        h = _get_handoff_or_404(db, handoff_id)
        if h.status not in ("draft", "rejected"):
            raise HTTPException(status_code=400, detail="当前状态不可编辑")
        if body.title is not None:
            h.title = body.title.strip()
        if body.delivery_owner is not None:
            h.delivery_owner = body.delivery_owner.strip()
        if body.source_text is not None:
            h.source_text = body.source_text
        if body.requirement is not None:
            h.requirement_json = json.dumps(body.requirement, ensure_ascii=False)
        h.updated_at = datetime.now()
        _log_review(db, h.id, h.client_id, user, "save", "保存草稿")
        db.commit()
        client = db.query(Client).filter(Client.id == h.client_id).first()
        return _handoff_to_dict(h, client.name if client else "")

    @app.post("/api/handoffs/{handoff_id}/submit")
    async def submit_handoff(
        handoff_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handoff.write")),
    ):
        h = _get_handoff_or_404(db, handoff_id)
        if h.status not in ("draft", "rejected"):
            raise HTTPException(status_code=400, detail="当前状态不可提交")
        req = parse_requirement_json(h.requirement_json)
        ok, errors = validate_for_submit(req)
        if not ok:
            raise HTTPException(status_code=400, detail="; ".join(errors))
        h.status = "pending_review"
        h.submitted_at = datetime.now()
        h.updated_at = datetime.now()
        h.reject_reason_code = ""
        h.reject_detail = ""
        client = db.query(Client).filter(Client.id == h.client_id).first()
        _log_review(db, h.id, h.client_id, user, "submit", "提交审批")
        target = h.delivery_owner or effective_admin_username()
        _notify(db, target, "handoff_pending", f"【待审】{client.name if client else ''}：{h.title}", h.id, h.client_id)
        db.commit()
        return _handoff_to_dict(h, client.name if client else "")

    @app.post("/api/handoffs/{handoff_id}/approve")
    async def approve_handoff(handoff_id: int, db: Session = Depends(get_db), user: str = Depends(_require_reviewer)):
        h = _get_handoff_or_404(db, handoff_id)
        if h.status != "pending_review":
            raise HTTPException(status_code=400, detail="仅待审状态可通过")
        client = db.query(Client).filter(Client.id == h.client_id).first()
        req = parse_requirement_json(h.requirement_json)
        brief = generate_brief_markdown(client.name if client else "", h.title, req, h.sales_owner)
        h.status = "approved"
        h.reviewer = user
        h.reviewed_at = datetime.now()
        h.updated_at = datetime.now()
        h.ai_brief_md = brief
        _log_review(db, h.id, h.client_id, user, "approve", "审批通过")
        if Contract and ContractMilestone and client:
            from phase2_routes import create_contract_from_handoff

            create_contract_from_handoff(db, h, client, Contract=Contract, ContractMilestone=ContractMilestone)
            _log_review(db, h.id, h.client_id, user, "contract_draft", "生成合同草稿与里程碑")
        _notify(
            db,
            h.sales_owner or user,
            "handoff_approved",
            f"【已通过】{client.name if client else ''}：{h.title}",
            h.id,
            h.client_id,
        )
        db.commit()
        return _handoff_to_dict(h, client.name if client else "")

    @app.post("/api/handoffs/{handoff_id}/reject")
    async def reject_handoff(
        handoff_id: int,
        body: HandoffRejectBody,
        db: Session = Depends(get_db),
        user: str = Depends(_require_reviewer),
    ):
        h = _get_handoff_or_404(db, handoff_id)
        if h.status != "pending_review":
            raise HTTPException(status_code=400, detail="仅待审状态可驳回")
        if body.code not in HANDOFF_REJECT_CODES:
            raise HTTPException(status_code=400, detail="无效的驳回原因码")
        client = db.query(Client).filter(Client.id == h.client_id).first()
        h.status = "rejected"
        h.reviewer = user
        h.reviewed_at = datetime.now()
        h.updated_at = datetime.now()
        h.reject_reason_code = body.code
        h.reject_detail = body.detail.strip()
        label = HANDOFF_REJECT_CODES[body.code]
        _log_review(db, h.id, h.client_id, user, "reject", f"{label}：{body.detail.strip()}")
        _notify(
            db,
            h.sales_owner or user,
            "handoff_rejected",
            f"【已驳回】{client.name if client else ''}：{label}",
            h.id,
            h.client_id,
        )
        db.commit()
        return _handoff_to_dict(h, client.name if client else "")

    @app.post("/api/handoffs/{handoff_id}/ai/parse")
    async def ai_parse_handoff(
        handoff_id: int,
        body: HandoffAiParseBody = Body(default={}),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handoff.write")),
    ):
        h = _get_handoff_or_404(db, handoff_id)
        if h.status not in ("draft", "rejected"):
            raise HTTPException(status_code=400, detail="当前状态不可 AI 解析")
        text = (body.text if body.text is not None else h.source_text) or ""
        if not text.strip():
            raise HTTPException(status_code=400, detail="请先粘贴会议纪要或聊天记录")
        llm = get_llm_service()
        result = llm.extract_structured(text, ai_parse_schema_hint())
        if not result.get("ok"):
            h.ai_status = "failed"
            db.commit()
            return {"ok": False, "error": result.get("error"), "suggestion": result.get("data", {})}
        data = result.get("data") or {}
        h.ai_parsed_json = json.dumps(data, ensure_ascii=False)
        h.ai_status = "parsed"
        merged = merge_ai_into_requirement(parse_requirement_json(h.requirement_json), data)
        h.requirement_json = json.dumps(merged, ensure_ascii=False)
        _log_review(db, h.id, h.client_id, user, "ai_parse", "AI 解析原文并填充表单")
        db.commit()
        client = db.query(Client).filter(Client.id == h.client_id).first()
        return {"ok": True, "handoff": _handoff_to_dict(h, client.name if client else ""), "parsed": data}

    @app.post("/api/handoffs/{handoff_id}/ai/review-assist")
    async def ai_review_assist(handoff_id: int, db: Session = Depends(get_db), user: str = Depends(_require_reviewer)):
        h = _get_handoff_or_404(db, handoff_id)
        client = db.query(Client).filter(Client.id == h.client_id).first()
        req = parse_requirement_json(h.requirement_json)
        visits = (
            db.query(VisitRecord)
            .filter(VisitRecord.client_id == h.client_id)
            .order_by(desc(VisitRecord.id))
            .limit(6)
            .all()
        )
        visit_text = "\n".join(f"- {v.date} {v.location}: {(v.content or '')[:300]}" for v in visits)
        context = (
            f"客户：{client.name if client else ''}\n交接标题：{h.title}\n"
            f"结构化需求：{json.dumps(req, ensure_ascii=False)}\n最近拜访：\n{visit_text}"
        )
        llm = get_llm_service()
        brief_res = llm.summarize_brief(context)
        spec = load_requirement_spec()
        checklist = [spec.get("field_labels", {}).get(f, f) for f in (spec.get("required_fields") or [])]
        gaps: List[Any] = []
        brief_md = brief_res.get("markdown") or generate_brief_markdown(
            client.name if client else "", h.title, req, h.sales_owner
        )
        if brief_res.get("ok"):
            brief_md = brief_res["markdown"]
            gap_res = llm.diff_checklist(brief_md, checklist)
            if gap_res.get("ok"):
                gaps = gap_res.get("gaps") or []
        if not gaps:
            comp = compute_completeness(req)
            gaps = [{"field": m["field"], "severity": "high", "suggestion": f"缺少：{m['label']}"} for m in comp["missing"]]
        h.ai_brief_md = brief_md
        h.ai_gap_flags = json.dumps(gaps, ensure_ascii=False)
        h.ai_status = "review_assist"
        _log_review(db, h.id, h.client_id, user, "ai_review_assist", "生成交付审批辅助")
        db.commit()
        return {"ok": True, "brief_md": brief_md, "gaps": gaps, "llm_available": llm.available}

    @app.post("/api/handoffs/{handoff_id}/sync-pipeline-demand")
    async def sync_pipeline_demand(
        handoff_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handoff.write")),
    ):
        h = _get_handoff_or_404(db, handoff_id)
        if h.status != "approved":
            raise HTTPException(status_code=400, detail="仅已通过的交接单可同步")
        req = parse_requirement_json(h.requirement_json)
        positions = req.get("positions") or []
        period = datetime.now().strftime("%Y-%m")
        synced = 0
        for p in positions:
            pos = str(p.get("role") or "").strip()
            if not pos:
                continue
            qty = str(p.get("headcount") or "1")
            region = str((req.get("context") or {}).get("location") or "")
            existing = (
                db.query(DeliveryPipelineInsightDemand)
                .filter(
                    DeliveryPipelineInsightDemand.client_id == h.client_id,
                    DeliveryPipelineInsightDemand.period == period,
                    DeliveryPipelineInsightDemand.position == pos,
                    DeliveryPipelineInsightDemand.region == region,
                )
                .first()
            )
            if existing:
                existing.demand_qty = qty
            else:
                db.add(
                    DeliveryPipelineInsightDemand(
                        client_id=h.client_id,
                        period=period,
                        position=pos,
                        region=region,
                        demand_qty=qty,
                    )
                )
            synced += 1
        _log_review(db, h.id, h.client_id, user, "sync_pipeline", f"同步 {synced} 条需求到管道洞察")
        db.commit()
        return {"ok": True, "synced": synced}

    @app.get("/api/notifications")
    async def list_notifications(
        unread: Optional[int] = None,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handoff.read")),
    ):
        q = db.query(CrmNotification).filter(CrmNotification.username == user)
        if unread:
            q = q.filter(CrmNotification.read_at.is_(None))
        rows = q.order_by(desc(CrmNotification.created_at)).limit(50).all()
        return [
            {
                "id": n.id,
                "type": n.ntype,
                "message": n.message,
                "handoff_id": n.handoff_id,
                "client_id": n.client_id,
                "read_at": n.read_at.isoformat() if n.read_at else "",
                "created_at": n.created_at.isoformat() if n.created_at else "",
            }
            for n in rows
        ]

    @app.post("/api/notifications/{notification_id}/read")
    async def read_notification(
        notification_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handoff.read")),
    ):
        n = db.query(CrmNotification).filter(CrmNotification.id == notification_id, CrmNotification.username == user).first()
        if n and not n.read_at:
            n.read_at = datetime.now()
            db.commit()
        return {"ok": True}

    @app.get("/api/handoffs/{handoff_id}/export")
    async def export_handoff(
        handoff_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handoff.read")),
    ):
        h = _get_handoff_or_404(db, handoff_id)
        client = db.query(Client).filter(Client.id == h.client_id).first()
        data = _handoff_to_dict(h, client.name if client else "")
        logs = (
            db.query(HandoffReviewLog)
            .filter(HandoffReviewLog.handoff_id == handoff_id)
            .order_by(desc(HandoffReviewLog.created_at))
            .all()
        )
        data["audit_logs"] = [
            {
                "operator": lg.operator,
                "action": lg.action,
                "detail": lg.detail,
                "created_at": lg.created_at.isoformat() if lg.created_at else "",
            }
            for lg in logs
        ]
        return data

    @app.get("/customers/reviews", response_class=HTMLResponse)
    async def page_handoff_reviews(
        request: Request,
        _user: str = Depends(require_permission("delivery.handoff.review")),
    ):
        return page_renderer("pages/customer_reviews.html", request)

    @app.get("/delivery/handoff-pending", response_class=HTMLResponse)
    async def page_delivery_handoff_pending(request: Request):
        return page_renderer("pages/delivery_handoff_pending.html", request)

    @app.get("/customers/{client_id}/handoff", response_class=HTMLResponse)
    async def page_client_handoff(
        request: Request,
        client_id: int,
        _user: str = Depends(require_permission("delivery.handoff.read")),
    ):
        return page_renderer("pages/customer_handoff.html", request, client_id=client_id, handoff_id=None)

    @app.get("/customers/{client_id}/handoff/{handoff_id}", response_class=HTMLResponse)
    async def page_client_handoff_detail(
        request: Request,
        client_id: int,
        handoff_id: int,
        _user: str = Depends(require_permission("delivery.handoff.read")),
    ):
        return page_renderer(
            "pages/customer_handoff.html",
            request,
            client_id=client_id,
            handoff_id=handoff_id,
        )

    def extend_stats(stats_fn):
        """Wrap get_stats to add handoff counts."""

        async def wrapped(
            db: Session = Depends(get_db),
            user: str = Depends(require_permission("crm.clients.read")),
        ):
            base = await stats_fn(db=db, user=user)
            pending = db.query(HandoffRequest).filter(HandoffRequest.status == "pending_review").count()
            rejected = db.query(HandoffRequest).filter(HandoffRequest.status == "rejected").count()
            approved = db.query(HandoffRequest).filter(HandoffRequest.status == "approved").count()
            base["handoff"] = {"pending_review": pending, "rejected": rejected, "approved": approved}
            base["notifications_unread"] = (
                db.query(CrmNotification)
                .filter(CrmNotification.username == user, CrmNotification.read_at.is_(None))
                .count()
            )
            return base

        return wrapped

    return {"extend_stats": extend_stats, "client_gate_status": _client_gate_status}
