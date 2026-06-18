"""RMS Offer approval API routes (Phase 6B)."""
from __future__ import annotations

from typing import Any, Callable, Optional, Type

from fastapi import Depends
from sqlalchemy.orm import Session

from auth.deps import get_current_context, _require_logged_in, require_permission
from auth.service import AuthContext
from schemas.rms import OfferApprovalSubmitBody, OfferApproveBody, OfferReasonBody, OfferRejectBody
from services import rms_offer_approval as offer_svc


def register_rms_offers_routes(
    app,
    *,
    get_db: Callable,
    Client: Type[Any],
    CrmNotification: Type[Any],
    RmsApplication: Type[Any],
    RmsApplicationStatusHistory: Type[Any],
    RmsCandidate: Type[Any],
    RmsJob: Type[Any],
    RmsOfferRecord: Type[Any],
    RmsOfferApprovalStep: Type[Any],
    RmsOfferApprovalConfig: Type[Any],
):
    from auth.deps import require_permission

    @app.get("/api/rms/offers")
    async def api_list_offer_records(
        status: Optional[str] = None,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.applications.read")),
    ):
        return offer_svc.list_offer_records(
            db,
            ctx,
            status=status,
            RmsOfferRecord=RmsOfferRecord,
            RmsOfferApprovalStep=RmsOfferApprovalStep,
            RmsApplication=RmsApplication,
            RmsCandidate=RmsCandidate,
            RmsJob=RmsJob,
            Client=Client,
        )

    @app.get("/api/rms/applications/{application_id}/offer-approval-draft")
    async def api_get_offer_approval_draft(
        application_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.applications.read")),
    ):
        return offer_svc.get_offer_approval_draft(
            db,
            ctx,
            application_id,
            RmsApplication=RmsApplication,
            RmsCandidate=RmsCandidate,
            RmsJob=RmsJob,
            Client=Client,
        )

    @app.post("/api/rms/applications/{application_id}/offer-approval")
    async def api_submit_offer_approval(
        application_id: int,
        body: OfferApprovalSubmitBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.applications.write")),
    ):
        return offer_svc.submit_offer_approval(
            db,
            ctx,
            application_id,
            body.model_dump(),
            RmsApplication=RmsApplication,
            RmsApplicationStatusHistory=RmsApplicationStatusHistory,
            RmsCandidate=RmsCandidate,
            RmsJob=RmsJob,
            RmsOfferRecord=RmsOfferRecord,
            RmsOfferApprovalStep=RmsOfferApprovalStep,
            RmsOfferApprovalConfig=RmsOfferApprovalConfig,
            Client=Client,
            CrmNotification=CrmNotification,
        )

    @app.post("/api/rms/offers/{offer_record_id}/approve")
    async def api_approve_offer_step(
        offer_record_id: int,
        body: OfferApproveBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(_require_logged_in),
    ):
        return offer_svc.approve_offer_step(
            db,
            ctx,
            offer_record_id,
            body.comment,
            RmsApplication=RmsApplication,
            RmsApplicationStatusHistory=RmsApplicationStatusHistory,
            RmsOfferRecord=RmsOfferRecord,
            RmsOfferApprovalStep=RmsOfferApprovalStep,
            Client=Client,
            CrmNotification=CrmNotification,
        )

    @app.post("/api/rms/offers/{offer_record_id}/reject")
    async def api_reject_offer_step(
        offer_record_id: int,
        body: OfferRejectBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(_require_logged_in),
    ):
        return offer_svc.reject_offer_step(
            db,
            ctx,
            offer_record_id,
            body.reason,
            RmsApplication=RmsApplication,
            RmsApplicationStatusHistory=RmsApplicationStatusHistory,
            RmsOfferRecord=RmsOfferRecord,
            RmsOfferApprovalStep=RmsOfferApprovalStep,
            CrmNotification=CrmNotification,
        )

    @app.post("/api/rms/applications/{application_id}/drop-offer")
    async def api_drop_offer(
        application_id: int,
        body: OfferReasonBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.applications.write")),
    ):
        return offer_svc.drop_offer(
            db,
            ctx,
            application_id,
            body.reason,
            RmsApplication=RmsApplication,
            RmsApplicationStatusHistory=RmsApplicationStatusHistory,
            RmsCandidate=RmsCandidate,
            RmsJob=RmsJob,
            RmsOfferRecord=RmsOfferRecord,
            Client=Client,
        )

    @app.post("/api/rms/applications/{application_id}/transit-lost")
    async def api_mark_transit_lost(
        application_id: int,
        body: OfferReasonBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.applications.write")),
    ):
        return offer_svc.mark_transit_lost(
            db,
            ctx,
            application_id,
            body.reason,
            RmsApplication=RmsApplication,
            RmsApplicationStatusHistory=RmsApplicationStatusHistory,
            RmsCandidate=RmsCandidate,
            RmsJob=RmsJob,
            RmsOfferRecord=RmsOfferRecord,
            Client=Client,
        )
