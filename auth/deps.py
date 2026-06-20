from __future__ import annotations

from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from auth import service as auth_svc
from auth.service import AuthContext

_security = HTTPBasic(auto_error=False)

# Set by main at startup
_legacy_verify: Optional[Callable[[str, str], bool]] = None
_legacy_effective_username: Optional[Callable[[], str]] = None
_get_db: Optional[Callable] = None


def _db_session():
    if _get_db is None:
        raise RuntimeError("auth.deps.configure_auth not called")
    yield from _get_db()


def configure_auth(
    *,
    get_db,
    legacy_verify: Callable[[str, str], bool],
    legacy_effective_username: Callable[[], str],
) -> None:
    global _get_db, _legacy_verify, _legacy_effective_username
    _get_db = get_db
    _legacy_verify = legacy_verify
    _legacy_effective_username = legacy_effective_username


def _resolve_context(request: Request, db: Session) -> Optional[AuthContext]:
    if _legacy_verify is None or _legacy_effective_username is None:
        raise RuntimeError("auth.deps.configure_auth not called")
    if auth_svc.is_rbac_mode():
        return auth_svc.resolve_rbac_from_request(
            request,
            db,
            legacy_verify=_legacy_verify,
            legacy_effective_username=_legacy_effective_username,
        )
    return auth_svc.resolve_legacy_from_request(
        request,
        legacy_verify=_legacy_verify,
        legacy_effective_username=_legacy_effective_username,
    )


def get_current_context(
    request: Request,
    db: Session = Depends(_db_session),
    credentials: Optional[HTTPBasicCredentials] = Depends(_security),
) -> AuthContext:
    ctx = _resolve_context(request, db)
    if ctx:
        request.state.crm_auth = ctx
        request.state.crm_permissions = ctx.permissions
        request.state.crm_is_super = ctx.is_super
        request.state.crm_user_id = ctx.user_id
        return ctx
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或会话已失效")


def get_current_user(ctx: AuthContext = Depends(get_current_context)) -> str:
    return ctx.username


def _require_logged_in(ctx: AuthContext = Depends(get_current_context)) -> AuthContext:
    """Authenticated session only; route may apply finer authorization."""
    return ctx


def _require_super_admin(ctx: AuthContext = Depends(get_current_context)) -> AuthContext:
    from auth.policy import assert_actor_is_super

    assert_actor_is_super(ctx)
    return ctx


def authenticate_admin(ctx: AuthContext = Depends(get_current_context)) -> str:
    if not ctx.is_super and "system.users.manage" not in ctx.permissions:
        if auth_svc.is_rbac_mode():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
        if _legacy_effective_username and ctx.username != _legacy_effective_username():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return ctx.username


def require_permission(code: str):
    def _dep(request: Request, ctx: AuthContext = Depends(get_current_context)) -> str:
        if auth_svc.is_rbac_mode() and not auth_svc.user_has_permission(ctx, code):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"缺少权限: {code}")
        return ctx.username

    return _dep


def require_any_permission(*codes: str):
    def _dep(request: Request, ctx: AuthContext = Depends(get_current_context)) -> AuthContext:
        if not auth_svc.is_rbac_mode():
            return ctx
        if ctx.is_super or any(auth_svc.user_has_permission(ctx, c) for c in codes):
            return ctx
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"缺少权限（需要其一）: {', '.join(codes)}",
        )

    return _dep


def request_is_authenticated(request: Request) -> bool:
    if _get_db is None:
        return False
    gen = _get_db()
    db = next(gen)
    try:
        return _resolve_context(request, db) is not None
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


# Back-compat alias used by route modules
def authenticate(ctx: AuthContext = Depends(get_current_context)) -> str:
    return ctx.username
