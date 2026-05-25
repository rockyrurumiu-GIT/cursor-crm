"""Smoke tests: phase 02 RBAC (permission 403, /api/me, migrations)."""
from __future__ import annotations

import importlib
import os

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from auth import service as auth_svc
from tests.helpers import auth_header


@pytest.fixture
def client_rbac(_test_env, monkeypatch):
    monkeypatch.setenv("CRM_AUTH_MODE", "rbac")
    import main as crm_main

    importlib.reload(crm_main)
    with TestClient(crm_main.app) as c:
        yield c


def _login_rbac(client, username: str, password: str):
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )


def _create_viewer(client, admin_user: str, admin_pwd: str, suffix: str):
    headers = {**auth_header(admin_user, admin_pwd), "Content-Type": "application/json"}
    username = f"viewer_{suffix}"
    body = {
        "username": username,
        "password": "viewer123",
        "display_name": "Viewer",
        "role_codes": ["RESTRICTED"],
    }
    r = client.post("/api/system/users", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return username, "viewer123"


def test_schema_migrations_applied(client):
    import main as crm_main

    with crm_main.engine.connect() as conn:
        row = conn.execute(
            text("SELECT migration_id FROM schema_migrations WHERE migration_id = :id"),
            {"id": "001_rbac_tables.sql"},
        ).fetchone()
    assert row is not None


def test_api_me_admin(client, admin_auth):
    user, pwd = admin_auth
    boot = client.post("/api/auth/legacy-bootstrap", headers=auth_header(user, pwd))
    assert boot.status_code == 200
    me = client.get("/api/me", cookies=boot.cookies)
    assert me.status_code == 200
    data = me.json()
    assert data["user"]["username"] == user
    assert "crm.clients.read" in data["permissions"]
    assert "SUPER_ADMIN" in data["roles"]


def test_viewer_forbidden_clients_list(client_rbac, admin_auth):
    user, pwd = admin_auth
    suffix = os.getpid()
    viewer_user, viewer_pwd = _create_viewer(client_rbac, user, pwd, str(suffix))
    login = _login_rbac(client_rbac, viewer_user, viewer_pwd)
    assert login.status_code == 200
    me = client_rbac.get("/api/me", cookies=login.cookies)
    assert me.status_code == 200
    assert "crm.clients.read" not in me.json().get("permissions", [])

    listed = client_rbac.get("/api/clients", cookies=login.cookies)
    assert listed.status_code == 403


def test_viewer_me_permissions(client_rbac, admin_auth):
    user, pwd = admin_auth
    viewer_user, viewer_pwd = _create_viewer(client_rbac, user, pwd, f"me_{os.getpid()}")
    login = _login_rbac(client_rbac, viewer_user, viewer_pwd)
    me = client_rbac.get("/api/me", cookies=login.cookies)
    assert me.status_code == 200
    perms = set(me.json().get("permissions") or [])
    assert perms == set()
    assert me.json().get("roles") == ["RESTRICTED"]


def test_rbac_login_session(client_rbac, admin_auth):
    user, pwd = admin_auth
    r = _login_rbac(client_rbac, user, pwd)
    assert r.status_code == 200
    assert auth_svc.SESSION_COOKIE_NAME in r.cookies
    stats = client_rbac.get("/api/stats", cookies=r.cookies)
    assert stats.status_code == 200


def test_username_login_case_insensitive(client_rbac, admin_auth):
    user, pwd = admin_auth
    suffix = os.getpid()
    headers = {**auth_header(user, pwd), "Content-Type": "application/json"}
    stored = f"CaseUser_{suffix}"
    body = {
        "username": stored,
        "password": "casepass1",
        "display_name": "Case User",
        "role_codes": ["VIEWER"],
    }
    created = client_rbac.post("/api/system/users", headers=headers, json=body)
    assert created.status_code == 200, created.text

    for login_name in (stored.lower(), stored.upper()):
        login = _login_rbac(client_rbac, login_name, "casepass1")
        assert login.status_code == 200, login.text
        me = client_rbac.get("/api/me", cookies=login.cookies)
        assert me.status_code == 200
        assert me.json()["user"]["username"] == stored


def test_username_create_rejects_case_duplicate(client_rbac, admin_auth):
    user, pwd = admin_auth
    suffix = os.getpid()
    headers = {**auth_header(user, pwd), "Content-Type": "application/json"}
    stored = f"DupUser_{suffix}"
    body = {
        "username": stored,
        "password": "casepass1",
        "display_name": "Dup User",
        "role_codes": ["VIEWER"],
    }
    first = client_rbac.post("/api/system/users", headers=headers, json=body)
    assert first.status_code == 200, first.text

    dup = client_rbac.post(
        "/api/system/users",
        headers=headers,
        json={**body, "username": stored.lower()},
    )
    assert dup.status_code == 400
    assert "用户名已存在" in dup.json().get("detail", "")
