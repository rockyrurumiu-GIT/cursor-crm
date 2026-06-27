"""Navigation and page access restrictions for recruitment org departments."""
from __future__ import annotations

from typing import Callable, Set

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse, Response

from auth import service as auth_svc
from auth.service import AuthContext
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth import data_scope as ds

_RECRUITMENT_DEPT_MATCH_SQL = (
    "name LIKE :pat OR UPPER(code) LIKE 'RECRUIT%' OR path LIKE '%/RECRUIT%'"
)

_RECRUITMENT_HTML_PREFIXES = (
    "/rms",
    "/login",
    "/static",
)

_RECRUITMENT_HTML_EXACT = frozenset({"/", "/home"})


def recruitment_org_dept_ids(db: Session) -> Set[int]:
    rows = db.execute(
        text(
            "SELECT id FROM sys_dept WHERE status = 'active' "
            f"AND ({_RECRUITMENT_DEPT_MATCH_SQL})"
        ),
        {"pat": "%招聘%"},
    ).fetchall()
    root_ids = [int(r[0]) for r in rows]
    if not root_ids:
        return set()
    return ds._dept_subtree_ids(db, root_ids)


def user_in_recruitment_org_dept(db: Session, ctx: AuthContext) -> bool:
    if ctx.is_super or ctx.user_id is None:
        return False
    user_depts = ctx.dept_ids or ([ctx.primary_dept_id] if ctx.primary_dept_id else [])
    if not user_depts:
        return False
    recruit_ids = recruitment_org_dept_ids(db)
    if not recruit_ids:
        return False
    return any(int(d) in recruit_ids for d in user_depts)


def is_recruitment_nav_only_user(db: Session, ctx: AuthContext) -> bool:
    return user_in_recruitment_org_dept(db, ctx)


def is_recruitment_nav_html_path_allowed(path: str) -> bool:
    p = (path or "").split("?", 1)[0].rstrip("/") or "/"
    if p in _RECRUITMENT_HTML_EXACT:
        return True
    for prefix in _RECRUITMENT_HTML_PREFIXES:
        if p == prefix or p.startswith(prefix + "/"):
            return True
    return False


def recruitment_nav_redirect_path(path: str) -> str:
    return "/rms"


def recruitment_nav_middleware(
    get_db: Callable,
    *,
    legacy_verify: Callable[[str, str], bool],
    legacy_effective_username: Callable[[], str],
    is_html_page_request: Callable[[Request], bool],
) -> type[BaseHTTPMiddleware]:
    class _RecruitmentNavMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next) -> Response:
            path = request.url.path or ""
            if not is_html_page_request(request) or path.startswith("/login"):
                return await call_next(request)

            gen = get_db()
            db = next(gen)
            try:
                ctx = auth_svc.resolve_rbac_from_request(
                    request,
                    db,
                    legacy_verify=legacy_verify,
                    legacy_effective_username=legacy_effective_username,
                )
                if ctx is None:
                    ctx = auth_svc.resolve_legacy_from_request(
                        request,
                        legacy_verify=legacy_verify,
                        legacy_effective_username=legacy_effective_username,
                    )
                if ctx is None or not is_recruitment_nav_only_user(db, ctx):
                    return await call_next(request)
                norm = path.rstrip("/") or "/"
                if norm in ("/", "/home"):
                    return RedirectResponse(
                        url=recruitment_nav_redirect_path(path),
                        status_code=302,
                    )
                if is_recruitment_nav_html_path_allowed(path):
                    return await call_next(request)
                return RedirectResponse(
                    url=recruitment_nav_redirect_path(path),
                    status_code=302,
                )
            finally:
                try:
                    next(gen)
                except StopIteration:
                    pass

    return _RecruitmentNavMiddleware
