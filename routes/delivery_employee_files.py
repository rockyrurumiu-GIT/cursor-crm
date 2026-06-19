"""Delivery employee file API routes."""
from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Type

from fastapi import Body, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import desc
from sqlalchemy.orm import Session

import security_foundation as sec
from auth.deps import require_permission
from schemas.delivery_employee_files import EMPLOYEE_FILE_ALLOWED_SUFFIXES, EMPLOYEE_FILE_STATUS_SET
from services.delivery_employee_files import (
    employee_file_client_dir_rel,
    employee_file_normalize_status,
    employee_file_row_to_dict,
    safe_employee_file_filename,
)
from services.delivery_handbook import handbook_suffix_to_media_kind


def register_delivery_employee_file_routes(
    app,
    *,
    get_db: Callable,
    Client: Type,
    DeliveryEmployeeFile: Type,
    AuditLog: Type,
    upload_dir: str,
    max_file_size: int,
):
    def _row_to_dict(r):
        return employee_file_row_to_dict(r, sec.file_access_url)

    @app.get("/api/clients/{client_id}/delivery/employee-files")
    async def list_delivery_employee_files(
        client_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.employee_files.read")),
    ):
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
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
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.employee_files.write")),
    ):
        if not files:
            raise HTTPException(status_code=400, detail="请选择文件")
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="客户不存在")
        rel_dir = employee_file_client_dir_rel(client)
        abs_dir = sec.resolve_upload_path(upload_dir, rel_dir)
        os.makedirs(abs_dir, exist_ok=True)
        ts_base = int(time.time() * 1000000)
        st = employee_file_normalize_status(status or "draft")
        saved: List = []
        now = datetime.now()
        for idx, up in enumerate(files):
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
            stored_rel = f"{rel_dir}/{ts_base}_{idx}_{safe}"
            try:
                abs_target = sec.resolve_upload_path(upload_dir, stored_rel)
            except ValueError:
                raise HTTPException(status_code=400, detail="非法文件路径")
            with open(abs_target, "wb") as f:
                f.write(content_bytes)
            mk = handbook_suffix_to_media_kind(ext)
            row = DeliveryEmployeeFile(
                client_id=client_id,
                original_filename=raw_name or safe,
                stored_path=stored_rel,
                status=st,
                media_kind=mk,
                updated_at=now,
            )
            db.add(row)
            saved.append(row)
        db.commit()
        for row in saved:
            db.refresh(row)
            db.add(
                AuditLog(
                    client_id=client_id,
                    operator=user,
                    action=f"员工文件上传: {row.original_filename or ('#' + str(row.id))}",
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
        user: str = Depends(require_permission("delivery.employee_files.write")),
    ):
        row = db.query(DeliveryEmployeeFile).filter(DeliveryEmployeeFile.id == row_id).first()
        if not row or row.client_id != client_id:
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
        user: str = Depends(require_permission("delivery.employee_files.delete")),
    ):
        row = db.query(DeliveryEmployeeFile).filter(DeliveryEmployeeFile.id == row_id).first()
        if not row or row.client_id != client_id:
            raise HTTPException(status_code=404, detail="记录不存在")
        sp = (row.stored_path or "").strip()
        if sp:
            try:
                abs_path = sec.resolve_upload_path(upload_dir, sp)
                if os.path.isfile(abs_path):
                    os.remove(abs_path)
            except (ValueError, OSError):
                pass
        name = row.original_filename or f"#{row_id}"
        db.delete(row)
        db.add(AuditLog(client_id=client_id, operator=user, action=f"员工文件删除: {name}"))
        db.commit()
        return {"status": "ok"}
