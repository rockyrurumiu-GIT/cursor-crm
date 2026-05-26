"""Client read API routes (Phase 3A) — migrated from main.py."""
from __future__ import annotations

import csv
import io
import os
from datetime import datetime
from typing import Callable, Optional

from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from auth import deps as auth_deps
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
