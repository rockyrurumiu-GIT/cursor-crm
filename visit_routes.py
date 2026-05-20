"""客户拜访记录：页面与 API。"""
from __future__ import annotations

from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from visit_core import VisitBody, apply_visit_body, visit_to_dict


def register_visit_routes(
    app,
    *,
    get_db: Callable,
    authenticate: Callable,
    page_renderer: Callable,
    Client,
    VisitRecord,
):
    @app.get("/customers/visits", response_class=HTMLResponse)
    async def page_customer_visits(request: Request):
        return page_renderer("pages/customer_visits.html", request)

    @app.get("/api/customer-visits/filters")
    async def visit_filters(db: Session = Depends(get_db), user: str = Depends(authenticate)):
        rows = db.query(VisitRecord).all()
        sales = sorted({(r.salesperson or "").strip() for r in rows if (r.salesperson or "").strip()})
        regions = sorted({(r.region or r.location or "").strip() for r in rows if (r.region or r.location or "").strip()})
        clients = db.query(Client).order_by(Client.name).all()
        return {
            "salespeople": sales,
            "regions": regions,
            "clients": [{"id": c.id, "name": c.name, "owner": c.owner or ""} for c in clients],
        }

    @app.get("/api/customer-visits")
    async def list_customer_visits(
        salesperson: Optional[str] = None,
        region: Optional[str] = None,
        client_id: Optional[int] = None,
        db: Session = Depends(get_db),
        user: str = Depends(authenticate),
    ):
        q = db.query(VisitRecord)
        if client_id:
            q = q.filter(VisitRecord.client_id == client_id)
        rows = q.order_by(desc(VisitRecord.id)).all()
        out = []
        for v in rows:
            c = db.query(Client).filter(Client.id == v.client_id).first()
            d = visit_to_dict(v, c.name if c else "")
            sp = d["salesperson"] or (c.owner if c else "")
            reg = d["region"]
            if salesperson and sp != salesperson:
                continue
            if region and reg != region:
                continue
            d["salesperson"] = sp
            out.append(d)
        return out

    @app.get("/api/customer-visits/{visit_id}")
    async def get_customer_visit(
        visit_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)
    ):
        v = db.query(VisitRecord).filter(VisitRecord.id == visit_id).first()
        if not v:
            raise HTTPException(status_code=404, detail="拜访记录不存在")
        c = db.query(Client).filter(Client.id == v.client_id).first()
        d = visit_to_dict(v, c.name if c else "")
        d["salesperson"] = d["salesperson"] or (c.owner if c else "")
        return d

    @app.post("/api/customer-visits")
    async def create_customer_visit(
        body: VisitBody, db: Session = Depends(get_db), user: str = Depends(authenticate)
    ):
        client = db.query(Client).filter(Client.id == body.client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="客户不存在")
        v = VisitRecord(client_id=body.client_id)
        apply_visit_body(v, body)
        if not v.salesperson:
            v.salesperson = client.owner or user
        db.add(v)
        db.commit()
        db.refresh(v)
        return visit_to_dict(v, client.name)

    @app.put("/api/customer-visits/{visit_id}")
    async def update_customer_visit(
        visit_id: int,
        body: VisitBody,
        db: Session = Depends(get_db),
        user: str = Depends(authenticate),
    ):
        v = db.query(VisitRecord).filter(VisitRecord.id == visit_id).first()
        if not v:
            raise HTTPException(status_code=404, detail="拜访记录不存在")
        client = db.query(Client).filter(Client.id == body.client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="客户不存在")
        apply_visit_body(v, body)
        db.commit()
        db.refresh(v)
        return visit_to_dict(v, client.name)

    @app.delete("/api/customer-visits/{visit_id}")
    async def delete_customer_visit(
        visit_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)
    ):
        v = db.query(VisitRecord).filter(VisitRecord.id == visit_id).first()
        if not v:
            raise HTTPException(status_code=404, detail="拜访记录不存在")
        db.delete(v)
        db.commit()
        return {"ok": True}
