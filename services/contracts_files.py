"""Contract attachment upload, filter, and download helpers."""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Type

from fastapi import HTTPException, UploadFile
from sqlalchemy import desc
from sqlalchemy.orm import Session

import security_foundation as sec
from auth.service import AuthContext
from phase2_core import CONTRACT_STATUS_LABELS, CONTRACT_STATUSES, contract_to_dict, milestone_to_dict
from schemas.company_materials import MATERIAL_ALLOWED_SUFFIXES
from services.company_materials import _load_user_names, _write_upload_chunked, safe_material_filename


def contract_stored_path_rel(filename: str) -> str:
    safe = safe_material_filename(filename)
    now = datetime.now()
    return f"contracts/{now.year:04d}/{now.month:02d}/{uuid.uuid4().hex}_{safe}"


def list_form_options(db: Session, Client: Type[Any]) -> Dict[str, Any]:
    clients = (
        db.query(Client.id, Client.name)
        .order_by(Client.name)
        .all()
    )
    return {
        "statuses": [{"value": k, "label": v} for k, v in CONTRACT_STATUS_LABELS.items()],
        "clients": [{"id": int(c.id), "name": str(c.name or "")} for c in clients],
    }


def _resolve_sales_owner(db: Session, handoffs: Dict[int, Any], c: Any, client: Any) -> str:
    handoff = handoffs.get(c.handoff_id) if c.handoff_id else None
    return (handoff.sales_owner if handoff else "") or (client.owner if client else "")


def list_contract_rows(
    db: Session,
    Contract: Type[Any],
    Client: Type[Any],
    HandoffRequest: Type[Any],
    ContractMilestone: Type[Any],
    *,
    client_id: Optional[int] = None,
    status: Optional[str] = None,
    expires_before: Optional[str] = None,
    q_text: Optional[str] = None,
) -> List[Dict[str, Any]]:
    q = db.query(Contract)
    if client_id is not None:
        q = q.filter(Contract.client_id == int(client_id))
    st = (status or "").strip().lower()
    if st:
        if st not in CONTRACT_STATUSES:
            raise HTTPException(status_code=400, detail="无效的状态筛选")
        q = q.filter(Contract.status == st)
    if expires_before:
        exp = expires_before.strip()
        q = q.filter(Contract.end_date != None).filter(Contract.end_date <= exp)  # noqa: E711
    rows = q.order_by(desc(Contract.created_at)).all()
    handoff_ids = {c.handoff_id for c in rows if c.handoff_id}
    handoffs: Dict[int, Any] = {}
    if handoff_ids:
        for h in db.query(HandoffRequest).filter(HandoffRequest.id.in_(handoff_ids)).all():
            handoffs[h.id] = h
    user_ids = [int(c.uploaded_by) for c in rows if getattr(c, "uploaded_by", None)]
    user_names = _load_user_names(db, user_ids)
    needle = (q_text or "").strip().lower()
    out: List[Dict[str, Any]] = []
    for c in rows:
        client = db.query(Client).filter(Client.id == c.client_id).first()
        ms = db.query(ContractMilestone).filter(ContractMilestone.contract_id == c.id).all()
        sales_owner = _resolve_sales_owner(db, handoffs, c, client)
        uploaded_by_name = user_names.get(int(c.uploaded_by), "") if getattr(c, "uploaded_by", None) else ""
        item = contract_to_dict(
            c,
            client.name if client else "",
            [milestone_to_dict(m) for m in ms],
            sales_owner=sales_owner,
            uploaded_by_name=uploaded_by_name,
        )
        if needle:
            hay = " ".join(
                str(item.get(k) or "")
                for k in (
                    "material_name",
                    "title",
                    "client_name",
                    "contract_no",
                    "file_name",
                    "sales_owner",
                    "uploaded_by_name",
                )
            ).lower()
            if needle not in hay:
                continue
        out.append(item)
    return out


def _contract_row(db: Session, Contract: Type[Any], contract_id: int):
    row = db.query(Contract).filter(Contract.id == contract_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="合同不存在")
    return row


def _validate_client(db: Session, Client: Type[Any], client_id: int) -> Any:
    client = db.query(Client).filter(Client.id == int(client_id)).first()
    if not client:
        raise HTTPException(status_code=400, detail="客户不存在")
    return client


async def create_contract_with_file(
    db: Session,
    ctx: AuthContext,
    Contract: Type[Any],
    Client: Type[Any],
    *,
    title: str,
    client_id: int,
    contract_no: str,
    end_date: str,
    upload: UploadFile,
    upload_dir: str,
    max_file_size: int,
    allowed_suffixes: Set[str],
) -> Dict[str, Any]:
    t = str(title or "").strip()
    if not t:
        raise HTTPException(status_code=400, detail="请填写资料名称")
    client = _validate_client(db, Client, client_id)
    stored_rel = contract_stored_path_rel(upload.filename or "contract.bin")
    try:
        abs_path = sec.resolve_upload_path(upload_dir, stored_rel)
    except ValueError:
        raise HTTPException(status_code=400, detail="非法文件路径")
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    file_name, mime_type, file_size = await _write_upload_chunked(
        upload,
        abs_path,
        max_file_size=max_file_size,
        allowed_suffixes=allowed_suffixes,
    )
    now = datetime.now()
    row = Contract(
        client_id=int(client_id),
        contract_no=str(contract_no or "").strip(),
        title=t,
        end_date=str(end_date or "").strip(),
        status="draft",
        file_name=file_name,
        stored_path=stored_rel,
        mime_type=mime_type,
        file_size=file_size,
        uploaded_by=ctx.user_id,
        created_at=now,
        updated_at=now,
    )
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        if os.path.isfile(abs_path):
            try:
                os.remove(abs_path)
            except OSError:
                pass
        raise
    uploaded_by_name = ""
    if ctx.user_id:
        names = _load_user_names(db, [int(ctx.user_id)])
        uploaded_by_name = names.get(int(ctx.user_id), "")
    return contract_to_dict(
        row,
        client.name if client else "",
        [],
        sales_owner=client.owner if client else "",
        uploaded_by_name=uploaded_by_name,
    )


async def replace_contract_file(
    db: Session,
    ctx: AuthContext,
    Contract: Type[Any],
    contract_id: int,
    *,
    upload: UploadFile,
    upload_dir: str,
    max_file_size: int,
    allowed_suffixes: Set[str],
) -> Dict[str, Any]:
    row = _contract_row(db, Contract, contract_id)
    old_stored_path = (getattr(row, "stored_path", None) or "").strip()
    if old_stored_path:
        try:
            old_abs_path = sec.resolve_upload_path(upload_dir, old_stored_path)
            if os.path.isfile(old_abs_path):
                os.remove(old_abs_path)
        except (ValueError, OSError):
            pass
    stored_rel = contract_stored_path_rel(upload.filename or "contract.bin")
    try:
        abs_path = sec.resolve_upload_path(upload_dir, stored_rel)
    except ValueError:
        raise HTTPException(status_code=400, detail="非法文件路径")
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    file_name, mime_type, file_size = await _write_upload_chunked(
        upload,
        abs_path,
        max_file_size=max_file_size,
        allowed_suffixes=allowed_suffixes,
    )
    row.file_name = file_name
    row.stored_path = stored_rel
    row.mime_type = mime_type
    row.file_size = file_size
    row.uploaded_by = ctx.user_id
    row.updated_at = datetime.now()
    db.commit()
    db.refresh(row)
    return {"ok": True, "file_name": file_name, "file_size": file_size}


def download_contract_file(
    db: Session,
    Contract: Type[Any],
    contract_id: int,
    *,
    upload_dir: str,
):
    from fastapi.responses import FileResponse

    row = _contract_row(db, Contract, contract_id)
    stored_path = (getattr(row, "stored_path", None) or "").strip()
    if not stored_path:
        raise HTTPException(status_code=404, detail="该合同暂无附件")
    try:
        abs_path = sec.resolve_upload_path(upload_dir, stored_path)
    except ValueError:
        raise HTTPException(status_code=400, detail="非法文件路径")
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="附件文件不存在")
    mime = (getattr(row, "mime_type", None) or "").strip() or "application/octet-stream"
    filename = (getattr(row, "file_name", None) or "").strip() or os.path.basename(abs_path)
    return FileResponse(abs_path, media_type=mime, filename=filename)
