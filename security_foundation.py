"""Phase 01 security helpers: admin password policy, upload path safety, HTML gate."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from typing import Callable, Optional, Tuple
from urllib.parse import quote

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

_TRUTHY = frozenset({"1", "true", "yes", "on"})

# Business HTML routes (not /api/, not /static/)
_HTML_PROTECTED_PREFIXES = (
    "/home",
    "/customers",
    "/delivery",
    "/opportunity",
    "/goals",
    "/contracts",
    "/contacts",
    "/tools",
    "/system",
)

_PUBLIC_PATHS = frozenset({"/login", "/api/auth/login", "/api/auth/logout", "/api/auth/legacy-bootstrap"})

# 免登录可访问的公开 HTML 页面（精确匹配）。/home 作为全屏落地页公开，
# 但 /home/funnel、/home/trash 等子页仍受保护。
_PUBLIC_HTML_PATHS = frozenset({"/home", "/home/"})

_VISIT_ALLOWED_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".txt", ".doc", ".docx",
})


def allow_default_admin() -> bool:
    return os.environ.get("CRM_ALLOW_DEFAULT_ADMIN", "").strip().lower() in _TRUTHY


def default_admin_password_allowed(
    *,
    credentials_store_path: str,
    env_password: str,
) -> bool:
    """Whether legacy admin may use env/default password when no credentials file."""
    if os.path.isfile(credentials_store_path):
        return True
    if (env_password or "").strip():
        return True
    return allow_default_admin()


def admin_startup_auth_hint(
    *,
    effective_username: str,
    credentials_store_path: str,
    env_password_set: bool,
) -> str:
    user = effective_username
    if os.path.isfile(credentials_store_path):
        return f"管理员账号: {user}（已在界面修改密码，凭据保存在本地文件）"
    if env_password_set:
        return f"管理员账号: {user}（已配置 CRM_ADMIN_PASSWORD）"
    if allow_default_admin():
        return f"管理员账号: {user}（开发默认密码模式；生产请关闭 CRM_ALLOW_DEFAULT_ADMIN）"
    return (
        f"管理员账号: {user}（未配置强密码，默认 admin123 已禁用；"
        "请设置 CRM_ADMIN_PASSWORD 或 CRM_ALLOW_DEFAULT_ADMIN=1）"
    )


def resolve_upload_path(upload_dir: str, rel_path: str) -> str:
    rel = (rel_path or "").strip().replace("\\", "/")
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        raise ValueError("invalid path")
    root = os.path.realpath(upload_dir)
    abs_path = os.path.realpath(os.path.join(root, rel))
    if abs_path != root and not abs_path.startswith(root + os.sep):
        raise ValueError("path traversal")
    return abs_path


def file_access_url(stored_path: str) -> str:
    sp = (stored_path or "").strip()
    if not sp:
        return ""
    return f"/api/files/access?path={quote(sp, safe='')}"


def safe_visit_attachment_name(original_filename: str) -> str:
    ext = os.path.splitext(str(original_filename or ""))[1].lower()
    if ext not in _VISIT_ALLOWED_EXTENSIONS:
        ext = ".bin"
    return f"{int(time.time())}_{secrets.token_hex(8)}{ext}"


LEGACY_COOKIE_NAME = "crm_legacy"


def legacy_session_secret() -> str:
    return (os.environ.get("CRM_SESSION_SECRET") or "crm-dev-session-secret-change-me").strip()


def make_legacy_session_token(username: str) -> str:
    user = (username or "").strip()
    sig = hmac.new(
        legacy_session_secret().encode("utf-8"),
        user.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{user}:{sig}"


def verify_legacy_session_token(
    token: str,
    *,
    effective_username: str,
) -> bool:
    raw = (token or "").strip()
    if ":" not in raw:
        return False
    user, sig = raw.split(":", 1)
    if user != effective_username:
        return False
    expected = make_legacy_session_token(user)
    return secrets.compare_digest(expected, f"{user}:{sig}")


def request_is_authenticated(
    request: Request,
    *,
    verify_login: Callable[[str, str], bool],
    effective_username: str,
) -> bool:
    creds = _parse_basic_auth(request)
    if creds and verify_login(creds[0], creds[1]):
        return True
    cookie = request.cookies.get(LEGACY_COOKIE_NAME) or ""
    return verify_legacy_session_token(cookie, effective_username=effective_username)


def _parse_basic_auth(request: Request) -> Optional[Tuple[str, str]]:
    auth = (request.headers.get("authorization") or "").strip()
    if not auth.lower().startswith("basic "):
        return None
    try:
        raw = base64.b64decode(auth[6:].strip(), validate=False)
        decoded = raw.decode("utf-8")
    except Exception:
        return None
    username, sep, password = decoded.partition(":")
    if not sep:
        return None
    return username, password


def is_html_page_request(request: Request) -> bool:
    if request.method not in ("GET", "HEAD"):
        return False
    path = request.url.path or ""
    if path in _PUBLIC_PATHS or path in _PUBLIC_HTML_PATHS or path.startswith("/static/"):
        return False
    if path.startswith("/api/"):
        return False
    if path == "/":
        return False
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" in accept:
        return True
    return any(path == p or path.startswith(p + "/") for p in _HTML_PROTECTED_PREFIXES)


def html_auth_middleware(
    verify_login: Callable[[str, str], bool],
    effective_username: Callable[[], str],
    *,
    is_authenticated: Callable[[Request], bool] | None = None,
) -> type[BaseHTTPMiddleware]:
    class _HtmlAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next) -> Response:
            path = request.url.path or ""
            eff_user = effective_username()

            def authed() -> bool:
                if is_authenticated is not None:
                    return is_authenticated(request)
                return request_is_authenticated(
                    request,
                    verify_login=verify_login,
                    effective_username=eff_user,
                )
            if path == "/login":
                if authed():
                    dest = (request.query_params.get("next") or "/customers").strip()
                    if not dest.startswith("/") or dest.startswith("//"):
                        dest = "/customers"
                    return RedirectResponse(url=dest, status_code=302)
                return await call_next(request)
            if is_html_page_request(request) and not authed():
                next_path = quote(path, safe="/")
                return RedirectResponse(url=f"/login?next={next_path}", status_code=302)
            return await call_next(request)

    return _HtmlAuthMiddleware
