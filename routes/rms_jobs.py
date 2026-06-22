"""RMS jobs API routes (Phase 2)."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Type

from fastapi import Body, Depends, HTTPException
from sqlalchemy.orm import Session

from auth.deps import get_current_context, require_permission
from auth.service import AuthContext
from schemas.rms import JobCreate, JobUpdate
from services import rms_jobs as job_svc


def register_rms_jobs_routes(
    app,
    *,
    get_db: Callable,
    Client: Type[Any],
    RmsJob: Type[Any],
    RmsApplication: Type[Any],
):
    @app.get("/api/rms/jobs")
    async def api_list_jobs(
        client_id: Optional[int] = None,
        status: Optional[str] = None,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.jobs.read")),
    ):
        return job_svc.list_jobs(
            db, ctx, RmsJob, Client, RmsApplication, client_id=client_id, status=status
        )

    @app.get("/api/rms/jobs/{job_id}")
    async def api_get_job(
        job_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.jobs.read")),
    ):
        return job_svc.get_job(db, ctx, job_id, RmsJob, Client, RmsApplication)

    @app.post("/api/rms/jobs")
    async def api_create_job(
        body: JobCreate,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.jobs.write")),
    ):
        return job_svc.create_job(
            db, ctx, body.model_dump(), RmsJob, RmsApplication, Client
        )

    @app.patch("/api/rms/jobs/{job_id}")
    async def api_patch_job(
        job_id: int,
        body: JobUpdate,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.jobs.write")),
    ):
        data = body.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status_code=400, detail="无更新字段")
        return job_svc.update_job(db, ctx, job_id, data, RmsJob, RmsApplication, Client)

    @app.delete("/api/rms/jobs/{job_id}")
    async def api_delete_job(
        job_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.jobs.delete")),
    ):
        return job_svc.delete_job(
            db, ctx, job_id, RmsJob, RmsApplication, Client
        )
