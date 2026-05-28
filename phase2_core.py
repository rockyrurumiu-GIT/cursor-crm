"""Phase 2: Opportunity, Contract, Milestone, Contact business logic."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

OPPORTUNITY_STAGES = frozenset({"initial", "qualifying", "proposal", "negotiating", "won", "lost"})
CONTACT_ACQUISITION_CHANNELS = frozenset({"个人", "公司", "其他"})
PRIMARY_CONTACT_TAG = "首要联系人"
OPPORTUNITY_STAGE_LABELS = {
    "initial": "商机确认 / 初步接触",
    "qualifying": "需求分析 / 方案匹配",
    "proposal": "方案建议 / 报价演示",
    "negotiating": "谈判 / 赢单谈判",
    "won": "赢单结案 / 签约",
    "lost": "输单结案",
}

CONTRACT_STATUSES = frozenset({"draft", "signed", "active", "closed"})
CONTRACT_STATUS_LABELS = {
    "draft": "草稿",
    "signed": "已签约",
    "active": "执行中",
    "closed": "已关闭",
}

MILESTONE_STATUSES = frozenset({"pending", "invoiced", "paid"})
MILESTONE_STATUS_LABELS = {"pending": "待开票", "invoiced": "已开票", "paid": "已回款"}


def _parse_numeric_amount(raw: str) -> float:
    s = "".join(ch for ch in str(raw or "") if ch.isdigit() or ch == ".")
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _format_wan_amount(wan: float) -> str:
    if wan <= 0:
        return ""
    return f"{wan:.2f}".rstrip("0").rstrip(".")


def compute_client_estimated_annual_amount_wan(db, client_id: int, Opportunity) -> str:
    """客户预估当年合作金额（万元）= SUM(商机预估当年金额 × 赢单率)，排除输单。"""
    opps = (
        db.query(Opportunity)
        .filter(Opportunity.client_id == client_id, Opportunity.stage != "lost")
        .all()
    )
    total_yuan = 0.0
    for o in opps:
        amount_yuan = _parse_numeric_amount(o.estimated_current_year_amount)
        win_rate = _parse_numeric_amount(o.probability) / 100.0
        total_yuan += amount_yuan * win_rate
    return _format_wan_amount(total_yuan / 10000.0)


def refresh_client_estimated_annual_amount(db, client_id: int, Client, Opportunity) -> str:
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return ""
    new_val = compute_client_estimated_annual_amount_wan(db, client_id, Opportunity)
    client.estimated_annual_amount = new_val
    return new_val


def opportunity_to_dict(o, client_name: str = "") -> Dict[str, Any]:
    return {
        "id": o.id,
        "client_id": o.client_id,
        "client_name": client_name,
        "name": o.name or "",
        "amount": o.amount or "",
        "estimated_current_year_amount": o.estimated_current_year_amount or "",
        "probability": o.probability or "",
        "expected_close_date": o.expected_close_date or "",
        "stage": o.stage or "initial",
        "stage_label": OPPORTUNITY_STAGE_LABELS.get(o.stage, o.stage),
        "owner": o.owner or "",
        "remarks": o.remarks or "",
        "created_at": o.created_at.isoformat() if o.created_at else "",
    }


def contract_to_dict(c, client_name: str = "", milestones: Optional[List[Dict]] = None) -> Dict[str, Any]:
    return {
        "id": c.id,
        "client_id": c.client_id,
        "client_name": client_name,
        "handoff_id": c.handoff_id,
        "opportunity_id": c.opportunity_id,
        "contract_no": c.contract_no or "",
        "contract_type": c.contract_type or "",
        "title": c.title or "",
        "total_amount": c.total_amount or "",
        "start_date": c.start_date or "",
        "end_date": c.end_date or "",
        "status": c.status or "draft",
        "status_label": CONTRACT_STATUS_LABELS.get(c.status, c.status),
        "sow_markdown": c.sow_markdown or "",
        "milestones": milestones or [],
        "created_at": c.created_at.isoformat() if c.created_at else "",
    }


def milestone_to_dict(m) -> Dict[str, Any]:
    return {
        "id": m.id,
        "contract_id": m.contract_id,
        "name": m.name or "",
        "deliverable": m.deliverable or "",
        "invoice_pct": m.invoice_pct or "",
        "planned_date": m.planned_date or "",
        "amount": m.amount or "",
        "status": m.status or "pending",
        "status_label": MILESTONE_STATUS_LABELS.get(m.status, m.status),
        "settlement_entry_id": m.settlement_entry_id,
    }


def contact_to_dict(c, client_name: str = "") -> Dict[str, Any]:
    return {
        "id": c.id,
        "client_id": c.client_id,
        "client_name": client_name,
        "name": c.name or "",
        "title": c.title or "",
        "phone": c.phone or "",
        "email": c.email or "",
        "tags": c.tags or "",
        "remarks": c.remarks or "",
        "superior_contact": c.superior_contact or "",
        "acquisition_channel": c.acquisition_channel or "",
        "description": c.description or "",
        "created_at": c.created_at.isoformat() if c.created_at else "",
    }


def parse_client_contact_info(contact_info: str) -> Tuple[str, str]:
    info = (contact_info or "").strip()
    if "@" in info:
        return "", info
    return info, ""


def format_client_contact_info(phone: str, email: str) -> str:
    phone = (phone or "").strip()
    email = (email or "").strip()
    if email:
        return email
    return phone


def relationship_from_contact_remarks(remarks: str) -> str:
    r = (remarks or "").strip()
    return r[3:] if r.startswith("关系：") else ""


def contact_remarks_from_relationship(relationship: str) -> str:
    rel = (relationship or "").strip()
    return f"关系：{rel}" if rel else ""


def find_client_primary_contact(db, Contact, client_id: int, contact_name: str):
    tagged = (
        db.query(Contact)
        .filter(Contact.client_id == client_id, Contact.tags == PRIMARY_CONTACT_TAG)
        .first()
    )
    if tagged:
        return tagged

    name = (contact_name or "").strip()
    if name:
        by_name = (
            db.query(Contact)
            .filter(Contact.client_id == client_id, Contact.name == name)
            .order_by(Contact.id)
            .first()
        )
        if by_name:
            return by_name

    rows = (
        db.query(Contact)
        .filter(Contact.client_id == client_id)
        .order_by(Contact.id)
        .all()
    )
    if len(rows) == 1:
        return rows[0]
    return None


def apply_client_contact_to_row(contact, client) -> None:
    name = (client.contact_name or "").strip()
    phone, email = parse_client_contact_info(client.contact_info)
    contact.name = name
    contact.title = (client.contact_title or "").strip()
    contact.phone = phone
    contact.email = email
    contact.remarks = contact_remarks_from_relationship(client.contact_relationship)
    contact.acquisition_channel = (client.contact_acquisition_channel or "").strip()
    contact.superior_contact = (client.contact_superior_contact or "").strip()
    contact.description = (client.contact_description or "").strip()
    contact.tags = PRIMARY_CONTACT_TAG


def sync_client_inline_from_contact(client, contact) -> None:
    client.contact_name = (contact.name or "").strip()
    client.contact_title = (contact.title or "").strip()
    client.contact_info = format_client_contact_info(contact.phone, contact.email)
    client.contact_relationship = relationship_from_contact_remarks(contact.remarks)
    client.contact_acquisition_channel = (contact.acquisition_channel or "").strip()
    client.contact_superior_contact = (contact.superior_contact or "").strip()
    client.contact_description = (contact.description or "").strip()


def sync_client_primary_contact(db, Contact, client) -> None:
    """将 Client 内联联系人同步到 contacts 表（更新已有记录，避免重复）。"""
    name = (client.contact_name or "").strip()
    primary = find_client_primary_contact(db, Contact, client.id, name)

    if not name:
        if primary and (primary.tags or "") == PRIMARY_CONTACT_TAG:
            db.delete(primary)
        return

    if primary:
        apply_client_contact_to_row(primary, client)
        db.query(Contact).filter(
            Contact.client_id == client.id,
            Contact.id != primary.id,
            Contact.name == name,
            Contact.tags != PRIMARY_CONTACT_TAG,
        ).delete(synchronize_session=False)
        return

    phone, email = parse_client_contact_info(client.contact_info)
    db.add(
        Contact(
            client_id=client.id,
            name=name,
            title=(client.contact_title or "").strip(),
            phone=phone,
            email=email,
            tags=PRIMARY_CONTACT_TAG,
            remarks=contact_remarks_from_relationship(client.contact_relationship),
            acquisition_channel=(client.contact_acquisition_channel or "").strip(),
            superior_contact=(client.contact_superior_contact or "").strip(),
            description=(client.contact_description or "").strip(),
            created_at=datetime.now(),
        )
    )


def suggest_milestones_from_requirement(
    requirement: Dict[str, Any], total_amount: str
) -> List[Dict[str, Any]]:
    """从岗位矩阵与商务信息生成建议里程碑。"""
    positions = requirement.get("positions") or []
    comm = requirement.get("commercial") or {}
    amount = total_amount or comm.get("estimated_amount") or ""
    milestones: List[Dict[str, Any]] = []
    if positions:
        roles = ", ".join(str(p.get("role") or "") for p in positions[:3])
        first_date = str(positions[0].get("start_date") or "")[:10]
        milestones.append(
            {
                "name": "Phase1 人员到岗",
                "deliverable": f"核心岗位到位：{roles}",
                "invoice_pct": "50",
                "planned_date": first_date,
                "amount": amount,
            }
        )
        milestones.append(
            {
                "name": "Phase2 稳定交付",
                "deliverable": "编制满员且通过客户验收",
                "invoice_pct": "50",
                "planned_date": first_date,
                "amount": "",
            }
        )
    else:
        milestones.append(
            {
                "name": "项目启动",
                "deliverable": "完成交接并通过交付准备",
                "invoice_pct": "100",
                "planned_date": datetime.now().strftime("%Y-%m-%d"),
                "amount": amount,
            }
        )
    return milestones


def build_contract_from_handoff(
    client_id: int,
    handoff_id: int,
    client_name: str,
    handoff_title: str,
    requirement: Dict[str, Any],
    brief_md: str,
    opportunity_id: Optional[int] = None,
) -> Dict[str, Any]:
    comm = requirement.get("commercial") or {}
    ts = datetime.now().strftime("%Y%m%d")
    return {
        "client_id": client_id,
        "handoff_id": handoff_id,
        "opportunity_id": opportunity_id,
        "contract_no": f"SOW-{client_name[:8]}-{ts}",
        "contract_type": "项目",
        "title": handoff_title or f"{client_name} 外包服务合同",
        "total_amount": comm.get("estimated_amount") or "",
        "start_date": datetime.now().strftime("%Y-%m-%d"),
        "end_date": "",
        "status": "draft",
        "sow_markdown": brief_md or "",
    }
