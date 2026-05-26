"""Client API routes — migrated from main.py (Phase 3A read, Phase 3B write)."""
from __future__ import annotations

import csv
import io
import os
import shutil
import time
from datetime import datetime
from typing import Callable, Optional

from fastapi import Depends, Form, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from auth import data_scope as ds
from auth import deps as auth_deps
from auth.data_scope_catalog import RESOURCE_CRM_CLIENT
from auth.deps import get_current_context, require_permission
from auth.service import AuthContext
from services.clients import ensure_client_access, scoped_client_query


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
        handoff_status: Optional[str] = None,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(auth_deps.require_permission("crm.clients.read")),
    ):
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
        if not handoff_status:
            return clients
        hs = handoff_status.strip()
        out = []
        for c in clients:
            latest = (
                db.query(HandoffRequest)
                .filter(HandoffRequest.client_id == c.id, HandoffRequest.status != "superseded")
                .order_by(desc(HandoffRequest.version), desc(HandoffRequest.id))
                .first()
            )
            cur = latest.status if latest else "none"
            if hs == "none" and not latest:
                out.append(c)
            elif latest and cur == hs:
                out.append(c)
        return out

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
        return client

    @app.get("/api/export/clients")
    async def export_clients(
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.clients.read")),
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
        city: Optional[str] = Form(None),
        remarks: Optional[str] = Form(None),
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.clients.write")),
    ):
        ds.assert_data_scope(ctx, RESOURCE_CRM_CLIENT, "write")
        owner_fields = ds.default_owner_fields(ctx)
        client = Client(
            name=name,
            industry=industry,
            owner=owner,
            scale=scale,
            phase=phase,
            description=description,
            estimated_annual_amount="",
            contact_name=(contact_name or "").strip(),
            contact_info=(contact_info or "").strip(),
            contact_title=(contact_title or "").strip(),
            contact_relationship=(contact_relationship or "").strip(),
            city=(city or "").strip(),
            remarks=(remarks or "").strip(),
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
        city: Optional[str] = Form(None),
        remarks: Optional[str] = Form(None),
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("crm.clients.write")),
    ):
        from phase2_core import refresh_client_estimated_annual_amount

        client = ensure_client_access(db, ctx, client_id, Client, action="write")
        duplicate = scoped_client_query(db, ctx, Client, action="write").filter(Client.name == name, Client.id != client_id).first()
        if duplicate:
            raise HTTPException(status_code=400, detail="\u5ba2\u6237\u540d\u79f0\u5df2\u5b58\u5728")

        old_name = client.name or ""
        updates = []
        if old_name != name:
            updates.append(f"\u5ba2\u6237\u540d\u79f0\u4ece[{old_name}]\u53d8\u66f4\u4e3a[{name}]")
        if client.industry != industry:
            updates.append(f"\u884c\u4e1a\u4ece[{client.industry}]\u53d8\u66f4\u4e3a[{industry}]")
        if client.owner != owner:
            updates.append(f"\u9500\u552e\u8d1f\u8d23\u4eba\u4ece[{client.owner}]\u53d8\u66f4\u4e3a[{owner}]")
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

        client.name = name
        client.industry = industry
        client.owner = owner
        client.scale = scale
        client.phase = phase
        client.description = description
        client.contact_name = new_contact_name
        client.contact_info = new_contact_info
        client.contact_title = new_contact_title
        client.contact_relationship = new_contact_relationship
        client.city = new_city
        client.remarks = remarks or ""

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
        user: str = Depends(require_permission("crm.clients.write")),
    ):
        client = ensure_client_access(db, ctx, client_id, Client, action="write")
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
