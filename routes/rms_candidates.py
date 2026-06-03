"""RMS candidates API routes (Phase 2)."""
from __future__ import annotations

from typing import Any, Callable, Optional, Type

from fastapi import Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from auth.deps import get_current_context, require_permission
from auth.service import AuthContext
from schemas.rms import CandidateCreate, CandidateUpdate
from services import rms_candidates as cand_svc
from services import rms_resumes as resume_svc


def register_rms_candidates_routes(
    app,
    *,
    get_db: Callable,
    upload_dir: str,
    Client: Type[Any],
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    RmsResume: Type[Any],
    RmsJob: Type[Any],
):
    @app.get("/api/rms/candidates")
    async def api_list_candidates(
        q: Optional[str] = None,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.candidates.read")),
    ):
        return cand_svc.list_candidates(
            db,
            ctx,
            RmsCandidate,
            RmsApplication,
            Client,
            RmsResume=RmsResume,
            RmsJob=RmsJob,
            q_text=q,
        )

    @app.get("/api/rms/candidates/{candidate_id}")
    async def api_get_candidate(
        candidate_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.candidates.read")),
    ):
        return cand_svc.get_candidate(
            db,
            ctx,
            candidate_id,
            RmsCandidate,
            RmsApplication,
            Client,
            RmsResume=RmsResume,
            RmsJob=RmsJob,
        )

    @app.post("/api/rms/candidates")
    async def api_create_candidate(
        body: CandidateCreate,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.candidates.write")),
    ):
        return cand_svc.create_candidate(
            db,
            ctx,
            body.model_dump(),
            RmsCandidate,
            RmsResume=RmsResume,
            RmsJob=RmsJob,
            Client=Client,
            RmsApplication=RmsApplication,
        )

    @app.patch("/api/rms/candidates/{candidate_id}")
    async def api_patch_candidate(
        candidate_id: int,
        body: CandidateUpdate,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.candidates.write")),
    ):
        data = body.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status_code=400, detail="无更新字段")
        return cand_svc.update_candidate(
            db,
            ctx,
            candidate_id,
            data,
            RmsCandidate,
            RmsApplication,
            Client,
            RmsResume=RmsResume,
            RmsJob=RmsJob,
        )

    @app.post("/api/rms/candidates/{candidate_id}/resume")
    async def api_upload_candidate_resume(
        candidate_id: int,
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.candidates.write")),
    ):
        return await resume_svc.upload_candidate_resume(
            db,
            ctx,
            candidate_id,
            file,
            upload_dir=upload_dir,
            RmsCandidate=RmsCandidate,
            RmsApplication=RmsApplication,
            Client=Client,
            RmsResume=RmsResume,
        )

    @app.delete("/api/rms/candidates/{candidate_id}")
    async def api_delete_candidate(
        candidate_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.candidates.write")),
    ):
        return cand_svc.delete_candidate(
            db,
            ctx,
            candidate_id,
            RmsCandidate,
            RmsApplication,
            Client,
            upload_dir=upload_dir,
            RmsResume=RmsResume,
        )

    @app.get("/api/rms/resumes/{resume_id}/view")
    async def api_view_resume(
        resume_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.resumes.read")),
    ):
        return resume_svc.view_resume(
            db,
            ctx,
            resume_id,
            upload_dir=upload_dir,
            RmsCandidate=RmsCandidate,
            RmsApplication=RmsApplication,
            Client=Client,
            RmsResume=RmsResume,
        )

    @app.get("/api/rms/resumes/{resume_id}/download")
    async def api_download_resume(
        resume_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.resumes.download")),
    ):
        return resume_svc.download_resume(
            db,
            ctx,
            resume_id,
            upload_dir=upload_dir,
            RmsCandidate=RmsCandidate,
            RmsApplication=RmsApplication,
            Client=Client,
            RmsResume=RmsResume,
        )
