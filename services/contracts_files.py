"""Contract attachment upload, filter, and download helpers."""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Type

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

import security_foundation as sec
from auth.service import AuthContext
from phase2_core import (
    CONTRACT_EXPIRY_STATUSES,
    CONTRACT_EXPIRY_STATUS_LABELS,
    CONTRACT_TYPE_LABELS,
    CONTRACT_UPLOAD_TYPES,
    contract_to_dict,
    milestone_to_dict,
)
from schemas.company_materials import (
    MATERIAL_ALLOWED_SUFFIXES,
    MATERIAL_OFFICE_CONVERT_SUFFIXES,
    MATERIAL_PREVIEWABLE_SUFFIXES,
    MATERIAL_PREVIEW_CONVERSION_FAILED_MSG,
    MATERIAL_PREVIEW_UNSUPPORTED_MSG,
)
from services.company_materials import _load_user_names, _write_upload_chunked, safe_material_filename
from services.contract_numbering import assert_contract_no_available, extract_client_abbr, generate_contract_no
from services.material_preview_conversion import (
    MaterialPreviewConversionError,
    convert_office_to_preview_pdf,
)

_MEDIA_TYPE_BY_EXT = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def _file_ext(name: str) -> str:
    n = (name or "").strip().lower()
    i = n.rfind(".")
    return n[i:] if i >= 0 else ""


def contract_stored_path_rel(filename: str) -> str:
    safe = safe_material_filename(filename)
    now = datetime.now()
    return f"contracts/{now.year:04d}/{now.month:02d}/{uuid.uuid4().hex}_{safe}"


def _client_sales_owner_name(db: Session, client: Any) -> str:
    uid = getattr(client, "owner_user_id", None)
    if uid:
        names = _load_user_names(db, [int(uid)])
        label = names.get(int(uid), "")
        if label:
            return label
    return (getattr(client, "owner", None) or "").strip()


def list_form_options(db: Session, Client: Type[Any]) -> Dict[str, Any]:
    clients = db.query(Client).order_by(Client.name).all()
    owner_ids = [int(c.owner_user_id) for c in clients if getattr(c, "owner_user_id", None)]
    owner_names = _load_user_names(db, owner_ids)
    return {
        "statuses": [
            {"value": k, "label": v} for k, v in CONTRACT_EXPIRY_STATUS_LABELS.items()
        ],
        "contract_types": [
            {"value": k, "label": v}
            for k, v in CONTRACT_TYPE_LABELS.items()
            if k in CONTRACT_UPLOAD_TYPES
        ],
        "clients": [
            {
                "id": int(c.id),
                "name": str(c.name or ""),
                "sales_owner_user_id": getattr(c, "owner_user_id", None),
                "sales_owner_name": (
                    owner_names.get(int(c.owner_user_id), "")
                    if getattr(c, "owner_user_id", None)
                    else ""
                )
                or (c.owner or ""),
                "client_abbr": extract_client_abbr(str(c.name or "")),
            }
            for c in clients
        ],
    }


def _resolve_sales_owner(
    db: Session,
    handoffs: Dict[int, Any],
    c: Any,
    client: Any,
    *,
    owner_names: Optional[Dict[int, str]] = None,
) -> str:
    handoff = handoffs.get(c.handoff_id) if c.handoff_id else None
    if handoff and (handoff.sales_owner or "").strip():
        return (handoff.sales_owner or "").strip()
    if client:
        uid = getattr(client, "owner_user_id", None)
        if uid and owner_names:
            label = owner_names.get(int(uid), "")
            if label:
                return label
        return (client.owner or "").strip()
    return ""


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
    if expires_before:
        exp = expires_before.strip()
        q = q.filter(Contract.end_date != None).filter(Contract.end_date <= exp)  # noqa: E711
    rows = q.order_by(desc(Contract.created_at)).all()
    st = (status or "").strip().lower()
    if st and st not in CONTRACT_EXPIRY_STATUSES:
        raise HTTPException(status_code=400, detail="无效的状态筛选")

    handoff_ids = {c.handoff_id for c in rows if c.handoff_id}
    handoffs: Dict[int, Any] = {}
    if handoff_ids:
        for h in db.query(HandoffRequest).filter(HandoffRequest.id.in_(handoff_ids)).all():
            handoffs[h.id] = h

    client_ids = {c.client_id for c in rows if c.client_id}
    clients_by_id: Dict[int, Any] = {}
    owner_ids: List[int] = []
    if client_ids:
        for cl in db.query(Client).filter(Client.id.in_(client_ids)).all():
            clients_by_id[int(cl.id)] = cl
            if getattr(cl, "owner_user_id", None):
                owner_ids.append(int(cl.owner_user_id))

    user_ids = [int(c.uploaded_by) for c in rows if getattr(c, "uploaded_by", None)]
    user_names = _load_user_names(db, user_ids)
    owner_names = _load_user_names(db, owner_ids)
    needle = (q_text or "").strip().lower()
    out: List[Dict[str, Any]] = []
    for c in rows:
        client = clients_by_id.get(int(c.client_id)) if c.client_id else None
        ms = db.query(ContractMilestone).filter(ContractMilestone.contract_id == c.id).all()
        sales_owner = _resolve_sales_owner(db, handoffs, c, client, owner_names=owner_names)
        uploaded_by_name = user_names.get(int(c.uploaded_by), "") if getattr(c, "uploaded_by", None) else ""
        item = contract_to_dict(
            c,
            client.name if client else "",
            [milestone_to_dict(m) for m in ms],
            sales_owner=sales_owner,
            uploaded_by_name=uploaded_by_name,
        )
        if st and item.get("status") != st:
            continue
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
                    "contract_type_label",
                    "remarks",
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
    contract_type: str,
    contract_no: str,
    end_date: str,
    remarks: str,
    upload: UploadFile,
    upload_dir: str,
    max_file_size: int,
    allowed_suffixes: Set[str],
) -> Dict[str, Any]:
    t = str(title or "").strip()
    if not t:
        raise HTTPException(status_code=400, detail="请填写资料名称")

    ct = (contract_type or "").strip().lower()
    if ct not in CONTRACT_UPLOAD_TYPES:
        raise HTTPException(status_code=400, detail="无效的合同类型")

    effective_end_date = str(end_date or "").strip()
    # 空 end_date 表示长期有效（无固定期限）

    client = _validate_client(db, Client, client_id)
    client_name = str(client.name or "")

    if ct == "vendor":
        final_no = str(contract_no or "").strip()
        if not final_no:
            raise HTTPException(status_code=400, detail="供应商合同编号不能为空")
    else:
        final_no = generate_contract_no(
            db,
            Contract,
            client_id=int(client_id),
            client_name=client_name,
            contract_type=ct,
        )

    assert_contract_no_available(db, Contract, final_no)

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
        contract_no=final_no,
        contract_type=ct,
        title=t,
        end_date=effective_end_date,
        remarks=str(remarks or "").strip(),
        status="active",
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
        sales_owner=_client_sales_owner_name(db, client),
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


def update_contract_metadata(
    db: Session,
    Contract: Type[Any],
    Client: Type[Any],
    contract_id: int,
    *,
    title: str,
    client_id: int,
    contract_type: str,
    contract_no: str,
    end_date: str,
    remarks: str,
) -> Dict[str, Any]:
    row = _contract_row(db, Contract, contract_id)
    if getattr(row, "handoff_id", None):
        raise HTTPException(status_code=400, detail="交接生成的合同不可在此修改，请在交接单中调整")

    t = str(title or "").strip()
    if not t:
        raise HTTPException(status_code=400, detail="请填写资料名称")

    ct = (contract_type or "").strip().lower()
    if ct not in CONTRACT_UPLOAD_TYPES:
        raise HTTPException(status_code=400, detail="无效的合同类型")

    effective_end_date = str(end_date or "").strip()
    client = _validate_client(db, Client, client_id)

    if ct == "vendor":
        final_no = str(contract_no or "").strip()
        if not final_no:
            raise HTTPException(status_code=400, detail="供应商合同编号不能为空")
        assert_contract_no_available(db, Contract, final_no, exclude_id=contract_id)
    else:
        final_no = (row.contract_no or "").strip()

    row.client_id = int(client_id)
    row.contract_type = ct
    row.title = t
    row.contract_no = final_no
    row.end_date = effective_end_date
    row.remarks = str(remarks or "").strip()
    row.updated_at = datetime.now()
    db.commit()
    db.refresh(row)

    uploaded_by_name = ""
    if getattr(row, "uploaded_by", None):
        names = _load_user_names(db, [int(row.uploaded_by)])
        uploaded_by_name = names.get(int(row.uploaded_by), "")
    return contract_to_dict(
        row,
        client.name if client else "",
        [],
        sales_owner=_client_sales_owner_name(db, client),
        uploaded_by_name=uploaded_by_name,
    )


def clear_milestone_settlement_refs(
    db: Session,
    ContractMilestone: Type[Any],
    DeliverySettlementEntry: Type[Any],
    *,
    contract_id: int | None = None,
    settlement_entry_id: int | None = None,
) -> int:
    """Null milestone.settlement_entry_id when the settlement row is gone or on explicit delete."""
    q = db.query(ContractMilestone).filter(ContractMilestone.settlement_entry_id.isnot(None))
    if contract_id is not None:
        q = q.filter(ContractMilestone.contract_id == int(contract_id))
    if settlement_entry_id is not None:
        q = q.filter(ContractMilestone.settlement_entry_id == int(settlement_entry_id))
    cleared = 0
    for milestone in q.all():
        sid = int(milestone.settlement_entry_id)
        if settlement_entry_id is not None and sid == int(settlement_entry_id):
            milestone.settlement_entry_id = None
            cleared += 1
            continue
        exists = (
            db.query(DeliverySettlementEntry.id)
            .filter(DeliverySettlementEntry.id == sid)
            .first()
        )
        if not exists:
            milestone.settlement_entry_id = None
            cleared += 1
    return cleared


def _contract_has_active_settlement(
    db: Session,
    ContractMilestone: Type[Any],
    DeliverySettlementEntry: Type[Any],
    contract_id: int,
) -> bool:
    clear_milestone_settlement_refs(
        db,
        ContractMilestone,
        DeliverySettlementEntry,
        contract_id=contract_id,
    )
    db.flush()
    return (
        db.query(ContractMilestone.id)
        .filter(
            ContractMilestone.contract_id == contract_id,
            ContractMilestone.settlement_entry_id.isnot(None),
        )
        .first()
        is not None
    )


def delete_contract(
    db: Session,
    Contract: Type[Any],
    ContractMilestone: Type[Any],
    contract_id: int,
    *,
    upload_dir: str,
    DeliverySettlementEntry: Type[Any] | None = None,
) -> Dict[str, Any]:
    row = _contract_row(db, Contract, contract_id)
    if DeliverySettlementEntry is not None and _contract_has_active_settlement(
        db,
        ContractMilestone,
        DeliverySettlementEntry,
        contract_id,
    ):
        raise HTTPException(
            status_code=400,
            detail="该合同里程碑已预置结算，请先删除关联结算记录后再删合同",
        )
    elif DeliverySettlementEntry is None:
        seeded = (
            db.query(ContractMilestone.id)
            .filter(
                ContractMilestone.contract_id == contract_id,
                ContractMilestone.settlement_entry_id.isnot(None),
            )
            .first()
        )
        if seeded:
            raise HTTPException(
                status_code=400,
                detail="该合同里程碑已预置结算，请先删除关联结算记录后再删合同",
            )

    stored_path = (getattr(row, "stored_path", None) or "").strip()
    if stored_path:
        try:
            abs_path = sec.resolve_upload_path(upload_dir, stored_path)
            if os.path.isfile(abs_path):
                os.remove(abs_path)
        except (ValueError, OSError):
            pass

    db.query(ContractMilestone).filter(ContractMilestone.contract_id == contract_id).delete()
    db.delete(row)
    db.commit()
    return {"ok": True}


def download_contract_file(
    db: Session,
    Contract: Type[Any],
    contract_id: int,
    *,
    upload_dir: str,
):
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


def preview_contract_file(
    db: Session,
    Contract: Type[Any],
    contract_id: int,
    *,
    upload_dir: str,
):
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

    file_name = (getattr(row, "file_name", None) or "").strip() or os.path.basename(abs_path)
    ext = _file_ext(file_name)
    if ext in MATERIAL_PREVIEWABLE_SUFFIXES:
        media_type = _MEDIA_TYPE_BY_EXT.get(ext, "application/octet-stream")
        return FileResponse(
            abs_path,
            media_type=media_type,
            filename=file_name,
            content_disposition_type="inline",
        )
    if ext in MATERIAL_OFFICE_CONVERT_SUFFIXES:
        try:
            pdf_abs = convert_office_to_preview_pdf(
                source_abs=abs_path,
                upload_dir=upload_dir,
                material_id=int(row.id),
                updated_at=getattr(row, "updated_at", None),
            )
        except MaterialPreviewConversionError:
            raise HTTPException(status_code=400, detail=MATERIAL_PREVIEW_CONVERSION_FAILED_MSG)
        stem = os.path.splitext(file_name)[0] or "preview"
        return FileResponse(
            pdf_abs,
            media_type="application/pdf",
            filename=f"{stem}.pdf",
            content_disposition_type="inline",
        )
    raise HTTPException(status_code=400, detail=MATERIAL_PREVIEW_UNSUPPORTED_MSG)
