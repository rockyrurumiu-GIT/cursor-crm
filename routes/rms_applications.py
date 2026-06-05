"""RMS applications API routes (Phase 2)."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Type

from fastapi import Body, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from auth.deps import get_current_context, require_permission
from auth.service import AuthContext
from schemas.rms import (
    ApplicationCreate,
    ApplicationStatusBody,
    ApplicationUpdate,
    DeliveryReviewBody,
    reject_forbidden_application_keys,
)
from services import rms_applications as app_svc


def register_rms_applications_routes(
    app,
    *,
    get_db: Callable,
    Client: Type[Any],
    RmsJob: Type[Any],
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    RmsApplicationStatusHistory: Type[Any],
):
    @app.get("/api/rms/applications")
    async def api_list_applications(
        job_id: Optional[int] = None,
        candidate_id: Optional[int] = None,
        client_id: Optional[int] = None,
        status: Optional[str] = None,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.applications.read")),
    ):
        return app_svc.list_applications(
            db,
            ctx,
            RmsApplication,
            Client,
            job_id=job_id,
            candidate_id=candidate_id,
            client_id=client_id,
            status=status,
        )

    @app.post("/api/rms/applications/candidate-report/parse-draft")
    async def api_parse_candidate_report_draft(
        file: UploadFile = File(...),
        job_id: Optional[int] = Form(None),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.applications.write")),
    ):
        content = await file.read()
        return app_svc.parse_resume_draft(file.filename or "", content)

    @app.get("/api/rms/applications/delivery-review")
    async def api_list_delivery_review_applications(
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.applications.read")),
    ):
        return app_svc.list_delivery_review_applications(db, ctx, RmsApplication, Client)

    @app.get("/api/rms/applications/{application_id}")
    async def api_get_application(
        application_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.applications.read")),
    ):
        return app_svc.get_application(db, ctx, application_id, RmsApplication, Client)

    @app.post("/api/rms/applications")
    async def api_create_application(
        body: Dict[str, Any] = Body(...),
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.applications.write")),
    ):
        reject_forbidden_application_keys(body)
        payload = ApplicationCreate.model_validate(body)
        return app_svc.create_application(
            db,
            ctx,
            payload.model_dump(),
            RmsJob,
            RmsCandidate,
            RmsApplication,
            Client,
        )

    @app.patch("/api/rms/applications/{application_id}")
    async def api_patch_application(
        application_id: int,
        body: Dict[str, Any] = Body(...),
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.applications.write")),
    ):
        reject_forbidden_application_keys(body)
        if not body:
            raise HTTPException(status_code=400, detail="无更新字段")
        payload = ApplicationUpdate.model_validate(body)
        data = payload.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status_code=400, detail="无更新字段")
        return app_svc.update_application(
            db,
            ctx,
            application_id,
            data,
            RmsJob,
            RmsCandidate,
            RmsApplication,
            Client,
        )

    @app.post("/api/rms/applications/{application_id}/delivery-review")
    async def api_submit_delivery_review(
        application_id: int,
        body: DeliveryReviewBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.applications.write")),
    ):
        return app_svc.submit_delivery_review(
            db,
            ctx,
            application_id,
            body.model_dump(),
            RmsApplication,
            Client,
        )

    @app.post("/api/rms/applications/{application_id}/status")
    async def api_transition_application_status(
        application_id: int,
        body: ApplicationStatusBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.applications.write")),
    ):
        return app_svc.transition_application_status(
            db,
            ctx,
            application_id,
            body.model_dump(),
            RmsApplication,
            RmsApplicationStatusHistory,
            Client,
        )

    @app.get("/api/rms/applications/{application_id}/status-history")
    async def api_list_status_history(
        application_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.applications.read")),
    ):
        return app_svc.list_status_history(
            db,
            ctx,
            application_id,
            RmsApplication,
            RmsApplicationStatusHistory,
            Client,
        )
