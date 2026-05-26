"""Settlement business logic — migrated from main.py (Phase 2)."""
from __future__ import annotations

import csv
import io
import os
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Type

from fastapi import HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session


SETTLEMENT_EXPORT_HEADERS = [
    "序号",
    "结算进度更新日期",
    "客户",
    "费用月份",
    "追款月份",
    "金额",
    "内部确认考勤",
    "客户确认",
    "是否开票",
    "开票日期",
    "是否回款",
    "预计回款时间",
    "实际回款时间",
    "回款天数",
    "回款周期",
    "回款性质",
    "PO单",
    "发票号",
    "备注",
]

SETTLEMENT_HEADER_MAP = {
    "序号": "serial_no",
    "结算进度更新日期": "progress_updated_at",
    "客户": "customer_name",
    "费用月份": "fee_month",
    "追款月份": "chase_month",
    "金额": "amount",
    "内部确认考勤": "internal_attendance_confirm",
    "客户确认": "client_confirm",
    "是否开票": "invoiced",
    "开票日期": "invoice_date",
    "是否回款": "paid",
    "预计回款时间": "expected_payment_date",
    "实际回款时间": "actual_payment_date",
    "回款天数": "payment_days",
    "回款周期": "payment_cycle",
    "回款性质": "payment_nature",
    "PO单": "po_no",
    "发票号": "invoice_no",
    "备注": "remarks",
}

SETTLEMENT_REQUIRED_FIELDS = (
    "customer_name",
    "fee_month",
    "amount",
    "internal_attendance_confirm",
    "client_confirm",
    "invoiced",
    "paid",
    "payment_cycle",
)

SETTLEMENT_REQUIRED_LABELS = {
    "customer_name": "客户",
    "fee_month": "费用月份",
    "amount": "金额",
    "internal_attendance_confirm": "内部确认考勤",
    "client_confirm": "客户确认",
    "invoiced": "是否开票",
    "paid": "是否回款",
    "payment_cycle": "回款周期",
}


def settlement_entry_to_dict(e) -> Dict[str, Any]:
    return {
        "id": e.id,
        "client_id": e.client_id,
        "serial_no": e.serial_no or "",
        "progress_updated_at": e.progress_updated_at or "",
        "customer_name": e.customer_name or "",
        "fee_month": e.fee_month or "",
        "chase_month": e.chase_month or "",
        "amount": e.amount or "",
        "internal_attendance_confirm": e.internal_attendance_confirm or "",
        "client_confirm": e.client_confirm or "",
        "invoiced": e.invoiced or "",
        "invoice_date": e.invoice_date or "",
        "paid": e.paid or "",
        "expected_payment_date": e.expected_payment_date or "",
        "actual_payment_date": e.actual_payment_date or "",
        "payment_days": e.payment_days or "",
        "payment_cycle": e.payment_cycle or "",
        "payment_nature": e.payment_nature or "",
        "po_no": e.po_no or "",
        "invoice_no": e.invoice_no or "",
        "remarks": e.remarks or "",
    }


def normalize_settlement_amount(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    s = re.sub(r"[¥￥,\s\u00a0]", "", s)
    try:
        n = float(s)
    except ValueError:
        return ""
    return f"{n:.2f}"


def normalize_settlement_payload(d: Dict[str, Any]) -> Dict[str, str]:
    keys = [
        "serial_no",
        "progress_updated_at",
        "customer_name",
        "fee_month",
        "chase_month",
        "amount",
        "internal_attendance_confirm",
        "client_confirm",
        "invoiced",
        "invoice_date",
        "paid",
        "expected_payment_date",
        "actual_payment_date",
        "payment_days",
        "payment_cycle",
        "payment_nature",
        "po_no",
        "invoice_no",
        "remarks",
    ]
    out: Dict[str, str] = {}
    for k in keys:
        v = d.get(k, "")
        if v is None:
            v = ""
        out[k] = str(v).strip()
    out["amount"] = normalize_settlement_amount(out.get("amount", ""))
    return out


def validate_settlement_payload(data: Dict[str, str]) -> None:
    missing = [k for k in SETTLEMENT_REQUIRED_FIELDS if not str(data.get(k, "")).strip()]
    if missing:
        labels = [SETTLEMENT_REQUIRED_LABELS.get(k, k) for k in missing]
        raise HTTPException(status_code=400, detail=f"以下必填项未填写：{'、'.join(labels)}")

    for k, label in (
        ("internal_attendance_confirm", "内部确认考勤"),
        ("client_confirm", "客户确认"),
        ("invoiced", "是否开票"),
        ("paid", "是否回款"),
    ):
        v = str(data.get(k, "")).strip()
        if v and v not in ("是", "否"):
            raise HTTPException(status_code=400, detail=f"{label}仅支持\u201c是/否\u201d")

    payment_cycle = str(data.get("payment_cycle", "")).strip()
    if payment_cycle and payment_cycle not in ("月度", "双月", "季度", "半年度"):
        raise HTTPException(status_code=400, detail="回款周期仅支持：月度、双月、季度、半年度")

    payment_nature = str(data.get("payment_nature", "")).strip()
    if payment_nature and payment_nature not in ("增量回款", "存量回款"):
        raise HTTPException(status_code=400, detail="回款性质仅支持：增量回款、存量回款")
    amount = str(data.get("amount", "")).strip()
    if amount:
        try:
            float(amount)
        except ValueError:
            raise HTTPException(status_code=400, detail="金额格式不正确")


def resolve_settlement_client_id(db: Session, customer_name: str, Client, require_existing: bool) -> Optional[int]:
    name = str(customer_name or "").strip()
    c = db.query(Client).filter(Client.name == name).first() if name else None
    if require_existing and not c:
        raise HTTPException(status_code=400, detail="手动新增/修改时，客户必须从已建客户名单中选择")
    return c.id if c else None


def settlement_dedup_key(customer_name: str, fee_month: str, amount: str, remarks: str) -> str:
    cn = str(customer_name or "").strip()
    fm = str(fee_month or "").strip()
    am = str(amount or "").strip()
    rm = str(remarks or "").strip()
    if not cn or not fm or not am:
        return ""
    return f"{cn}||{fm}||{am}||{rm}"


def resequence_settlement_serial_no_all(db: Session, DeliverySettlementEntry) -> None:
    rows = db.query(DeliverySettlementEntry).order_by(DeliverySettlementEntry.id).all()
    for idx, row in enumerate(rows, start=1):
        row.serial_no = str(idx)


def write_settlement_backup_csv(rows, backup_dir: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"settlement_backup_{ts}.csv"
    path = os.path.join(backup_dir, name)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(SETTLEMENT_EXPORT_HEADERS)
        for e in rows:
            d = settlement_entry_to_dict(e)
            writer.writerow([d.get(SETTLEMENT_HEADER_MAP[h], "") for h in SETTLEMENT_EXPORT_HEADERS])
    return name
