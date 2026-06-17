"""Phase 2 CRM routes: Opportunity, Contract, Contact."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from fastapi import Body, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from auth import data_scope as ds
from auth.data_scope_catalog import RESOURCE_CRM_CONTACT, RESOURCE_CRM_OPPORTUNITY
from auth.deps import get_current_context, require_permission
from auth.service import AuthContext
from handoff_core import generate_brief_markdown, parse_requirement_json
from phase2_core import (
    OPPORTUNITY_STAGE_LABELS,
    OPPORTUNITY_STAGES,
    CONTACT_ACQUISITION_CHANNELS,
    PRIMARY_CONTACT_TAG,
    build_contract_from_handoff,
    contact_remarks_from_relationship,
    contact_to_dict,
    contract_to_dict,
    find_client_primary_contact,
    milestone_to_dict,
    opportunity_to_dict,
    refresh_client_estimated_annual_amount,
    relationship_from_contact_remarks,
    suggest_milestones_from_requirement,
    sync_client_inline_from_contact,
)
from services.delivery_roster import decode_roster_upload_bytes

CONTACT_EXPORT_HEADERS = [
    "ID",
    "姓名",
    "客户",
    "职位",
    "城市",
    "创建人",
    "电话",
    "邮箱",
    "关系",
    "分组标签",
    "获客渠道",
    "联系人+1",
    "说明",
    "创建时间",
]

CONTACT_RELATIONSHIP_OPTIONS = frozenset({"普通", "良好", "密切"})
CONTACT_TAG_IMPORT_OPTIONS = frozenset({"首要", "次要", "一般"})


class OpportunityBody(BaseModel):
    client_id: int
    name: str
    amount: str = ""
    estimated_current_year_amount: str = ""
    probability: str = ""
    expected_close_date: str = ""
    stage: str = "initial"
    owner: str = ""
    contact_id: Optional[int] = None
    remarks: str = ""




class ContactBody(BaseModel):
    client_id: int
    name: str
    title: str = ""
    city: str = ""
    created_by: str = ""
    phone: str = ""
    email: str = ""
    tags: str = ""
    remarks: str = ""
    superior_contact: str = ""
    acquisition_channel: str = ""
    description: str = ""


def create_contract_from_handoff(
    db: Session,
    handoff,
    client,
    *,
    Contract,
    ContractMilestone,
) -> Any:
    existing = db.query(Contract).filter(Contract.handoff_id == handoff.id).first()
    if existing:
        return existing
    req = parse_requirement_json(handoff.requirement_json)
    brief = handoff.ai_brief_md or generate_brief_markdown(
        client.name, handoff.title, req, handoff.sales_owner
    )
    data = build_contract_from_handoff(
        client.id,
        handoff.id,
        client.name,
        handoff.title,
        req,
        brief,
        getattr(handoff, "opportunity_id", None),
    )
    contract = Contract(
        client_id=data["client_id"],
        handoff_id=data["handoff_id"],
        opportunity_id=data.get("opportunity_id"),
        contract_no=data["contract_no"],
        contract_type=data["contract_type"],
        title=data["title"],
        total_amount=data["total_amount"],
        start_date=data["start_date"],
        end_date=data["end_date"],
        status=data["status"],
        sow_markdown=data["sow_markdown"],
    )
    db.add(contract)
    db.flush()
    for m in suggest_milestones_from_requirement(req, contract.total_amount):
        db.add(
            ContractMilestone(
                contract_id=contract.id,
                name=m["name"],
                deliverable=m["deliverable"],
                invoice_pct=m.get("invoice_pct") or "",
                planned_date=m.get("planned_date") or "",
                amount=m.get("amount") or "",
                status="pending",
            )
        )
    return contract


def seed_settlement_from_milestone(
    db: Session,
    milestone,
    contract,
    client,
    DeliverySettlementEntry,
) -> int:
    if milestone.settlement_entry_id:
        return milestone.settlement_entry_id
    fee_month = (milestone.planned_date or "")[:7] or datetime.now().strftime("%Y-%m")
    entry = DeliverySettlementEntry(
        client_id=client.id,
        customer_name=client.name,
        fee_month=fee_month,
        amount=milestone.amount or contract.total_amount or "",
        po_no=contract.contract_no or "",
        invoiced="否",
        paid="否",
        internal_attendance_confirm="否",
        client_confirm="否",
        payment_cycle="月度",
        remarks=f"里程碑预置：{milestone.name}",
    )
    db.add(entry)
    db.flush()
    milestone.settlement_entry_id = entry.id
    return entry.id


def _resolve_opportunity_contact(db: Session, Contact, contact_id: Optional[int], client_id: int) -> Optional[Any]:
    if not contact_id:
        return None
    ct = db.query(Contact).filter(Contact.id == contact_id).first()
    if not ct:
        raise HTTPException(status_code=400, detail="联系人不存在")
    if ct.client_id != client_id:
        raise HTTPException(status_code=400, detail="联系人不属于所选客户")
    return ct


def _opportunity_contact_name(db: Session, Contact, contact_id: Optional[int]) -> str:
    if not contact_id:
        return ""
    ct = db.query(Contact).filter(Contact.id == contact_id).first()
    return (ct.name or "") if ct else ""


def _strip_excel_sep_directive(text: str) -> str:
    lines = text.splitlines()
    if len(lines) >= 2 and lines[0].strip().lower().startswith("sep="):
        return "\n".join(lines[1:])
    return text


def _contact_tags_export_label(tags: str) -> str:
    t = (tags or "").strip()
    if t in (PRIMARY_CONTACT_TAG, "首要"):
        return "首要"
    if t in ("次要", "一般"):
        return t
    return t


def _contact_tags_from_import(label: str) -> str:
    t = (label or "").strip()
    if t == "首要":
        return PRIMARY_CONTACT_TAG
    return t


def _contact_created_at_export(raw) -> str:
    if raw is None:
        return ""
    if hasattr(raw, "strftime"):
        return raw.strftime("%Y-%m-%d")
    s = str(raw).strip()
    if not s:
        return ""
    return s.replace("T", " ").replace("Z", "").split(".")[0][:10]


def register_phase2_routes(
    app,
    *,
    get_db: Callable,
    authenticate: Callable,
    page_renderer: Callable,
    Client,
    Contact,
    Opportunity,
    Contract,
    ContractMilestone,
    HandoffRequest,
    DeliverySettlementEntry,
    set_csv_download_headers: Callable,
    max_file_size: int,
):
    @app.get("/api/opportunities")
    async def list_opportunities(
        client_id: Optional[int] = None,
        stage: Optional[str] = None,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.opportunities.read")),
    ):
        q = db.query(Opportunity)
        if client_id:
            ds.assert_client_in_scope(db, ctx, client_id, Client, RESOURCE_CRM_OPPORTUNITY, "read")
            q = q.filter(Opportunity.client_id == client_id)
        q = ds.filter_query_by_client_scope(
            q, db, ctx, RESOURCE_CRM_OPPORTUNITY, "read", Opportunity.client_id, Client
        )
        if stage:
            q = q.filter(Opportunity.stage == stage)
        rows = q.order_by(desc(Opportunity.created_at)).all()
        out = []
        for o in rows:
            c = db.query(Client).filter(Client.id == o.client_id).first()
            contact_name = _opportunity_contact_name(db, Contact, getattr(o, "contact_id", None))
            out.append(opportunity_to_dict(o, c.name if c else "", contact_name))
        return out

    @app.post("/api/opportunities")
    async def create_opportunity(
        body: OpportunityBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.opportunities.write")),
    ):
        if body.stage not in OPPORTUNITY_STAGES:
            raise HTTPException(status_code=400, detail="无效商机阶段")
        ds.assert_client_in_scope(db, ctx, body.client_id, Client, RESOURCE_CRM_OPPORTUNITY, "write")
        client = db.query(Client).filter(Client.id == body.client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="客户不存在")
        _resolve_opportunity_contact(db, Contact, body.contact_id, body.client_id)
        o = Opportunity(
            client_id=body.client_id,
            name=body.name.strip(),
            amount=body.amount,
            estimated_current_year_amount=body.estimated_current_year_amount,
            probability=body.probability,
            expected_close_date=body.expected_close_date,
            stage=body.stage,
            owner=body.owner or client.owner or user,
            contact_id=body.contact_id,
            remarks=body.remarks,
        )
        db.add(o)
        db.commit()
        db.refresh(o)
        refresh_client_estimated_annual_amount(db, body.client_id, Client, Opportunity)
        db.commit()
        contact_name = _opportunity_contact_name(db, Contact, o.contact_id)
        return opportunity_to_dict(o, client.name, contact_name)

    @app.put("/api/opportunities/{opp_id}")
    async def update_opportunity(
        opp_id: int,
        body: OpportunityBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.opportunities.write")),
    ):
        o = db.query(Opportunity).filter(Opportunity.id == opp_id).first()
        if not o:
            raise HTTPException(status_code=404, detail="商机不存在")
        ds.assert_client_in_scope(db, ctx, o.client_id, Client, RESOURCE_CRM_OPPORTUNITY, "write")
        if body.stage not in OPPORTUNITY_STAGES:
            raise HTTPException(status_code=400, detail="无效商机阶段")
        if body.client_id != o.client_id:
            ds.assert_client_in_scope(db, ctx, body.client_id, Client, RESOURCE_CRM_OPPORTUNITY, "write")
        _resolve_opportunity_contact(db, Contact, body.contact_id, body.client_id)
        o.client_id = body.client_id
        o.name = body.name.strip()
        o.amount = body.amount
        o.estimated_current_year_amount = body.estimated_current_year_amount
        o.probability = body.probability
        o.expected_close_date = body.expected_close_date
        o.stage = body.stage
        o.owner = body.owner
        o.contact_id = body.contact_id
        o.remarks = body.remarks
        db.commit()
        refresh_client_estimated_annual_amount(db, o.client_id, Client, Opportunity)
        db.commit()
        client = db.query(Client).filter(Client.id == o.client_id).first()
        contact_name = _opportunity_contact_name(db, Contact, o.contact_id)
        return opportunity_to_dict(o, client.name if client else "", contact_name)

    @app.delete("/api/opportunities/{opp_id}")
    async def delete_opportunity(
        opp_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.opportunities.write")),
    ):
        o = db.query(Opportunity).filter(Opportunity.id == opp_id).first()
        if not o:
            raise HTTPException(status_code=404, detail="商机不存在")
        ds.assert_client_in_scope(db, ctx, o.client_id, Client, RESOURCE_CRM_OPPORTUNITY, "write")
        client_id = o.client_id
        db.delete(o)
        db.commit()
        refresh_client_estimated_annual_amount(db, client_id, Client, Opportunity)
        db.commit()
        return {"ok": True}

    @app.post("/api/opportunities/{opp_id}/create-handoff")
    async def opp_create_handoff(
        opp_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("crm.opportunities.write")),
    ):
        o = db.query(Opportunity).filter(Opportunity.id == opp_id).first()
        if not o:
            raise HTTPException(status_code=404, detail="商机不存在")
        if o.stage != "won":
            raise HTTPException(status_code=400, detail="仅赢单商机可发起交接")
        client = db.query(Client).filter(Client.id == o.client_id).first()
        latest = (
            db.query(HandoffRequest)
            .filter(HandoffRequest.client_id == o.client_id)
            .order_by(desc(HandoffRequest.version))
            .first()
        )
        if latest and latest.status in ("draft", "pending_review"):
            raise HTTPException(status_code=400, detail="存在未完成的交接单")
        version = (latest.version + 1) if latest else 1
        if latest and latest.status in ("rejected", "approved"):
            latest.status = "superseded"
        from handoff_core import empty_requirement, load_delivery_reviewers

        req = empty_requirement()
        req["commercial"]["estimated_amount"] = o.amount or ""
        h = HandoffRequest(
            client_id=o.client_id,
            opportunity_id=o.id,
            version=version,
            title=f"{o.name} 交接 v{version}",
            status="draft",
            sales_owner=o.owner or user,
            delivery_owner=(load_delivery_reviewers(user)[0] if load_delivery_reviewers(user) else user),
            requirement_json=json.dumps(req, ensure_ascii=False),
        )
        db.add(h)
        db.commit()
        db.refresh(h)
        return {"handoff_id": h.id, "url": f"/customers/{o.client_id}/handoff/{h.id}"}

    @app.get("/api/contracts")
    async def list_contracts(
        client_id: Optional[int] = None,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("crm.opportunities.read")),
    ):
        q = db.query(Contract)
        if client_id:
            q = q.filter(Contract.client_id == client_id)
        rows = q.order_by(desc(Contract.created_at)).all()
        out = []
        for c in rows:
            client = db.query(Client).filter(Client.id == c.client_id).first()
            ms = db.query(ContractMilestone).filter(ContractMilestone.contract_id == c.id).all()
            out.append(contract_to_dict(c, client.name if client else "", [milestone_to_dict(m) for m in ms]))
        return out

    @app.get("/api/contracts/{contract_id}")
    async def get_contract(
        contract_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("crm.opportunities.read")),
    ):
        c = db.query(Contract).filter(Contract.id == contract_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="合同不存在")
        client = db.query(Client).filter(Client.id == c.client_id).first()
        ms = db.query(ContractMilestone).filter(ContractMilestone.contract_id == c.id).all()
        return contract_to_dict(c, client.name if client else "", [milestone_to_dict(m) for m in ms])

    @app.post("/api/contracts/{contract_id}/milestones/{milestone_id}/seed-settlement")
    async def seed_milestone_settlement(
        contract_id: int,
        milestone_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("crm.opportunities.write")),
    ):
        c = db.query(Contract).filter(Contract.id == contract_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="合同不存在")
        m = db.query(ContractMilestone).filter(
            ContractMilestone.id == milestone_id, ContractMilestone.contract_id == contract_id
        ).first()
        if not m:
            raise HTTPException(status_code=404, detail="里程碑不存在")
        client = db.query(Client).filter(Client.id == c.client_id).first()
        entry_id = seed_settlement_from_milestone(db, m, c, client, DeliverySettlementEntry)
        db.commit()
        return {"ok": True, "settlement_entry_id": entry_id}

    @app.get("/api/contacts")
    async def list_contacts(
        client_id: Optional[int] = None,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.contacts.read")),
    ):
        q = db.query(Contact)
        if client_id:
            ds.assert_client_in_scope(db, ctx, client_id, Client, RESOURCE_CRM_CONTACT, "read")
            q = q.filter(Contact.client_id == client_id)
        q = ds.filter_query_by_client_scope(
            q, db, ctx, RESOURCE_CRM_CONTACT, "read", Contact.client_id, Client
        )
        rows = q.order_by(desc(Contact.created_at)).all()
        out = []
        for ct in rows:
            c = db.query(Client).filter(Client.id == ct.client_id).first()
            out.append(contact_to_dict(ct, c.name if c else ""))
        return out

    @app.post("/api/contacts")
    async def create_contact(
        body: ContactBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.contacts.write")),
    ):
        ds.assert_client_in_scope(db, ctx, body.client_id, Client, RESOURCE_CRM_CONTACT, "write")
        client = db.query(Client).filter(Client.id == body.client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="客户不存在")
        channel = (body.acquisition_channel or "").strip()
        if channel and channel not in CONTACT_ACQUISITION_CHANNELS:
            raise HTTPException(status_code=400, detail="获客渠道须为：个人、公司、其他")
        ct = Contact(
            client_id=body.client_id,
            name=body.name.strip(),
            title=body.title,
            city=(body.city or "").strip(),
            phone=body.phone,
            email=body.email,
            tags=body.tags,
            remarks=body.remarks,
            superior_contact=(body.superior_contact or "").strip(),
            acquisition_channel=channel,
            description=(body.description or "").strip(),
            created_by=(body.created_by or "").strip(),
            created_at=datetime.now(),
        )
        db.add(ct)
        db.commit()
        db.refresh(ct)
        return contact_to_dict(ct, client.name)

    @app.get("/api/export/contacts")
    async def export_contacts_csv(
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.contacts.read")),
    ):
        q = db.query(Contact)
        q = ds.filter_query_by_client_scope(
            q, db, ctx, RESOURCE_CRM_CONTACT, "read", Contact.client_id, Client
        )
        rows = q.order_by(desc(Contact.created_at)).all()
        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output)
        writer.writerow(CONTACT_EXPORT_HEADERS)
        for ct in rows:
            client = db.query(Client).filter(Client.id == ct.client_id).first()
            writer.writerow([
                ct.id,
                ct.name or "",
                client.name if client else "",
                ct.title or "",
                (getattr(ct, "city", None) or "").strip(),
                (getattr(ct, "created_by", None) or "").strip(),
                ct.phone or "",
                ct.email or "",
                relationship_from_contact_remarks(ct.remarks or ""),
                _contact_tags_export_label(ct.tags or ""),
                ct.acquisition_channel or "",
                ct.superior_contact or "",
                ct.description or "",
                _contact_created_at_export(ct.created_at),
            ])
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        response = StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv")
        set_csv_download_headers(
            response,
            chinese_filename=f"联系人列表_{ts}.csv",
            ascii_base=f"contacts_{ts}",
        )
        return response

    @app.post("/api/import/contacts")
    async def import_contacts_csv(
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.contacts.write")),
    ):
        raw = await file.read()
        if len(raw) > max_file_size:
            raise HTTPException(status_code=400, detail="文件超过大小限制")
        text = _strip_excel_sep_directive(decode_roster_upload_bytes(raw))
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise HTTPException(status_code=400, detail="CSV 缺少表头")
        imported = 0
        updated = 0
        skipped_details: List[Dict[str, str]] = []

        def _row_label(row_index: int, name: str) -> str:
            shown = (name or "").strip()
            return shown if shown else f"CSV第{row_index}行"

        def _resolve_client(client_name: str) -> Any:
            cn = (client_name or "").strip()
            if not cn:
                raise ValueError("客户不能为空")
            q = db.query(Client).filter(Client.name == cn)
            q = ds.filter_query_by_client_scope(
                q, db, ctx, RESOURCE_CRM_CONTACT, "write", Client.id, Client
            )
            matches = q.all()
            if not matches:
                raise ValueError(f"客户「{cn}」不存在或无写入权限")
            if len(matches) > 1:
                raise ValueError(f"客户名称「{cn}」存在多条，请使用唯一客户名")
            return matches[0]

        def _parse_row(row: Dict[str, str], row_index: int) -> Dict[str, str]:
            get = lambda key: str(row.get(key, "") or "").strip()
            relationship = get("关系")
            if relationship and relationship not in CONTACT_RELATIONSHIP_OPTIONS:
                raise ValueError("关系须为：普通、良好、密切")
            tag_label = get("分组标签")
            if tag_label and tag_label not in CONTACT_TAG_IMPORT_OPTIONS:
                raise ValueError("分组标签须为：首要、次要、一般")
            channel = get("获客渠道")
            if channel and channel not in CONTACT_ACQUISITION_CHANNELS:
                raise ValueError("获客渠道须为：个人、公司、其他")
            required = {
                "客户": get("客户"),
                "姓名": get("姓名"),
                "职位": get("职位"),
                "城市": get("城市"),
                "创建人": get("创建人"),
                "电话": get("电话"),
                "邮箱": get("邮箱"),
                "关系": relationship,
                "分组标签": tag_label,
                "获客渠道": channel,
                "说明": get("说明"),
            }
            for label, val in required.items():
                if not val:
                    raise ValueError(f"请填写{label}")
            return {
                "id_raw": get("ID"),
                "client_name": required["客户"],
                "name": required["姓名"],
                "title": required["职位"],
                "city": required["城市"],
                "created_by": required["创建人"],
                "phone": required["电话"],
                "email": required["邮箱"],
                "relationship": relationship,
                "tags": _contact_tags_from_import(tag_label),
                "acquisition_channel": channel,
                "superior_contact": get("联系人+1"),
                "description": required["说明"],
                "row_label": _row_label(row_index, required["姓名"]),
            }

        for row_index, row in enumerate(reader, start=2):
            if not any(str(v or "").strip() for v in row.values()):
                continue
            try:
                parsed = _parse_row(row, row_index)
            except ValueError as exc:
                skipped_details.append({"row": _row_label(row_index, str(row.get("姓名", ""))), "reason": str(exc)})
                continue
            try:
                client = _resolve_client(parsed["client_name"])
            except ValueError as exc:
                skipped_details.append({"row": parsed["row_label"], "reason": str(exc)})
                continue

            contact_id = None
            if parsed["id_raw"]:
                try:
                    contact_id = int(parsed["id_raw"])
                except ValueError:
                    skipped_details.append({"row": parsed["row_label"], "reason": "ID 格式无效"})
                    continue

            ct = None
            if contact_id is not None:
                ct = db.query(Contact).filter(Contact.id == contact_id).first()
                if not ct:
                    skipped_details.append({"row": parsed["row_label"], "reason": f"联系人 ID {contact_id} 不存在"})
                    continue
                try:
                    ds.assert_client_in_scope(db, ctx, ct.client_id, Client, RESOURCE_CRM_CONTACT, "write")
                    ds.assert_client_in_scope(db, ctx, client.id, Client, RESOURCE_CRM_CONTACT, "write")
                except HTTPException:
                    skipped_details.append({"row": parsed["row_label"], "reason": "联系人不属于可写入范围"})
                    continue
            else:
                dup_q = db.query(Contact).filter(Contact.client_id == client.id)
                if parsed["phone"]:
                    ct = dup_q.filter(Contact.phone == parsed["phone"]).first()
                elif parsed["email"]:
                    ct = dup_q.filter(Contact.email == parsed["email"]).first()
                if ct:
                    skipped_details.append({
                        "row": parsed["row_label"],
                        "reason": "同客户下电话或邮箱已存在",
                    })
                    continue

            remarks = contact_remarks_from_relationship(parsed["relationship"])
            if ct:
                ct.client_id = client.id
                ct.name = parsed["name"]
                ct.title = parsed["title"]
                ct.city = parsed["city"]
                ct.created_by = parsed["created_by"]
                ct.phone = parsed["phone"]
                ct.email = parsed["email"]
                ct.tags = parsed["tags"]
                ct.remarks = remarks
                ct.superior_contact = parsed["superior_contact"]
                ct.acquisition_channel = parsed["acquisition_channel"]
                ct.description = parsed["description"]
                if (ct.tags or "") == PRIMARY_CONTACT_TAG:
                    sync_client_inline_from_contact(client, ct)
                updated += 1
            else:
                db.add(Contact(
                    client_id=client.id,
                    name=parsed["name"],
                    title=parsed["title"],
                    city=parsed["city"],
                    created_by=parsed["created_by"],
                    phone=parsed["phone"],
                    email=parsed["email"],
                    tags=parsed["tags"],
                    remarks=remarks,
                    superior_contact=parsed["superior_contact"],
                    acquisition_channel=parsed["acquisition_channel"],
                    description=parsed["description"],
                    created_at=datetime.now(),
                ))
                imported += 1

        db.commit()
        skip_total = len(skipped_details)
        return {
            "imported": imported,
            "updated": updated,
            "skipped_total": skip_total,
            "skipped_details": skipped_details,
        }

    @app.put("/api/contacts/{contact_id}")
    async def update_contact(
        contact_id: int,
        body: ContactBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.contacts.write")),
    ):
        ct = db.query(Contact).filter(Contact.id == contact_id).first()
        if not ct:
            raise HTTPException(status_code=404, detail="联系人不存在")
        ds.assert_client_in_scope(db, ctx, ct.client_id, Client, RESOURCE_CRM_CONTACT, "write")
        ds.assert_client_in_scope(db, ctx, body.client_id, Client, RESOURCE_CRM_CONTACT, "write")
        client = db.query(Client).filter(Client.id == body.client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="客户不存在")
        channel = (body.acquisition_channel or "").strip()
        if channel and channel not in CONTACT_ACQUISITION_CHANNELS:
            raise HTTPException(status_code=400, detail="获客渠道须为：个人、公司、其他")
        resolved_primary = find_client_primary_contact(db, Contact, ct.client_id, client.contact_name)
        was_primary = (ct.tags or "") == PRIMARY_CONTACT_TAG or (
            resolved_primary is not None and resolved_primary.id == ct.id
        )
        ct.client_id = body.client_id
        ct.name = body.name.strip()
        ct.title = body.title
        ct.city = (body.city or "").strip()
        ct.created_by = (body.created_by or "").strip()
        ct.phone = body.phone
        ct.email = body.email
        ct.tags = body.tags
        ct.remarks = body.remarks
        ct.superior_contact = (body.superior_contact or "").strip()
        ct.acquisition_channel = channel
        ct.description = (body.description or "").strip()
        if was_primary or (ct.tags or "") == PRIMARY_CONTACT_TAG:
            ct.tags = PRIMARY_CONTACT_TAG
            sync_client_inline_from_contact(client, ct)
        db.commit()
        db.refresh(ct)
        return contact_to_dict(ct, client.name)

    @app.delete("/api/contacts/{contact_id}")
    async def delete_contact(
        contact_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.contacts.write")),
    ):
        ct = db.query(Contact).filter(Contact.id == contact_id).first()
        if not ct:
            raise HTTPException(status_code=404, detail="联系人不存在")
        ds.assert_client_in_scope(db, ctx, ct.client_id, Client, RESOURCE_CRM_CONTACT, "write")
        db.delete(ct)
        db.commit()
        return {"ok": True}

    @app.get("/api/clients/{client_id}/approved-handoff-summary")
    async def approved_handoff_summary(
        client_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("crm.opportunities.read")),
    ):
        h = (
            db.query(HandoffRequest)
            .filter(HandoffRequest.client_id == client_id, HandoffRequest.status == "approved")
            .order_by(desc(HandoffRequest.version))
            .first()
        )
        if not h:
            return {"approved": False}
        req = parse_requirement_json(h.requirement_json)
        return {
            "approved": True,
            "handoff_id": h.id,
            "title": h.title,
            "brief_md": h.ai_brief_md,
            "requirement": req,
            "approved_at": h.reviewed_at.isoformat() if h.reviewed_at else "",
        }

    @app.get("/contracts", response_class=HTMLResponse)
    async def page_contracts(request: Request):
        return page_renderer("pages/contracts_index.html", request)

    @app.get("/opportunity/leads", response_class=HTMLResponse)
    async def page_opportunity_leads(request: Request):
        return page_renderer("pages/opportunity_leads.html", request)

    @app.get("/opportunity/pool", response_class=HTMLResponse)
    async def page_opportunity_pool(request: Request):
        return RedirectResponse(url="/opportunity/leads", status_code=302)

    @app.get("/opportunity/dashboard", response_class=HTMLResponse)
    async def page_opportunity_dashboard(request: Request):
        return RedirectResponse(url="/home/funnel#goals", status_code=302)

    @app.get("/contacts/all", response_class=HTMLResponse)
    async def page_contacts_all(
        request: Request,
        _user: str = Depends(require_permission("crm.contacts.read")),
    ):
        return page_renderer("pages/contacts_all.html", request)

    @app.get("/contacts/tags", response_class=HTMLResponse)
    async def page_contacts_tags(
        request: Request,
        _user: str = Depends(require_permission("crm.contacts.read")),
    ):
        return RedirectResponse(url="/contacts/all", status_code=302)

    @app.get("/contacts/import", response_class=HTMLResponse)
    async def page_contacts_import(
        request: Request,
        _user: str = Depends(require_permission("crm.contacts.read")),
    ):
        return RedirectResponse(url="/contacts/all", status_code=302)

    @app.get("/goals/quarter", response_class=HTMLResponse)
    async def page_goals_quarter(request: Request):
        return RedirectResponse(url="/home/funnel#goals", status_code=302)

    @app.get("/goals/personal", response_class=HTMLResponse)
    async def page_goals_personal(request: Request):
        return RedirectResponse(url="/home/funnel#goals", status_code=302)

    @app.get("/goals/team", response_class=HTMLResponse)
    async def page_goals_team(request: Request):
        return RedirectResponse(url="/home/funnel#goals", status_code=302)

    return {"create_contract_from_handoff": create_contract_from_handoff}
