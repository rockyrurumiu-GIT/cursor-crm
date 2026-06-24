"""CRM_COOKIE_SECURE: session cookies use Secure flag when enabled."""
from __future__ import annotations

from starlette.responses import JSONResponse

import security_foundation as sec


def test_cookie_secure_env_truthy(monkeypatch):
    monkeypatch.setenv("CRM_COOKIE_SECURE", "1")
    assert sec.cookie_secure() is True


def test_cookie_secure_env_false_by_default(monkeypatch):
    monkeypatch.delenv("CRM_COOKIE_SECURE", raising=False)
    assert sec.cookie_secure() is False


def _set_cookie_headers(response) -> str:
    raw = response.headers.get("set-cookie", "")
    if hasattr(response.headers, "getlist"):
        parts = response.headers.getlist("set-cookie")
        if parts:
            return "; ".join(parts)
    return raw


def test_set_cookie_includes_secure_when_enabled(monkeypatch):
    monkeypatch.setenv("CRM_COOKIE_SECURE", "1")
    resp = JSONResponse({"ok": True})
    resp.set_cookie("crm_session", "token", httponly=True, samesite="lax", secure=sec.cookie_secure(), path="/")
    assert "secure" in _set_cookie_headers(resp).lower()


def test_delete_cookie_includes_secure_when_enabled(monkeypatch):
    monkeypatch.setenv("CRM_COOKIE_SECURE", "1")
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("crm_session", path="/", secure=sec.cookie_secure())
    assert "secure" in _set_cookie_headers(resp).lower()


def test_set_cookie_omits_secure_when_disabled(monkeypatch):
    monkeypatch.delenv("CRM_COOKIE_SECURE", raising=False)
    resp = JSONResponse({"ok": True})
    resp.set_cookie("crm_session", "token", httponly=True, samesite="lax", secure=sec.cookie_secure(), path="/")
    assert "secure" not in _set_cookie_headers(resp).lower()
