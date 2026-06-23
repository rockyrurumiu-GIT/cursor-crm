"""Delivery employee file API routes."""
from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Tuple, Type

from fastapi import Body, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import desc
from sqlalchemy.orm import Session

import security_foundation as sec
from auth import data_scope as ds
from auth.data_scope_catalog import RESOURCE_DELIVERY_EMPLOYEE_FILES
from auth.deps import get_current_context, require_permission
from auth.service import AuthContext
from schemas.delivery_employee_files import (
    EMPLOYEE_FILE_ALLOWED_SUFFIXES,
    EMPLOYEE_FILE_STATUS_SET,
    LABOR_CONTRACT_DOCUMENT_TYPE,
)
from services.delivery_employee_files import (
    employee_file_client_dir_rel,
    employee_file_normalize_status,
    employee_file_row_to_dict,
    is_labor_contract_row,
    labor_contract_delete_is_hard,
    prepare_labor_contract_upload,
    safe_employee_file_filename,
)
from services.delivery_handbook import handbook_suffix_to_media_kind


def register_delivery_employee_file_routes(
    app,
    *,
    get_db: Callable,
    Client: Type,
    DeliveryEmployeeFile: Type,
    RosterEntry: Type,
    AuditLog: Type,
    upload_dir: str,
    max_file_size: int,
):
    def _row_to_dict(r):
        return employee_file_row_to_dict(r, sec.file_access_url)

    def _cleanup_written_paths(paths: List[str]) -> None:
        for sp in paths:
            try:
                abs_path = sec.resolve_upload_path(upload_dir, sp)
                if os.path.isfile(abs_path):
                    os.remove(abs_path)
            except (ValueError, OSError):
                pass

    async def _read_and_validate_uploads(
        files: List[UploadFile],
    ) -> List[Tuple[str, str, bytes, str]]:
        payloads: List[Tuple[str, str, bytes, str]] = []
        for up in files:
            raw_name = up.filename or ""
            ext = os.path.splitext(raw_name)[1].lower()
            if ext not in EMPLOYEE_FILE_ALLOWED_SUFFIXES:
                display_name = raw_name or "（未命名）"
                raise HTTPException(
                    status_code=400,
                    detail=f"不支持的文件类型：{display_name}，允许：PDF、Word、Excel、图片、压缩包",
                )
            content_bytes = await up.read()
            if len(content_bytes) > max_file_size:
                oversize_name = raw_name or "未命名"
                raise HTTPException(status_code=400, detail=f"文件超过20MB限制：{oversize_name}")
            safe = safe_employee_file_filename(raw_name)
            if not os.path.splitext(safe)[1]:
                safe = safe + ext
            payloads.append((raw_name, ext, content_bytes, safe))
        return payloads

    @app.get("/api/clients/{client_id}/delivery/employee-files")
    async def list_delivery_employee_files(
        client_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("delivery.employee_files.read")),
    ):
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        ds.assert_client_in_scope(
            db, ctx, client_id, Client, RESOURCE_DELIVERY_EMPLOYEE_FILES, "read"
        )
        rows = (
            db.query(DeliveryEmployeeFile)
            .filter(DeliveryEmployeeFile.client_id == client_id)
            .order_by(desc(DeliveryEmployeeFile.created_at))
            .all()
        )
        return [_row_to_dict(r) for r in rows]

    @app.post("/api/clients/{client_id}/delivery/employee-files")
    async def upload_delivery_employee_files(
        client_id: int,
        files: List[UploadFile] = File(default=[]),
        status: str = Form(default="draft"),
        document_type: str = Form(default=""),
        employee_full_name: str = Form(default=""),
        employee_contact_info: str = Form(default=""),
        contract_sign_date: str = Form(default=""),
        contract_valid_until: str = Form(default=""),
        confirm_same_year_renewal: int = Form(default=0),
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("delivery.employee_files.write")),
    ):
        if not files:
            raise HTTPException(status_code=400, detail="请选择文件")
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="客户不存在")
        ds.assert_client_in_scope(
            db, ctx, client_id, Client, RESOURCE_DELIVERY_EMPLOYEE_FILES, "write"
        )

        doc_type = str(document_type or "").strip()
        is_labor = doc_type == LABOR_CONTRACT_DOCUMENT_TYPE
        lc_ctx: Dict[str, Any] | None = None

        if is_labor:
            if len(files) != 1:
                raise HTTPException(status_code=400, detail="劳动合同每次只能上传 1 个文件")
            if not str(employee_full_name or "").strip():
                raise HTTPException(status_code=400, detail="请填写员工姓名")
            if not str(employee_contact_info or "").strip():
                raise HTTPException(status_code=400, detail="请填写手机号")
            lc_ctx = prepare_labor_contract_upload(
                db,
                client_id=client_id,
                employee_full_name=employee_full_name,
                employee_contact_info=employee_contact_info,
                contract_sign_date=contract_sign_date,
                contract_valid_until=contract_valid_until,
                confirm_same_year_renewal=confirm_same_year_renewal,
                RosterEntry=RosterEntry,
                DeliveryEmployeeFile=DeliveryEmployeeFile,
            )

        try:
            file_payloads = await _read_and_validate_uploads(files)
        except HTTPException:
            raise

        rel_dir = employee_file_client_dir_rel(client)
        abs_dir = sec.resolve_upload_path(upload_dir, rel_dir)
        os.makedirs(abs_dir, exist_ok=True)
        ts_base = int(time.time() * 1000000)
        st = employee_file_normalize_status(status or "draft")
        saved: List = []
        written_paths: List[str] = []
        now = datetime.now()
        try:
            for idx, (raw_name, ext, content_bytes, safe) in enumerate(file_payloads):
                stored_rel = f"{rel_dir}/{ts_base}_{idx}_{safe}"
                try:
                    abs_target = sec.resolve_upload_path(upload_dir, stored_rel)
                except ValueError:
                    raise HTTPException(status_code=400, detail="非法文件路径")
                with open(abs_target, "wb") as f:
                    f.write(content_bytes)
                written_paths.append(stored_rel)
                mk = handbook_suffix_to_media_kind(ext)
                row_kwargs: Dict[str, Any] = {
                    "client_id": client_id,
                    "original_filename": raw_name or safe,
                    "stored_path": stored_rel,
                    "status": st,
                    "media_kind": mk,
                    "updated_at": now,
                }
                if is_labor and lc_ctx:
                    row_kwargs.update(lc_ctx)
                elif doc_type:
                    row_kwargs["document_type"] = doc_type
                row = DeliveryEmployeeFile(**row_kwargs)
                db.add(row)
                saved.append(row)
            db.commit()
        except Exception:
            db.rollback()
            _cleanup_written_paths(written_paths)
            raise

        for row in saved:
            db.refresh(row)
            label = row.original_filename or ("#" + str(row.id))
            if is_labor and getattr(row, "labor_contract_no", None):
                label = row.labor_contract_no
            db.add(
                AuditLog(
                    client_id=client_id,
                    operator=user,
                    action=f"员工文件上传: {label}",
                )
            )
        db.commit()
        return [_row_to_dict(r) for r in saved]

    @app.patch("/api/clients/{client_id}/delivery/employee-files/{row_id}")
    async def patch_delivery_employee_file(
        client_id: int,
        row_id: int,
        body: Dict[str, Any] = Body(default={}),
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("delivery.employee_files.write")),
    ):
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        ds.assert_client_in_scope(
            db, ctx, client_id, Client, RESOURCE_DELIVERY_EMPLOYEE_FILES, "write"
        )
        row = (
            db.query(DeliveryEmployeeFile)
            .filter(
                DeliveryEmployeeFile.id == row_id,
                DeliveryEmployeeFile.client_id == client_id,
            )
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail="记录不存在")
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="无效请求体")
        if "status" in body:
            st = str(body.get("status") or "").strip().lower()
            if st not in EMPLOYEE_FILE_STATUS_SET:
                raise HTTPException(status_code=400, detail="无效状态")
            row.status = st
        row.updated_at = datetime.now()
        db.commit()
        db.refresh(row)
        db.add(AuditLog(client_id=client_id, operator=user, action=f"员工文件修改 id={row_id}"))
        db.commit()
        return _row_to_dict(row)

    @app.delete("/api/clients/{client_id}/delivery/employee-files/{row_id}")
    async def delete_delivery_employee_file(
        client_id: int,
        row_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("delivery.employee_files.delete")),
    ):
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        ds.assert_client_in_scope(
            db, ctx, client_id, Client, RESOURCE_DELIVERY_EMPLOYEE_FILES, "delete"
        )
        row = (
            db.query(DeliveryEmployeeFile)
            .filter(
                DeliveryEmployeeFile.id == row_id,
                DeliveryEmployeeFile.client_id == client_id,
            )
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail="记录不存在")

        label = (row.original_filename or f"#{row_id}").strip()
        if is_labor_contract_row(row):
            label = (row.labor_contract_no or label).strip()

        if labor_contract_delete_is_hard(row):
            sp = (row.stored_path or "").strip()
            if sp:
                try:
                    abs_path = sec.resolve_upload_path(upload_dir, sp)
                    if os.path.isfile(abs_path):
                        os.remove(abs_path)
                except (ValueError, OSError):
                    pass
            db.delete(row)
            db.add(
                AuditLog(
                    client_id=client_id,
                    operator=user,
                    action=f"员工文件删除(草稿劳动合同): {label}",
                )
            )
            db.commit()
            return {"status": "ok"}

        if is_labor_contract_row(row):
            row.status = "deprecated"
            row.updated_at = datetime.now()
            db.add(AuditLog(client_id=client_id, operator=user, action=f"员工文件作废: {label}"))
            db.commit()
            return {"status": "ok"}

        sp = (row.stored_path or "").strip()
        if sp:
            try:
                abs_path = sec.resolve_upload_path(upload_dir, sp)
                if os.path.isfile(abs_path):
                    os.remove(abs_path)
            except (ValueError, OSError):
                pass
        db.delete(row)
        db.add(AuditLog(client_id=client_id, operator=user, action=f"员工文件删除: {label}"))
        db.commit()
        return {"status": "ok"}
