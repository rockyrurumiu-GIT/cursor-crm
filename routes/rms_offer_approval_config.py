"""RMS Offer approval config API routes (Phase 6B-0)."""
from __future__ import annotations

from typing import Any, Callable, Optional, Type

from fastapi import Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.deps import get_current_context, require_permission
from auth.service import AuthContext
from services import rms_offer_approval_config as config_svc


class OfferApprovalConfigBody(BaseModel):
    dept_superior_user_id: Optional[int] = None
    ops_head_user_id: Optional[int] = None
    gm_user_id: Optional[int] = None


def register_rms_offer_approval_config_routes(
    app,
    *,
    get_db: Callable,
    RmsOfferApprovalConfig: Type[Any],
):
    @app.get("/api/rms/offer-approval-config")
    async def api_list_offer_approval_config(
        db: Session = Depends(get_db),
        _user: str = Depends(require_permission("system.users.manage")),
    ):
        return config_svc.list_offer_approval_configs(
            db,
            RmsOfferApprovalConfig=RmsOfferApprovalConfig,
        )

    @app.put("/api/rms/offer-approval-config/default")
    async def api_upsert_default_offer_approval_config(
        body: OfferApprovalConfigBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("system.users.manage")),
    ):
        return config_svc.upsert_default_offer_approval_config(
            db,
            body.model_dump(),
            ctx,
            RmsOfferApprovalConfig=RmsOfferApprovalConfig,
        )

    @app.put("/api/rms/offer-approval-config/depts/{dept_id}")
    async def api_upsert_dept_offer_approval_config(
        dept_id: int,
        body: OfferApprovalConfigBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("system.users.manage")),
    ):
        return config_svc.upsert_dept_offer_approval_config(
            db,
            dept_id,
            body.model_dump(),
            ctx,
            RmsOfferApprovalConfig=RmsOfferApprovalConfig,
        )

    @app.delete("/api/rms/offer-approval-config/depts/{dept_id}")
    async def api_delete_dept_offer_approval_config(
        dept_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("system.users.manage")),
    ):
        return config_svc.delete_dept_offer_approval_config(
            db,
            dept_id,
            ctx,
            RmsOfferApprovalConfig=RmsOfferApprovalConfig,
        )
