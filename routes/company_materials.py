"""Company materials library API routes."""
from __future__ import annotations

from typing import Any, Callable, Optional, Type

from fastapi import Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from auth.deps import get_current_context, require_permission
from auth.service import AuthContext
from schemas.company_materials import MATERIAL_ALLOWED_SUFFIXES, MaterialUpdateBody
from services import company_materials as mat_svc


def register_company_materials_routes(
    app,
    *,
    get_db: Callable,
    CompanyMaterial: Type[Any],
    upload_dir: str,
    max_file_size: int,
):
    @app.get("/api/materials/form-options")
    async def api_materials_form_options(
        db: Session = Depends(get_db),
        _user: str = Depends(require_permission("materials.read")),
    ):
        return mat_svc.list_form_options(db)

    @app.get("/api/materials")
    async def api_list_materials(
        q: Optional[str] = None,
        category: Optional[str] = None,
        confidentiality: Optional[str] = None,
        status: Optional[str] = None,
        owner_dept_id: Optional[int] = None,
        expires_before: Optional[str] = None,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("materials.read")),
    ):
        return mat_svc.list_materials(
            db,
            ctx,
            CompanyMaterial,
            q_text=q,
            category=category,
            confidentiality=confidentiality,
            status_filter=status,
            owner_dept_id=owner_dept_id,
            expires_before=expires_before,
        )

    @app.post("/api/materials", status_code=201)
    async def api_create_material(
        title: str = Form(...),
        category: str = Form(...),
        confidentiality: str = Form(...),
        description: str = Form(default=""),
        owner_dept_id: Optional[int] = Form(default=None),
        expires_at: str = Form(default=""),
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("materials.write")),
    ):
        return await mat_svc.create_material(
            db,
            ctx,
            CompanyMaterial,
            title=title,
            category=category,
            confidentiality=confidentiality,
            description=description,
            owner_dept_id=owner_dept_id,
            expires_at=expires_at,
            upload=file,
            upload_dir=upload_dir,
            max_file_size=max_file_size,
            allowed_suffixes=MATERIAL_ALLOWED_SUFFIXES,
        )

    @app.get("/api/materials/{material_id}")
    async def api_get_material(
        material_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("materials.read")),
    ):
        return mat_svc.get_material(db, ctx, CompanyMaterial, material_id)

    @app.patch("/api/materials/{material_id}")
    async def api_patch_material(
        material_id: int,
        body: MaterialUpdateBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("materials.write")),
    ):
        return mat_svc.update_material(
            db,
            ctx,
            CompanyMaterial,
            material_id,
            body,
            fields_set=set(body.model_fields_set),
        )

    @app.get("/api/materials/{material_id}/download")
    async def api_download_material(
        material_id: int,
        db: Session = Depends(get_db),
        _user: str = Depends(require_permission("materials.download")),
    ):
        return mat_svc.download_material(
            db,
            CompanyMaterial,
            material_id,
            upload_dir=upload_dir,
        )

    @app.post("/api/materials/{material_id}/replace-file")
    async def api_replace_material_file(
        material_id: int,
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("materials.write")),
    ):
        return await mat_svc.replace_material_file(
            db,
            ctx,
            CompanyMaterial,
            material_id,
            upload=file,
            upload_dir=upload_dir,
            max_file_size=max_file_size,
            allowed_suffixes=MATERIAL_ALLOWED_SUFFIXES,
        )

    @app.post("/api/materials/{material_id}/archive")
    async def api_archive_material(
        material_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("materials.delete")),
    ):
        return mat_svc.archive_material(db, ctx, CompanyMaterial, material_id)
