"""Client domain service — shared helpers for routes/clients.py and main.py (24B/24C)."""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from auth import data_scope as ds
from auth.data_scope_catalog import RESOURCE_CRM_CLIENT
from auth.service import AuthContext


def scoped_client_query(db: Session, ctx: AuthContext, Client, *, action: str = "read"):
    """Return a query filtered by the current user's data scope."""
    allowed = ds.visible_client_ids(db, ctx, Client, action=action)
    q = db.query(Client)
    if allowed is None:
        return q
    if not allowed:
        return q.filter(Client.id == -1)
    return q.filter(Client.id.in_(allowed))


def ensure_client_access(
    db: Session,
    ctx: AuthContext,
    client_id: int,
    Client,
    *,
    resource: str = RESOURCE_CRM_CLIENT,
    action: str = "read",
):
    """Assert the current user can access the given client, then return the Client row."""
    if resource == RESOURCE_CRM_CLIENT and action == "read":
        ds.assert_client_visible(db, ctx, client_id, Client, action=action)
    else:
        ds.assert_client_in_scope(db, ctx, client_id, Client, resource, action)
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="\u5ba2\u6237\u4e0d\u5b58\u5728")
    return client
