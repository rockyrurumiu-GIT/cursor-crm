"""Contract number generation for manual upload flow."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Type

from fastapi import HTTPException
from sqlalchemy.orm import Session

_TYPE_PREFIX = {
    "msa": "TRM-MSA",
    "nda": "TRM-NDA",
    "sow": "TRM-SOW",
    "agreement": "TRM-AGR",
}


def extract_client_abbr(client_name: str) -> str:
    """取客户名称末尾连续英文/数字段并转大写，如 蛮啾 MJ -> MJ。"""
    m = re.search(r"([A-Za-z0-9]+)\s*$", (client_name or "").strip())
    return m.group(1).upper() if m else ""


def assert_contract_no_available(
    db: Session,
    Contract: Type[Any],
    contract_no: str,
    *,
    exclude_id: int | None = None,
) -> None:
    no = (contract_no or "").strip()
    if not no:
        return
    q = db.query(Contract.id).filter(Contract.contract_no == no)
    if exclude_id is not None:
        q = q.filter(Contract.id != int(exclude_id))
    if q.first():
        raise HTTPException(status_code=400, detail="合同编号已存在")


def _next_sequence(
    db: Session,
    Contract: Type[Any],
    *,
    client_id: int,
    contract_type: str,
    prefix: str,
) -> int:
    rows = (
        db.query(Contract.contract_no)
        .filter(
            Contract.client_id == int(client_id),
            Contract.contract_type == contract_type,
            Contract.contract_no.like(f"{prefix}%"),
        )
        .all()
    )
    max_seq = 0
    for (no,) in rows:
        tail = (no or "").rsplit("-", 1)[-1]
        if tail.isdigit():
            max_seq = max(max_seq, int(tail))
    return max_seq + 1


def generate_contract_no(
    db: Session,
    Contract: Type[Any],
    *,
    client_id: int,
    client_name: str,
    contract_type: str,
    year: int | None = None,
) -> str:
    ct = (contract_type or "").strip().lower()
    tag = _TYPE_PREFIX.get(ct)
    if not tag:
        raise HTTPException(status_code=400, detail="无效的合同类型")

    abbr = extract_client_abbr(client_name)
    if not abbr:
        raise HTTPException(status_code=400, detail="客户名称缺少英文简写，无法生成合同编号")

    yr = int(year if year is not None else datetime.now().year)
    if ct in ("msa", "nda"):
        return f"{tag}-{abbr}-{yr}"

    prefix = f"{tag}-{abbr}-{yr}-"
    seq = _next_sequence(
        db,
        Contract,
        client_id=client_id,
        contract_type=ct,
        prefix=prefix,
    )
    return f"{prefix}{seq:02d}"
