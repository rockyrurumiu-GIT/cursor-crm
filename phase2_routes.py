"""Phase 2 CRM routes: Opportunity, Contract, Contact."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from fastapi import Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from handoff_core import generate_brief_markdown, parse_requirement_json
from phase2_core import (
    OPPORTUNITY_STAGE_LABELS,
    OPPORTUNITY_STAGES,
    build_contract_from_handoff,
    contact_to_dict,
    contract_to_dict,
    milestone_to_dict,
    opportunity_to_dict,
    suggest_milestones_from_requirement,
)


class OpportunityBody(BaseModel):
    client_id: int
    name: str
    amount: str = ""
    probability: str = ""
    expected_close_date: str = ""
    stage: str = "qualifying"
    owner: str = ""
    remarks: str = ""


class ContactBody(BaseModel):
    client_id: int
    name: str
    title: str = ""
    phone: str = ""
    email: str = ""
    tags: str = ""
    remarks: str = ""


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
):
    @app.get("/api/opportunities")
    async def list_opportunities(
        client_id: Optional[int] = None,
        stage: Optional[str] = None,
        db: Session = Depends(get_db),
        user: str = Depends(authenticate),
    ):
        q = db.query(Opportunity)
        if client_id:
            q = q.filter(Opportunity.client_id == client_id)
        if stage:
            q = q.filter(Opportunity.stage == stage)
        rows = q.order_by(desc(Opportunity.created_at)).all()
        out = []
        for o in rows:
            c = db.query(Client).filter(Client.id == o.client_id).first()
            out.append(opportunity_to_dict(o, c.name if c else ""))
        return out

    @app.post("/api/opportunities")
    async def create_opportunity(
        body: OpportunityBody,
        db: Session = Depends(get_db),
        user: str = Depends(authenticate),
    ):
        if body.stage not in OPPORTUNITY_STAGES:
            raise HTTPException(status_code=400, detail="无效商机阶段")
        client = db.query(Client).filter(Client.id == body.client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="客户不存在")
        o = Opportunity(
            client_id=body.client_id,
            name=body.name.strip(),
            amount=body.amount,
            probability=body.probability,
            expected_close_date=body.expected_close_date,
            stage=body.stage,
            owner=body.owner or client.owner or user,
            remarks=body.remarks,
        )
        db.add(o)
        db.commit()
        db.refresh(o)
        return opportunity_to_dict(o, client.name)

    @app.put("/api/opportunities/{opp_id}")
    async def update_opportunity(
        opp_id: int,
        body: OpportunityBody,
        db: Session = Depends(get_db),
        user: str = Depends(authenticate),
    ):
        o = db.query(Opportunity).filter(Opportunity.id == opp_id).first()
        if not o:
            raise HTTPException(status_code=404, detail="商机不存在")
        if body.stage not in OPPORTUNITY_STAGES:
            raise HTTPException(status_code=400, detail="无效商机阶段")
        o.name = body.name.strip()
        o.amount = body.amount
        o.probability = body.probability
        o.expected_close_date = body.expected_close_date
        o.stage = body.stage
        o.owner = body.owner
        o.remarks = body.remarks
        db.commit()
        client = db.query(Client).filter(Client.id == o.client_id).first()
        return opportunity_to_dict(o, client.name if client else "")

    @app.post("/api/opportunities/{opp_id}/create-handoff")
    async def opp_create_handoff(opp_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
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
        user: str = Depends(authenticate),
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
    async def get_contract(contract_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
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
        user: str = Depends(authenticate),
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
        user: str = Depends(authenticate),
    ):
        q = db.query(Contact)
        if client_id:
            q = q.filter(Contact.client_id == client_id)
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
        user: str = Depends(authenticate),
    ):
        client = db.query(Client).filter(Client.id == body.client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="客户不存在")
        ct = Contact(
            client_id=body.client_id,
            name=body.name.strip(),
            title=body.title,
            phone=body.phone,
            email=body.email,
            tags=body.tags,
            remarks=body.remarks,
        )
        db.add(ct)
        db.commit()
        db.refresh(ct)
        return contact_to_dict(ct, client.name)

    @app.delete("/api/contacts/{contact_id}")
    async def delete_contact(contact_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
        ct = db.query(Contact).filter(Contact.id == contact_id).first()
        if not ct:
            raise HTTPException(status_code=404, detail="联系人不存在")
        db.delete(ct)
        db.commit()
        return {"ok": True}

    @app.get("/api/clients/{client_id}/approved-handoff-summary")
    async def approved_handoff_summary(
        client_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)
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
    async def page_contacts_all(request: Request):
        return page_renderer("pages/contacts_all.html", request)

    @app.get("/contacts/tags", response_class=HTMLResponse)
    async def page_contacts_tags(request: Request):
        return RedirectResponse(url="/contacts/all", status_code=302)

    @app.get("/contacts/import", response_class=HTMLResponse)
    async def page_contacts_import(request: Request):
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
