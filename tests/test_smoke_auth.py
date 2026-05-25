"""Smoke tests: auth, file gateway, HTML gate (phase 01)."""
from __future__ import annotations

from tests.helpers import auth_header


def test_stats_requires_auth(client):
    r = client.get("/api/stats")
    assert r.status_code == 401


def test_stats_admin_basic(client, admin_auth):
    user, pwd = admin_auth
    r = client.get("/api/stats", headers=auth_header(user, pwd))
    assert r.status_code == 200


def test_legacy_bootstrap_sets_cookie(client, admin_auth):
    user, pwd = admin_auth
    r = client.post("/api/auth/legacy-bootstrap", headers=auth_header(user, pwd))
    assert r.status_code == 200
    assert "crm_legacy" in r.cookies


def test_files_access_unauthenticated(client):
    r = client.get("/api/files/access", params={"path": "any/file.txt"})
    assert r.status_code == 401


def test_previews_mount_removed(client):
    r = client.get("/previews/any/path.txt")
    assert r.status_code == 404


def test_html_customers_redirects_without_session(client):
    r = client.get("/customers", headers={"Accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location", "").startswith("/login")


def test_html_customers_ok_with_cookie(client, admin_auth):
    user, pwd = admin_auth
    boot = client.post("/api/auth/legacy-bootstrap", headers=auth_header(user, pwd))
    assert boot.status_code == 200
    r = client.get("/customers", headers={"Accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 200


def test_default_password_blocked_without_allow_flag(client, monkeypatch):
    monkeypatch.delenv("CRM_ALLOW_DEFAULT_ADMIN", raising=False)
    monkeypatch.delenv("CRM_ADMIN_PASSWORD", raising=False)
    import security_foundation as sec

    assert sec.default_admin_password_allowed(
        credentials_store_path="/nonexistent/creds.json",
        env_password="",
    ) is False
