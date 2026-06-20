"""Policy guards for permission center (P0)."""
from __future__ import annotations

import importlib
import os

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from tests.helpers import auth_header


@pytest.fixture
def client_rbac(_test_env, monkeypatch):
    monkeypatch.setenv("CRM_AUTH_MODE", "rbac")
    import main as crm_main

    importlib.reload(crm_main)
    with TestClient(crm_main.app) as c:
        yield c


def _login(client, username: str, password: str):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _create_restricted(client, admin_user: str, admin_pwd: str, suffix: str):
    headers = {**auth_header(admin_user, admin_pwd), "Content-Type": "application/json"}
    username = f"restricted_{suffix}"
    r = client.post(
        "/api/system/users",
        headers=headers,
        json={
            "username": username,
            "password": "restricted1",
            "display_name": "R",
            "role_codes": ["RESTRICTED"],
        },
    )
    if r.status_code == 400 and "已存在" in r.text:
        return username, "restricted1"
    assert r.status_code == 200, r.text
    return username, "restricted1"


def test_migration_003_applied(client):
    import main as crm_main

    with crm_main.engine.connect() as conn:
        row = conn.execute(
            text("SELECT migration_id FROM schema_migrations WHERE migration_id LIKE '003_%'")
        ).fetchone()
    assert row is not None


def test_migration_002_applied(client):
    import main as crm_main

    with crm_main.engine.connect() as conn:
        row = conn.execute(
            text("SELECT migration_id FROM schema_migrations WHERE migration_id LIKE '002_%'")
        ).fetchone()
    assert row is not None


def test_viewer_cannot_create_user(client_rbac, admin_auth):
    user, pwd = admin_auth
    suffix = os.getpid()
    _create_restricted(client_rbac, user, pwd, str(suffix))
    r_user, r_pwd = f"restricted_{suffix}", "restricted1"
    login = _login(client_rbac, r_user, r_pwd)
    assert login.status_code == 200
    created = client_rbac.post(
        "/api/system/users",
        cookies=login.cookies,
        json={
            "username": f"blocked_{suffix}",
            "password": "pass1234",
            "display_name": "X",
            "role_codes": ["VIEWER"],
        },
    )
    assert created.status_code == 403


@pytest.mark.parametrize(
    "method,path_template,body",
    [
        (
            "put",
            "/api/system/users/{uid}/roles",
            {"role_codes": ["VIEWER"]},
        ),
        (
            "put",
            "/api/system/users/{uid}/password",
            {"password": "newpass12"},
        ),
    ],
)
def test_restricted_cannot_manage_users(
    client_rbac, admin_auth, method, path_template, body
):
    user, pwd = admin_auth
    suffix = f"{os.getpid()}_{method}_{path_template.split('/')[-1]}"
    headers = {**auth_header(user, pwd), "Content-Type": "application/json"}
    target = client_rbac.post(
        "/api/system/users",
        headers=headers,
        json={
            "username": f"target_{suffix}",
            "password": "target1234",
            "display_name": "T",
            "role_codes": ["VIEWER"],
        },
    )
    assert target.status_code == 200, target.text
    uid = target.json()["id"]
    _create_restricted(client_rbac, user, pwd, suffix)
    login = _login(client_rbac, f"restricted_{suffix}", "restricted1")
    assert login.status_code == 200
    path = path_template.format(uid=uid)
    r = client_rbac.request(method, path, cookies=login.cookies, json=body)
    assert r.status_code == 403
    assert "system.users.manage" in r.json().get("detail", "")


def test_restricted_cannot_edit_viewer_role_permissions(client_rbac, admin_auth):
    user, pwd = admin_auth
    suffix = f"{os.getpid()}_viewer_role"
    _create_restricted(client_rbac, user, pwd, suffix)
    login = _login(client_rbac, f"restricted_{suffix}", "restricted1")
    import main as crm_main

    with crm_main.engine.connect() as conn:
        rid = conn.execute(
            text("SELECT id FROM sys_role WHERE code = 'VIEWER'")
        ).fetchone()[0]
    r = client_rbac.put(
        f"/api/system/roles/{rid}/permissions",
        cookies=login.cookies,
        json={"permission_codes": ["crm.clients.read"]},
    )
    assert r.status_code == 403
    assert "system.roles.manage" in r.json().get("detail", "")


def test_non_super_cannot_edit_super_admin_role_permissions(client_rbac, admin_auth):
    user, pwd = admin_auth
    suffix = f"{os.getpid()}_super_role"
    _create_restricted(client_rbac, user, pwd, suffix)
    login = _login(client_rbac, f"restricted_{suffix}", "restricted1")
    import main as crm_main

    with crm_main.engine.connect() as conn:
        rid = conn.execute(
            text("SELECT id FROM sys_role WHERE code = 'SUPER_ADMIN'")
        ).fetchone()[0]
    r = client_rbac.put(
        f"/api/system/roles/{rid}/permissions",
        cookies=login.cookies,
        json={"permission_codes": ["crm.clients.read"]},
    )
    assert r.status_code == 403


def test_cannot_remove_last_super_admin(client_rbac, admin_auth):
    import main as crm_main

    from auth.permissions import ROLE_SUPER_ADMIN

    user, pwd = admin_auth
    login = _login(client_rbac, user, pwd)
    me = client_rbac.get("/api/me", cookies=login.cookies).json()
    uid = me["user"]["id"]

    with crm_main.engine.begin() as conn:
        super_rid = conn.execute(
            text("SELECT id FROM sys_role WHERE code = :c"),
            {"c": ROLE_SUPER_ADMIN},
        ).scalar()
        conn.execute(
            text("DELETE FROM sys_user_role WHERE role_id = :rid AND user_id != :uid"),
            {"rid": super_rid, "uid": uid},
        )
        conn.execute(
            text("INSERT OR IGNORE INTO sys_user_role (user_id, role_id) VALUES (:uid, :rid)"),
            {"uid": uid, "rid": super_rid},
        )

    headers = {**auth_header(user, pwd), "Content-Type": "application/json"}
    r = client_rbac.put(
        f"/api/system/users/{uid}/roles",
        headers=headers,
        json={"role_codes": ["VIEWER"]},
    )
    assert r.status_code == 400
    assert "最后一个超级管理员" in str(r.json().get("detail", ""))


def test_disabled_user_session_invalid(client_rbac, admin_auth):
    user, pwd = admin_auth
    suffix = os.getpid()
    headers = {**auth_header(user, pwd), "Content-Type": "application/json"}
    uname = f"disable_me_{suffix}"
    created = client_rbac.post(
        "/api/system/users",
        headers=headers,
        json={
            "username": uname,
            "password": "disable123",
            "display_name": "D",
            "role_codes": ["VIEWER"],
        },
    )
    assert created.status_code == 200, created.text
    uid = created.json()["id"]
    login = _login(client_rbac, uname, "disable123")
    assert login.status_code == 200
    session_cookies = dict(login.cookies)
    # TestClient keeps cookies across requests; clear viewer session so admin Basic auth applies.
    client_rbac.cookies.clear()
    disabled = client_rbac.post(
        f"/api/system/users/{uid}/status",
        headers=headers,
        json={"status": "disabled"},
    )
    assert disabled.status_code == 200, disabled.text
    me = client_rbac.get("/api/me", cookies=session_cookies)
    assert me.status_code == 401


def test_role_change_writes_audit(client_rbac, admin_auth):
    user, pwd = admin_auth
    suffix = os.getpid()
    headers = {**auth_header(user, pwd), "Content-Type": "application/json"}
    uname = f"audit_user_{suffix}"
    client_rbac.post(
        "/api/system/users",
        headers=headers,
        json={
            "username": uname,
            "password": "audit1234",
            "display_name": "A",
            "role_codes": ["VIEWER"],
        },
    )
    users_payload = client_rbac.get("/api/system/users", headers=headers).json()
    target = next(
        x for x in users_payload["items"]
        if x["username"] == uname
    )
    client_rbac.put(
        f"/api/system/users/{target['id']}/roles",
        headers=headers,
        json={"role_codes": ["SALES"]},
    )
    logs = client_rbac.get(
        "/api/system/audit-logs",
        headers=headers,
        params={"action": "user.roles", "limit": 20},
    )
    assert logs.status_code == 200
    found = [x for x in logs.json() if x.get("target_id") == str(target["id"])]
    assert found
    assert found[0].get("before") is not None
    assert found[0].get("after") is not None


def test_batch_assign_roles(client_rbac, admin_auth):
    user, pwd = admin_auth
    suffix = os.getpid()
    headers = {**auth_header(user, pwd), "Content-Type": "application/json"}
    ids = []
    for i in range(2):
        uname = f"batch_{suffix}_{i}"
        r = client_rbac.post(
            "/api/system/users",
            headers=headers,
            json={
                "username": uname,
                "password": "batch1234",
                "display_name": "B",
                "role_codes": ["VIEWER"],
            },
        )
        assert r.status_code == 200
        ids.append(r.json()["id"])
    r = client_rbac.put(
        "/api/system/users/batch-roles",
        headers=headers,
        json={"user_ids": ids, "role_codes": ["SALES"], "mode": "replace"},
    )
    assert r.status_code == 200, r.text
    payload = client_rbac.get("/api/system/users", headers=headers, params={"q": f"batch_{suffix}"}).json()
    for u in payload["items"]:
        assert "SALES" in u["roles"]


def test_import_users_csv(client_rbac, admin_auth):
    user, pwd = admin_auth
    suffix = os.getpid()
    headers = auth_header(user, pwd)
    csv_body = (
        "username,password,display_name,role_codes\n"
        f"imported_{suffix},import1234,Imported,VIEWER\n"
    )
    r = client_rbac.post(
        "/api/system/users/import",
        headers=headers,
        files={"file": ("users.csv", csv_body.encode("utf-8"), "text/csv")},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("created") == 1
    listed = client_rbac.get(
        "/api/system/users",
        headers={**headers, "Content-Type": "application/json"},
        params={"q": f"imported_{suffix}"},
    ).json()
    assert any(x["username"] == f"imported_{suffix}" for x in listed["items"])


def test_reset_password_must_change_flag(client_rbac, admin_auth):
    user, pwd = admin_auth
    suffix = os.getpid()
    headers = {**auth_header(user, pwd), "Content-Type": "application/json"}
    uname = f"mcp_{suffix}"
    created = client_rbac.post(
        "/api/system/users",
        headers=headers,
        json={
            "username": uname,
            "password": "mcp12345",
            "display_name": "M",
            "role_codes": ["VIEWER"],
        },
    )
    uid = created.json()["id"]
    client_rbac.cookies.clear()
    client_rbac.put(
        f"/api/system/users/{uid}/password",
        headers=headers,
        json={"password": "newmcp12", "must_change_password": True},
    )
    login = _login(client_rbac, uname, "newmcp12")
    me = client_rbac.get("/api/me", cookies=login.cookies).json()
    assert me.get("must_change_password") is True
