"""RMS applications API routes (Phase 2)."""
from __future__ import annotations

import json
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
from services import rms_candidates as cand_svc
from services import rms_resumes as resume_svc
from services import rms_roster_check as roster_chk


def register_rms_applications_routes(
    app,
    *,
    get_db: Callable,
    upload_dir: str,
    Client: Type[Any],
    RmsJob: Type[Any],
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    RmsApplicationStatusHistory: Type[Any],
    RmsResume: Type[Any],
    RosterEntry: Type[Any],
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

    @app.post("/api/rms/applications/candidate-report")
    async def api_submit_candidate_report(
        report_json: str = Form(...),
        file: Optional[UploadFile] = File(None),
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.applications.write")),
    ):
        try:
            report = json.loads(report_json)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="推荐报告格式无效")
        if not isinstance(report, dict):
            raise HTTPException(status_code=400, detail="推荐报告格式无效")

        candidate_payload = {
            "name": str(report.get("name") or "").strip(),
            "phone": str(report.get("phone") or "").strip(),
            "email_wechat": str(report.get("email_wechat") or "").strip(),
            "age": str(report.get("age") or "").strip(),
            "work_years": str(report.get("work_years") or "").strip(),
            "target_job_id": report.get("job_id"),
            "target_client_id": report.get("client_id"),
            "current_salary": str(report.get("current_salary") or "").strip(),
            "expected_salary": str(report.get("expected_salary") or "").strip(),
            "available_date": str(report.get("available_date") or "").strip(),
            "education_level": str(report.get("education_level") or "").strip(),
            "school": str(report.get("school") or "").strip(),
            "major": str(report.get("major") or "").strip(),
            "gender": str(report.get("gender") or "").strip(),
            "marital_status": str(report.get("marital_status") or "").strip(),
            "city": str(report.get("city") or "").strip(),
            "source": str(report.get("source") or "").strip(),
        }
        candidate = cand_svc.create_candidate(
            db,
            ctx,
            candidate_payload,
            RmsCandidate,
            RmsResume=RmsResume,
            RmsJob=RmsJob,
            Client=Client,
            RmsApplication=RmsApplication,
        )
        resume_id = None
        if file is not None and file.filename:
            resume = await resume_svc.upload_candidate_resume(
                db,
                ctx,
                int(candidate["id"]),
                file,
                upload_dir=upload_dir,
                RmsCandidate=RmsCandidate,
                RmsApplication=RmsApplication,
                Client=Client,
                RmsResume=RmsResume,
            )
            resume_id = resume.get("id")
        application = app_svc.create_application(
            db,
            ctx,
            {
                "job_id": int(report.get("job_id") or 0),
                "candidate_id": int(candidate["id"]),
                "resume_id": resume_id,
            },
            RmsJob,
            RmsCandidate,
            RmsApplication,
            Client,
        )
        return {"candidate": candidate, "application": application}

    @app.get("/api/rms/applications/delivery-review")
    async def api_list_delivery_review_applications(
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.applications.read")),
    ):
        return app_svc.list_delivery_review_applications(db, ctx, RmsApplication, Client)

    @app.get("/api/rms/applications/hired-roster-check")
    async def api_hired_roster_check(
        client_id: Optional[int] = None,
        job_id: Optional[int] = None,
        recruiter_user_id: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.applications.read")),
    ):
        return roster_chk.list_hired_roster_checks(
            db,
            ctx,
            RmsApplication,
            RmsCandidate,
            RmsJob,
            RosterEntry,
            Client,
            client_id=client_id,
            job_id=job_id,
            recruiter_user_id=recruiter_user_id,
            date_from=date_from,
            date_to=date_to,
        )

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
            RmsApplicationStatusHistory,
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
            RmsCandidate=RmsCandidate,
            RosterEntry=RosterEntry,
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
