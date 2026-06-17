"""Client API routes — migrated from main.py (Phase 3A read, Phase 3B write)."""
from __future__ import annotations

import csv
import io
import os
import shutil
import time
from datetime import datetime
from typing import Callable, List, Optional, Union

from fastapi import Depends, Form, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from auth import data_scope as ds
from auth import deps as auth_deps
from auth.data_scope_catalog import RESOURCE_CRM_CLIENT
from auth.deps import get_current_context, require_permission
from auth.service import AuthContext
from phase2_core import CONTACT_ACQUISITION_CHANNELS
from services.clients import ensure_client_access, scoped_client_query


def _parse_handoff_status_filter(raw: Optional[Union[str, List[str]]]) -> set[str]:
    """多选交接状态：任一命中即保留（OR）。"""
    statuses: set[str] = set()
    if not raw:
        return statuses
    items = raw if isinstance(raw, list) else [raw]
    for item in items:
        for part in str(item).split(","):
            t = part.strip()
            if t:
                statuses.add(t)
    return statuses


def _normalize_contact_channel(raw: Optional[str]) -> str:
    channel = (raw or "").strip()
    if channel and channel not in CONTACT_ACQUISITION_CHANNELS:
        raise HTTPException(status_code=400, detail="获客渠道须为：个人、公司、其他")
    return channel


def _parse_optional_int(raw: Optional[str]) -> Optional[int]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的数值参数")


def _dept_label(db: Session, dept_id: Optional[int]) -> str:
    if not dept_id:
        return ""
    from sqlalchemy import text

    row = db.execute(
        text("SELECT name, code FROM sys_dept WHERE id = :id"), {"id": dept_id}
    ).fetchone()
    if not row:
        return str(dept_id)
    name, code = str(row[0] or ""), str(row[1] or "")
    return name or code or str(dept_id)


def _user_display_name(db: Session, user_id: Optional[int]) -> str:
    """Short display name for legacy Client.owner text field."""
    if not user_id:
        return ""
    from sqlalchemy import text

    row = db.execute(
        text("SELECT display_name, username FROM sys_user WHERE id = :id"), {"id": user_id}
    ).fetchone()
    if not row:
        return str(user_id)
    return str(row[0] or row[1] or user_id).strip()


def _user_label(db: Session, user_id: Optional[int]) -> str:
    if not user_id:
        return ""
    from sqlalchemy import text

    row = db.execute(
        text("SELECT display_name, username FROM sys_user WHERE id = :id"), {"id": user_id}
    ).fetchone()
    if not row:
        return str(user_id)
    display = str(row[0] or row[1] or user_id)
    username = str(row[1] or row[0] or user_id)
    return f"{display} · {username}"


def _serialize_client(db: Session, client) -> dict:
    from fastapi.encoders import jsonable_encoder

    d = jsonable_encoder(client)
    sales_dept_id = d.get("owner_dept_id")
    if sales_dept_id is None:
        sales_dept_id = getattr(client, "owner_dept_id", None)
    sales_user_id = d.get("owner_user_id")
    if sales_user_id is None:
        sales_user_id = getattr(client, "owner_user_id", None)
    d["owner_dept_id"] = sales_dept_id
    d["owner_user_id"] = sales_user_id
    d["owner_dept_label"] = _dept_label(db, sales_dept_id) if sales_dept_id else ""
    d["owner_user_label"] = _user_label(db, sales_user_id) if sales_user_id else ""
    dept_id = d.get("delivery_dept_id")
    if dept_id is None:
        dept_id = getattr(client, "delivery_dept_id", None)
    owner_id = d.get("delivery_owner_user_id")
    if owner_id is None:
        owner_id = getattr(client, "delivery_owner_user_id", None)
    d["delivery_dept_id"] = dept_id
    d["delivery_owner_user_id"] = owner_id
    d["delivery_dept_label"] = _dept_label(db, dept_id) if dept_id else ""
    d["delivery_owner_label"] = _user_label(db, owner_id) if owner_id else ""
    rec_dept_id = d.get("recruitment_dept_id")
    if rec_dept_id is None:
        rec_dept_id = getattr(client, "recruitment_dept_id", None)
    rec_owner_id = d.get("recruitment_owner_user_id")
    if rec_owner_id is None:
        rec_owner_id = getattr(client, "recruitment_owner_user_id", None)
    d["recruitment_dept_id"] = rec_dept_id
    d["recruitment_owner_user_id"] = rec_owner_id
    d["recruitment_dept_label"] = _dept_label(db, rec_dept_id) if rec_dept_id else ""
    d["recruitment_owner_label"] = _user_label(db, rec_owner_id) if rec_owner_id else ""
    return d


def register_client_read_routes(
    app,
    *,
    get_db: Callable,
    Client,
    Opportunity,
    HandoffRequest,
    CrmNotification,
    trash_dir: str,
    set_csv_download_headers: Callable,
):
    @app.get("/api/stats")
    async def get_stats(
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.clients.read")),
    ):
        phases = ["\u521d\u6b65\u63a5\u89e6", "\u65b9\u6848/\u62a5\u4ef7", "\u5408\u540c\u7b7e\u8ba2", "\u6210\u4ea4"]
        stats = {
            p: scoped_client_query(db, ctx, Client, action="read").filter(Client.phase == p).count()
            for p in phases
        }

        trash_count = 0
        trash_size = 0
        if os.path.exists(trash_dir):
            for f in os.listdir(trash_dir):
                fp = os.path.join(trash_dir, f)
                trash_count += 1
                trash_size += os.path.getsize(fp)

        handoff_pending = db.query(HandoffRequest).filter(HandoffRequest.status == "pending_review").count()
        handoff_rejected = db.query(HandoffRequest).filter(HandoffRequest.status == "rejected").count()
        handoff_approved = db.query(HandoffRequest).filter(HandoffRequest.status == "approved").count()
        notifications_unread = (
            db.query(CrmNotification)
            .filter(CrmNotification.username == user, CrmNotification.read_at.is_(None))
            .count()
        )

        return {
            "funnel": stats,
            "trash": {"count": trash_count, "size": f"{trash_size/1024/1024:.2f} MB"},
            "handoff": {
                "pending_review": handoff_pending,
                "rejected": handoff_rejected,
                "approved": handoff_approved,
            },
            "notifications_unread": notifications_unread,
        }

    @app.get("/api/clients")
    async def list_clients(
        phase: Optional[str] = None,
        handoff_status: Optional[List[str]] = Query(None),
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(auth_deps.require_permission("crm.clients.read")),
    ):
        from handoff_core import resolve_client_handoff_status
        from phase2_core import refresh_client_estimated_annual_amount

        query = scoped_client_query(db, ctx, Client, action="read")
        if phase:
            query = query.filter(Client.phase == phase)
        clients = query.order_by(desc(Client.created_at)).all()
        for c in clients:
            refresh_client_estimated_annual_amount(db, c.id, Client, Opportunity)
        db.commit()
        for c in clients:
            db.refresh(c)
        statuses = _parse_handoff_status_filter(handoff_status)
        if not statuses:
            return [_serialize_client(db, c) for c in clients]
        out = []
        for c in clients:
            latest = (
                db.query(HandoffRequest)
                .filter(HandoffRequest.client_id == c.id, HandoffRequest.status != "superseded")
                .order_by(desc(HandoffRequest.version), desc(HandoffRequest.id))
                .first()
            )
            cur = resolve_client_handoff_status(latest)
            # OR：待审 / 草稿 / 未提交等任一命中即展示
            if cur in statuses:
                out.append(c)
        return [_serialize_client(db, c) for c in out]

    @app.get("/api/clients/assign-options")
    async def client_assign_options(
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("crm.clients.read")),
    ):
        from sqlalchemy import text

        depts = db.execute(
            text(
                "SELECT id, name, code, parent_id, path, dept_type, status "
                "FROM sys_dept WHERE status = 'active' ORDER BY path"
            )
        ).mappings().all()
        users = db.execute(
            text(
                "SELECT id, username, display_name FROM sys_user "
                "WHERE status = 'active' ORDER BY username"
            )
        ).mappings().all()
        return {
            "depts": [dict(r) for r in depts],
            "users": [
                {
                    "id": int(r["id"]),
                    "username": str(r["username"]),
                    "display_name": str(r["display_name"] or r["username"]),
                }
                for r in users
            ],
            "defaults": {
                "owner_dept_id": ctx.primary_dept_id,
                "owner_user_id": ctx.user_id,
            },
        }

    @app.get("/api/clients/{client_id}")
    async def get_client(
        client_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.clients.read")),
    ):
        from phase2_core import refresh_client_estimated_annual_amount

        client = ensure_client_access(db, ctx, client_id, Client, action="read")
        refresh_client_estimated_annual_amount(db, client_id, Client, Opportunity)
        db.commit()
        db.refresh(client)
        return _serialize_client(db, client)

    @app.get("/api/export/clients")
    async def export_clients(
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.clients.write")),
    ):
        from phase2_core import refresh_client_estimated_annual_amount

        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output)
        writer.writerow([
            "ID", "\u5ba2\u6237\u540d\u79f0", "\u884c\u4e1a", "\u8d1f\u8d23\u4eba", "\u5916\u5305\u89c4\u6a21", "\u5f00\u62d3\u9636\u6bb5",
            "\u9884\u4f30\u5f53\u5e74\u5408\u4f5c\u91d1\u989d(\u4e07\u5143)", "\u8054\u7cfb\u4eba\u59d3\u540d", "\u8054\u7cfb\u65b9\u5f0f", "\u8054\u7cfb\u4eba\u804c\u4f4d", "\u8054\u7cfb\u4eba\u5173\u7cfb", "\u5ba2\u6237\u6240\u5728\u57ce\u5e02",
            "\u521b\u5efa\u65f6\u95f4",
        ])
        clients = scoped_client_query(db, ctx, Client, action="export").all()
        for c in clients:
            refresh_client_estimated_annual_amount(db, c.id, Client, Opportunity)
        db.commit()
        for c in clients:
            db.refresh(c)
            writer.writerow([
                c.id, c.name, c.industry, c.owner, c.scale, c.phase,
                c.estimated_annual_amount or "",
                c.contact_name or "", c.contact_info or "", c.contact_title or "",
                c.contact_relationship or "", c.city or "",
                c.created_at.strftime("%Y-%m-%d"),
            ])

        response = StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        set_csv_download_headers(
            response,
            chinese_filename=f"\u5ba2\u6237\u5217\u8868_{ts}.csv",
            ascii_base=f"clients_{ts}",
        )
        return response


def register_client_write_routes(
    app,
    *,
    get_db: Callable,
    Client,
    Contact,
    Opportunity,
    AuditLog,
    VisitRecord,
    DeliveryHandbookFile,
    upload_dir: str,
    trash_dir: str,
    sync_primary_contact: Callable,
):
    @app.post("/api/clients")
    async def create_client(
        name: str = Form(...),
        industry: str = Form(...),
        owner: str = Form(...),
        scale: str = Form(...),
        phase: str = Form(...),
        description: str = Form(...),
        contact_name: Optional[str] = Form(None),
        contact_info: Optional[str] = Form(None),
        contact_title: Optional[str] = Form(None),
        contact_relationship: Optional[str] = Form(None),
        contact_acquisition_channel: Optional[str] = Form(None),
        contact_superior_contact: Optional[str] = Form(None),
        contact_description: Optional[str] = Form(None),
        city: Optional[str] = Form(None),
        remarks: Optional[str] = Form(None),
        owner_dept_id: Optional[str] = Form(None),
        owner_user_id: Optional[str] = Form(None),
        delivery_dept_id: Optional[str] = Form(None),
        delivery_owner_user_id: Optional[str] = Form(None),
        recruitment_dept_id: Optional[str] = Form(None),
        recruitment_owner_user_id: Optional[str] = Form(None),
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.clients.write")),
    ):
        ds.assert_data_scope(ctx, RESOURCE_CRM_CLIENT, "write")
        sales_dept = _parse_optional_int(owner_dept_id)
        sales_user = _parse_optional_int(owner_user_id)
        owner_fields = ds.default_owner_fields(ctx)
        if sales_dept is not None:
            owner_fields["owner_dept_id"] = sales_dept
        if sales_user is not None:
            owner_fields["owner_user_id"] = sales_user
        owner_display = (owner or "").strip() or _user_display_name(db, owner_fields.get("owner_user_id"))
        delivery_dept = _parse_optional_int(delivery_dept_id)
        delivery_owner = _parse_optional_int(delivery_owner_user_id)
        recruitment_dept = _parse_optional_int(recruitment_dept_id)
        recruitment_owner = _parse_optional_int(recruitment_owner_user_id)
        client = Client(
            name=name,
            industry=industry,
            owner=owner_display,
            scale=scale,
            phase=phase,
            description=description,
            estimated_annual_amount="",
            contact_name=(contact_name or "").strip(),
            contact_info=(contact_info or "").strip(),
            contact_title=(contact_title or "").strip(),
            contact_relationship=(contact_relationship or "").strip(),
            contact_acquisition_channel=_normalize_contact_channel(contact_acquisition_channel),
            contact_superior_contact=(contact_superior_contact or "").strip(),
            contact_description=(contact_description or "").strip(),
            city=(city or "").strip(),
            remarks=(remarks or "").strip(),
            delivery_dept_id=delivery_dept,
            delivery_owner_user_id=delivery_owner,
            recruitment_dept_id=recruitment_dept,
            recruitment_owner_user_id=recruitment_owner,
            **owner_fields,
        )
        db.add(client)
        db.commit()
        db.refresh(client)
        sync_primary_contact(db, client)
        log = AuditLog(client_id=client.id, operator=user, action=f"\u521b\u5efa\u4e86\u5ba2\u6237: {name}")
        db.add(log)
        db.commit()
        db.refresh(client)
        return client

    @app.put("/api/clients/{client_id}")
    async def update_client(
        client_id: int,
        name: str = Form(...),
        industry: str = Form(...),
        owner: str = Form(...),
        scale: str = Form(...),
        phase: str = Form(...),
        description: str = Form(...),
        contact_name: Optional[str] = Form(None),
        contact_info: Optional[str] = Form(None),
        contact_title: Optional[str] = Form(None),
        contact_relationship: Optional[str] = Form(None),
        contact_acquisition_channel: Optional[str] = Form(None),
        contact_superior_contact: Optional[str] = Form(None),
        contact_description: Optional[str] = Form(None),
        city: Optional[str] = Form(None),
        remarks: Optional[str] = Form(None),
        owner_dept_id: Optional[str] = Form(None),
        owner_user_id: Optional[str] = Form(None),
        delivery_dept_id: Optional[str] = Form(None),
        delivery_owner_user_id: Optional[str] = Form(None),
        recruitment_dept_id: Optional[str] = Form(None),
        recruitment_owner_user_id: Optional[str] = Form(None),
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.clients.write")),
    ):
        from phase2_core import refresh_client_estimated_annual_amount

        client = ensure_client_access(db, ctx, client_id, Client, action="write")
        sales_dept = _parse_optional_int(owner_dept_id)
        sales_user = _parse_optional_int(owner_user_id)
        owner_display = (owner or "").strip() or _user_display_name(db, sales_user)
        delivery_dept = _parse_optional_int(delivery_dept_id)
        delivery_owner = _parse_optional_int(delivery_owner_user_id)
        recruitment_dept = _parse_optional_int(recruitment_dept_id)
        recruitment_owner = _parse_optional_int(recruitment_owner_user_id)
        duplicate = scoped_client_query(db, ctx, Client, action="write").filter(Client.name == name, Client.id != client_id).first()
        if duplicate:
            raise HTTPException(status_code=400, detail="\u5ba2\u6237\u540d\u79f0\u5df2\u5b58\u5728")

        old_name = client.name or ""
        updates = []
        if old_name != name:
            updates.append(f"\u5ba2\u6237\u540d\u79f0\u4ece[{old_name}]\u53d8\u66f4\u4e3a[{name}]")
        if client.industry != industry:
            updates.append(f"\u884c\u4e1a\u4ece[{client.industry}]\u53d8\u66f4\u4e3a[{industry}]")
        if client.owner != owner_display:
            updates.append(f"\u9500\u552e\u4e3b\u8d23\u4ece[{client.owner}]\u53d8\u66f4\u4e3a[{owner_display}]")
        if getattr(client, "owner_dept_id", None) != sales_dept:
            updates.append(
                f"\u9500\u552e\u90e8\u95e8\u4ece[{_dept_label(db, getattr(client, 'owner_dept_id', None)) or '—'}]"
                f"\u53d8\u66f4\u4e3a[{_dept_label(db, sales_dept) or '—'}]"
            )
        if getattr(client, "owner_user_id", None) != sales_user:
            updates.append(
                f"\u9500\u552e\u4e3b\u8d23\u4eba\u4ece[{_user_label(db, getattr(client, 'owner_user_id', None)) or '—'}]"
                f"\u53d8\u66f4\u4e3a[{_user_label(db, sales_user) or '—'}]"
            )
        if client.scale != scale:
            updates.append(f"\u5916\u5305\u89c4\u6a21\u4ece[{client.scale}]\u53d8\u66f4\u4e3a[{scale}]")
        if client.phase != phase:
            updates.append(f"\u9636\u6bb5\u4ece[{client.phase}]\u53d8\u66f4\u4e3a[{phase}]")
        if client.description != description:
            updates.append("\u66f4\u65b0\u4e86\u5ba2\u6237\u63cf\u8ff0")
        if (client.remarks or "") != (remarks or ""):
            updates.append("\u66f4\u65b0\u4e86\u5907\u6ce8\u4fe1\u606f")
        new_contact_name = (contact_name or "").strip()
        new_contact_info = (contact_info or "").strip()
        new_contact_title = (contact_title or "").strip()
        new_contact_relationship = (contact_relationship or "").strip()
        new_contact_acquisition_channel = _normalize_contact_channel(contact_acquisition_channel)
        new_contact_superior_contact = (contact_superior_contact or "").strip()
        new_contact_description = (contact_description or "").strip()
        new_city = (city or "").strip()
        if (client.contact_name or "") != new_contact_name:
            updates.append(f"\u8054\u7cfb\u4eba\u59d3\u540d\u4ece[{client.contact_name or ''}]\u53d8\u66f4\u4e3a[{new_contact_name}]")
        if (client.contact_info or "") != new_contact_info:
            updates.append("\u66f4\u65b0\u4e86\u8054\u7cfb\u65b9\u5f0f")
        if (client.contact_title or "") != new_contact_title:
            updates.append(f"\u8054\u7cfb\u4eba\u804c\u4f4d\u4ece[{client.contact_title or ''}]\u53d8\u66f4\u4e3a[{new_contact_title}]")
        if (client.contact_relationship or "") != new_contact_relationship:
            updates.append(f"\u8054\u7cfb\u4eba\u5173\u7cfb\u4ece[{client.contact_relationship or ''}]\u53d8\u66f4\u4e3a[{new_contact_relationship}]")
        if (client.city or "") != new_city:
            updates.append(f"\u5ba2\u6237\u6240\u5728\u57ce\u5e02\u4ece[{client.city or ''}]\u53d8\u66f4\u4e3a[{new_city}]")
        if getattr(client, "delivery_dept_id", None) != delivery_dept:
            updates.append(
                f"\u4ea4\u4ed8\u90e8\u95e8\u4ece[{_dept_label(db, getattr(client, 'delivery_dept_id', None)) or '—'}]"
                f"\u53d8\u66f4\u4e3a[{_dept_label(db, delivery_dept) or '—'}]"
            )
        if getattr(client, "delivery_owner_user_id", None) != delivery_owner:
            updates.append(
                f"\u4ea4\u4ed8\u8d1f\u8d23\u4eba\u4ece[{_user_label(db, getattr(client, 'delivery_owner_user_id', None)) or '—'}]"
                f"\u53d8\u66f4\u4e3a[{_user_label(db, delivery_owner) or '—'}]"
            )
        if getattr(client, "recruitment_dept_id", None) != recruitment_dept:
            updates.append(
                f"\u62db\u8058\u90e8\u95e8\u4ece[{_dept_label(db, getattr(client, 'recruitment_dept_id', None)) or '—'}]"
                f"\u53d8\u66f4\u4e3a[{_dept_label(db, recruitment_dept) or '—'}]"
            )
        if getattr(client, "recruitment_owner_user_id", None) != recruitment_owner:
            updates.append(
                f"\u62db\u8058\u8d1f\u8d23\u4eba\u4ece[{_user_label(db, getattr(client, 'recruitment_owner_user_id', None)) or '—'}]"
                f"\u53d8\u66f4\u4e3a[{_user_label(db, recruitment_owner) or '—'}]"
            )

        client.name = name
        client.industry = industry
        client.owner = owner_display
        client.owner_dept_id = sales_dept
        client.owner_user_id = sales_user
        client.scale = scale
        client.phase = phase
        client.description = description
        client.contact_name = new_contact_name
        client.contact_info = new_contact_info
        client.contact_title = new_contact_title
        client.contact_relationship = new_contact_relationship
        client.contact_acquisition_channel = new_contact_acquisition_channel
        client.contact_superior_contact = new_contact_superior_contact
        client.contact_description = new_contact_description
        client.city = new_city
        client.remarks = remarks or ""
        client.delivery_dept_id = delivery_dept
        client.delivery_owner_user_id = delivery_owner
        client.recruitment_dept_id = recruitment_dept
        client.recruitment_owner_user_id = recruitment_owner

        old_folder = f"{old_name}_{client_id}"
        new_folder = f"{name}_{client_id}"
        src_path = os.path.join(upload_dir, old_folder)
        dst_path = os.path.join(upload_dir, new_folder)
        if old_folder != new_folder and os.path.exists(src_path) and not os.path.exists(dst_path):
            shutil.move(src_path, dst_path)
            visits = db.query(VisitRecord).filter(VisitRecord.client_id == client_id).all()
            for visit in visits:
                if visit.attachment and visit.attachment.startswith(f"{old_folder}/"):
                    visit.attachment = visit.attachment.replace(f"{old_folder}/", f"{new_folder}/", 1)

            old_hb_prefix = f"handbooks/{old_folder}/"
            new_hb_prefix = f"handbooks/{new_folder}/"
            old_hb_dir = os.path.join(upload_dir, "handbooks", old_folder)
            new_hb_dir = os.path.join(upload_dir, "handbooks", new_folder)
            if old_folder != new_folder and os.path.isdir(old_hb_dir) and not os.path.exists(new_hb_dir):
                os.makedirs(os.path.join(upload_dir, "handbooks"), exist_ok=True)
                shutil.move(old_hb_dir, new_hb_dir)
                hb_rows = db.query(DeliveryHandbookFile).filter(DeliveryHandbookFile.client_id == client_id).all()
                for hb in hb_rows:
                    if (hb.stored_path or "").startswith(old_hb_prefix):
                        hb.stored_path = hb.stored_path.replace(old_hb_prefix, new_hb_prefix, 1)

        if updates:
            log = AuditLog(client_id=client_id, operator=user, action="; ".join(updates))
            db.add(log)
        sync_primary_contact(db, client)
        refresh_client_estimated_annual_amount(db, client_id, Client, Opportunity)
        db.commit()
        return {"status": "ok"}

    @app.delete("/api/clients/{client_id}")
    async def delete_client(
        client_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.clients.delete")),
    ):
        client = ensure_client_access(db, ctx, client_id, Client, action="delete")
        client_folder = f"{client.name}_{client.id}"
        src_path = os.path.join(upload_dir, client_folder)
        if os.path.exists(src_path):
            shutil.move(src_path, os.path.join(trash_dir, f"{client_folder}_{int(time.time())}"))
        hb_dir = os.path.join(upload_dir, "handbooks", client_folder)
        if os.path.isdir(hb_dir):
            shutil.move(hb_dir, os.path.join(trash_dir, f"handbooks_{client_folder}_{int(time.time())}"))
        db.query(DeliveryHandbookFile).filter(DeliveryHandbookFile.client_id == client_id).delete()

        db.delete(client)
        db.commit()
        return {"status": "deleted"}


def register_client_related_routes(
    app,
    *,
    get_db: Callable,
    Client,
    HandoffRequest,
    VisitRecord,
    AuditLog,
):
    """24C: handoff-summary, details, brief — must be registered BEFORE {client_id} routes."""

    @app.get("/api/clients/handoff-summary")
    async def clients_handoff_summary(
        db: Session = Depends(get_db), user: str = Depends(require_permission("crm.clients.read"))
    ):
        from handoff_core import build_clients_handoff_summary

        rows = db.query(HandoffRequest).filter(HandoffRequest.status != "superseded").all()
        return build_clients_handoff_summary(rows)

    @app.get("/api/clients/{client_id}/details")
    async def get_details(
        client_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.clients.read")),
    ):
        ensure_client_access(db, ctx, client_id, Client, action="read")
        if ctx.is_super or "crm.visits.read" in ctx.permissions:
            visits = db.query(VisitRecord).filter(VisitRecord.client_id == client_id).all()
        else:
            visits = []
        logs = db.query(AuditLog).filter(AuditLog.client_id == client_id).order_by(desc(AuditLog.created_at)).all()
        return {"visits": visits, "logs": logs}

    @app.get("/api/clients/{client_id}/brief")
    async def get_client_brief(
        client_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.clients.read")),
    ):
        c = ensure_client_access(db, ctx, client_id, Client, action="read")
        return {"id": c.id, "name": c.name, "owner": c.owner or "", "phase": c.phase or ""}
