from __future__ import annotations

import csv
import io
from typing import Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import security_foundation as sec
from auth import service as auth_svc
from auth.deps import get_current_context, require_permission
from auth.permission_catalog import build_matrix_for_role, matrix_template
from auth.permissions import ALL_PERMISSION_CODES, ROLE_SUPER_ADMIN
from auth.service import AuthContext, SESSION_COOKIE_NAME, SESSION_MAX_AGE


class LoginBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class UserCreateBody(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=256)
    display_name: str = Field(default="", max_length=128)
    role_codes: List[str] = Field(default_factory=list)


class UserUpdateBody(BaseModel):
    display_name: str = Field(default="", max_length=128)


class UserStatusBody(BaseModel):
    status: str = Field(..., pattern="^(active|disabled)$")


class UserRolesBody(BaseModel):
    role_codes: List[str] = Field(default_factory=list)


class UserDeptsBody(BaseModel):
    dept_ids: List[int] = Field(default_factory=list)
    primary_dept_id: Optional[int] = None


class RoleDataScopeBody(BaseModel):
    scopes: List[Dict[str, str]] = Field(default_factory=list)


class UserPasswordBody(BaseModel):
    password: str = Field(..., min_length=6, max_length=256)
    must_change_password: bool = False


class BatchUserRolesBody(BaseModel):
    user_ids: List[int] = Field(..., min_length=1)
    role_codes: List[str] = Field(..., min_length=1)
    mode: str = Field(default="replace", pattern="^(replace|add)$")


class ChangePasswordBody(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=6, max_length=256)


class RoleCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field(default="", max_length=256)


class RoleUpdateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field(default="", max_length=256)


class RolePermissionsBody(BaseModel):
    permission_codes: List[str] = Field(default_factory=list)


def _session_payload(ctx: AuthContext) -> dict:
    return {
        "ok": True,
        "user": {
            "id": ctx.user_id,
            "username": ctx.username,
            "display_name": ctx.display_name,
        },
    }


def _set_session_cookie(resp: JSONResponse, ctx: AuthContext, db: Session) -> None:
    if ctx.user_id is None:
        return
    ver = auth_svc._user_session_version(db, ctx.user_id)
    token = auth_svc.make_session_token(ctx.user_id, ctx.username, ver)
    resp.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_MAX_AGE,
        path="/",
    )


def build_router(
    get_db: Callable,
    *,
    legacy_verify: Callable[[str, str], bool],
    legacy_effective_username: Callable[[], str],
) -> APIRouter:
    router = APIRouter(tags=["auth"])

    @router.get("/api/me")
    async def api_me(ctx: AuthContext = Depends(get_current_context)):
        return {
            "user": {
                "id": ctx.user_id,
                "username": ctx.username,
                "display_name": ctx.display_name,
            },
            "roles": ctx.roles,
            "permissions": sorted(ctx.permissions),
            "dept_ids": ctx.dept_ids,
            "primary_dept_id": ctx.primary_dept_id,
            "auth_mode": auth_svc.auth_mode(),
            "is_super": ctx.is_super,
            "must_change_password": ctx.must_change_password,
        }

    @router.post("/api/auth/login")
    async def api_auth_login(body: LoginBody, db: Session = Depends(get_db)):
        ctx = auth_svc.verify_sys_user_password(db, body.username.strip(), body.password)
        if not ctx:
            eff = legacy_effective_username()
            if body.username.strip().lower() == eff.lower() and legacy_verify(body.username.strip(), body.password):
                row = auth_svc._fetch_user_by_username(db, body.username.strip())
                if row:
                    ctx = auth_svc.build_auth_context(db, int(row["id"]), str(row["username"]))
                else:
                    ctx = AuthContext(
                        username=eff,
                        display_name=eff,
                        roles=[ROLE_SUPER_ADMIN],
                        permissions=set(ALL_PERMISSION_CODES),
                        is_super=True,
                    )
        if not ctx:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")
        if ctx.user_id is not None:
            auth_svc.record_login(db, ctx.user_id)
            db.commit()
        resp = JSONResponse(_session_payload(ctx))
        _set_session_cookie(resp, ctx, db)
        return resp

    @router.get("/api/system/permissions")
    async def api_list_permissions(
        _user: str = Depends(require_permission("system.roles.manage")),
        db: Session = Depends(get_db),
    ):
        from sqlalchemy import text

        rows = db.execute(
            text("SELECT id, code, name, module FROM sys_permission ORDER BY code")
        ).mappings().all()
        return [dict(r) for r in rows]

    @router.get("/api/system/permissions/matrix")
    async def api_permissions_matrix(
        role_id: Optional[int] = None,
        _user: str = Depends(require_permission("system.roles.manage")),
        db: Session = Depends(get_db),
    ):
        if role_id is None:
            return matrix_template()
        from sqlalchemy import text

        row = db.execute(
            text("SELECT id FROM sys_role WHERE id = :id"), {"id": role_id}
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="角色不存在")
        perms = set(auth_svc._role_permission_codes(db, role_id))
        data = build_matrix_for_role(perms)
        data["role_id"] = role_id
        data["readonly"] = False
        role = db.execute(
            text("SELECT code, is_builtin FROM sys_role WHERE id = :id"), {"id": role_id}
        ).mappings().first()
        if role and str(role["code"]) == ROLE_SUPER_ADMIN:
            data["readonly"] = True
        return data

    @router.get("/api/system/users")
    async def api_list_users(
        q: str = "",
        limit: int = 0,
        offset: int = 0,
        _user: str = Depends(require_permission("system.users.manage")),
        db: Session = Depends(get_db),
    ):
        return auth_svc.list_users(db, q=q, limit=limit, offset=offset)

    @router.post("/api/system/users")
    async def api_create_user(
        body: UserCreateBody,
        ctx: AuthContext = Depends(get_current_context),
        _perm: str = Depends(require_permission("system.users.manage")),
        db: Session = Depends(get_db),
    ):
        from auth.policy import PolicyError

        if not body.role_codes:
            raise HTTPException(status_code=400, detail="至少分配一个角色")
        try:
            created = auth_svc.create_user(
                db,
                username=body.username.strip(),
                password=body.password,
                display_name=body.display_name.strip(),
                role_codes=body.role_codes,
                actor=ctx.username,
                actor_ctx=ctx,
            )
            db.commit()
            return created
        except (ValueError, PolicyError) as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            db.rollback()
            if "UNIQUE" in str(e).upper():
                raise HTTPException(status_code=400, detail="用户名已存在")
            raise

    @router.put("/api/system/users/batch-roles")
    async def api_batch_user_roles(
        body: BatchUserRolesBody,
        ctx: AuthContext = Depends(get_current_context),
        _perm: str = Depends(require_permission("system.users.manage")),
        db: Session = Depends(get_db),
    ):
        from auth.policy import PolicyError

        try:
            result = auth_svc.batch_update_user_roles(
                db,
                body.user_ids,
                body.role_codes,
                mode=body.mode,
                actor=ctx.username,
                actor_ctx=ctx,
            )
            db.commit()
            return result
        except (ValueError, PolicyError) as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/api/system/users/import")
    async def api_import_users(
        file: UploadFile = File(...),
        ctx: AuthContext = Depends(get_current_context),
        _perm: str = Depends(require_permission("system.users.manage")),
        db: Session = Depends(get_db),
    ):
        raw = await file.read()
        try:
            text_data = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="请上传 UTF-8 编码的 CSV")
        reader = csv.DictReader(io.StringIO(text_data))
        if not reader.fieldnames:
            raise HTTPException(status_code=400, detail="CSV 缺少表头")
        rows = [dict(r) for r in reader]
        try:
            result = auth_svc.import_users_csv(db, rows, actor=ctx.username, actor_ctx=ctx)
            db.commit()
            return result
        except ValueError as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))

    @router.put("/api/system/users/{user_id}")
    async def api_update_user(
        user_id: int,
        body: UserUpdateBody,
        ctx: AuthContext = Depends(get_current_context),
        _perm: str = Depends(require_permission("system.users.manage")),
        db: Session = Depends(get_db),
    ):
        try:
            auth_svc.update_user_profile(
                db, user_id, display_name=body.display_name.strip(), actor=ctx.username
            )
            db.commit()
            return {"ok": True}
        except ValueError as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/api/system/users/{user_id}/status")
    async def api_set_user_status(
        user_id: int,
        body: UserStatusBody,
        ctx: AuthContext = Depends(get_current_context),
        _perm: str = Depends(require_permission("system.users.manage")),
        db: Session = Depends(get_db),
    ):
        from auth.policy import PolicyError

        try:
            auth_svc.set_user_status(
                db, user_id, body.status, actor=ctx.username, actor_ctx=ctx
            )
            db.commit()
            return {"ok": True}
        except (ValueError, PolicyError) as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))

    @router.put("/api/system/users/{user_id}/roles")
    async def api_update_user_roles(
        user_id: int,
        body: UserRolesBody,
        ctx: AuthContext = Depends(get_current_context),
        _perm: str = Depends(require_permission("system.users.manage")),
        db: Session = Depends(get_db),
    ):
        from auth.policy import PolicyError

        try:
            auth_svc.update_user_roles(
                db, user_id, body.role_codes, actor=ctx.username, actor_ctx=ctx
            )
            db.commit()
            return {"ok": True}
        except (ValueError, PolicyError) as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))

    @router.put("/api/system/users/{user_id}/password")
    async def api_reset_user_password(
        user_id: int,
        body: UserPasswordBody,
        ctx: AuthContext = Depends(get_current_context),
        _perm: str = Depends(require_permission("system.users.manage")),
        db: Session = Depends(get_db),
    ):
        try:
            auth_svc.reset_user_password(
                db,
                user_id,
                body.password,
                actor=ctx.username,
                must_change_password=body.must_change_password,
            )
            db.commit()
            return {"ok": True}
        except ValueError as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/api/auth/change-password")
    async def api_change_password(
        body: ChangePasswordBody,
        ctx: AuthContext = Depends(get_current_context),
        db: Session = Depends(get_db),
    ):
        if ctx.user_id is None:
            raise HTTPException(status_code=400, detail="仅本地账号可修改密码")
        try:
            auth_svc.change_own_password(
                db,
                ctx.user_id,
                current_password=body.current_password,
                new_password=body.new_password,
            )
            db.commit()
            resp = JSONResponse({"ok": True})
            fresh = auth_svc.build_auth_context(db, ctx.user_id, ctx.username)
            _set_session_cookie(resp, fresh, db)
            return resp
        except ValueError as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/api/system/roles")
    async def api_list_roles(
        _user: str = Depends(require_permission("system.roles.manage")),
        db: Session = Depends(get_db),
    ):
        return auth_svc.list_roles(db)

    @router.post("/api/system/roles")
    async def api_create_role(
        body: RoleCreateBody,
        ctx: AuthContext = Depends(get_current_context),
        _perm: str = Depends(require_permission("system.roles.manage")),
        db: Session = Depends(get_db),
    ):
        from auth.policy import PolicyError

        try:
            created = auth_svc.create_custom_role(
                db,
                name=body.name,
                description=body.description,
                actor=ctx.username,
            )
            db.commit()
            return created
        except (ValueError, PolicyError) as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))

    @router.put("/api/system/roles/{role_id}")
    async def api_update_role(
        role_id: int,
        body: RoleUpdateBody,
        ctx: AuthContext = Depends(get_current_context),
        _perm: str = Depends(require_permission("system.roles.manage")),
        db: Session = Depends(get_db),
    ):
        try:
            auth_svc.update_role_meta(
                db, role_id, name=body.name, description=body.description, actor=ctx.username
            )
            db.commit()
            return {"ok": True}
        except ValueError as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))

    @router.put("/api/system/roles/{role_id}/permissions")
    async def api_update_role_permissions(
        role_id: int,
        body: RolePermissionsBody,
        ctx: AuthContext = Depends(get_current_context),
        _perm: str = Depends(require_permission("system.roles.manage")),
        db: Session = Depends(get_db),
    ):
        invalid = [c for c in body.permission_codes if c not in ALL_PERMISSION_CODES]
        if invalid:
            raise HTTPException(status_code=400, detail=f"未知权限: {invalid}")
        try:
            auth_svc.set_role_permissions(
                db, role_id, body.permission_codes, actor=ctx.username, actor_ctx=ctx
            )
            db.commit()
            return {"ok": True}
        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/api/system/depts")
    async def api_list_depts(
        _user: str = Depends(require_permission("system.users.manage")),
        db: Session = Depends(get_db),
    ):
        return auth_svc.list_departments(db)

    @router.put("/api/system/users/{user_id}/depts")
    async def api_set_user_depts(
        user_id: int,
        body: UserDeptsBody,
        ctx: AuthContext = Depends(get_current_context),
        _perm: str = Depends(require_permission("system.users.manage")),
        db: Session = Depends(get_db),
    ):
        try:
            auth_svc.set_user_departments(
                db,
                user_id,
                body.dept_ids,
                primary_dept_id=body.primary_dept_id,
                actor=ctx.username,
            )
            db.commit()
            return {"ok": True}
        except ValueError as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/api/system/roles/{role_id}/data-scopes")
    async def api_get_role_data_scopes(
        role_id: int,
        _user: str = Depends(require_permission("system.roles.manage")),
        db: Session = Depends(get_db),
    ):
        from sqlalchemy import text

        row = db.execute(text("SELECT id FROM sys_role WHERE id = :id"), {"id": role_id}).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="角色不存在")
        scopes = auth_svc.get_role_data_scopes(db, role_id)
        data = auth_svc.build_data_scope_matrix(scopes)
        data["role_id"] = role_id
        return data

    @router.put("/api/system/roles/{role_id}/data-scopes")
    async def api_set_role_data_scopes(
        role_id: int,
        body: RoleDataScopeBody,
        ctx: AuthContext = Depends(get_current_context),
        _perm: str = Depends(require_permission("system.roles.manage")),
        db: Session = Depends(get_db),
    ):
        try:
            auth_svc.set_role_data_scopes(
                db, role_id, body.scopes, actor=ctx.username, actor_ctx=ctx
            )
            db.commit()
            return {"ok": True}
        except ValueError as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/api/system/users/{user_id}/permission-preview")
    async def api_user_permission_preview(
        user_id: int,
        _user: str = Depends(require_permission("system.users.manage")),
        db: Session = Depends(get_db),
    ):
        try:
            return auth_svc.user_permission_preview(db, user_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/api/system/audit-logs")
    async def api_audit_logs(
        actor_username: str = "",
        target_type: str = "",
        action: str = "",
        date_from: str = "",
        date_to: str = "",
        limit: int = 100,
        offset: int = 0,
        _user: str = Depends(require_permission("system.audit.read")),
        db: Session = Depends(get_db),
    ):
        return auth_svc.list_audit_logs(
            db,
            actor_username=actor_username,
            target_type=target_type,
            action=action,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )

    return router
